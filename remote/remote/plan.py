"""Plan management: learn, list, show IR plans."""
from remote import config as cfg
from remote.broadlink_api import learn_ir


def cmd_list(args) -> None:
    plans = cfg.list_plans()
    if not plans:
        print("No plans saved. Use 'uv run remote.py plan learn <plan> <key>' to create one.")
        return
    print("Saved plans:")
    for name in plans:
        plan = cfg.load_plan(name)
        keys = plan.get("keys", [])
        desc = plan.get("description", "")
        suffix = f" — {desc}" if desc else ""
        print(f"  {name:<20} ({len(keys)} keys){suffix}")


def cmd_show(args) -> None:
    name = args.plan
    plans = cfg.list_plans()
    if name not in plans:
        print(f"Plan '{name}' not found.")
        return
    plan = cfg.load_plan(name)
    keys = plan.get("keys", [])
    desc = plan.get("description", "")
    print(f"Plan: {name}" + (f"  ({desc})" if desc else ""))
    if not keys:
        print("  (no keys learned yet)")
        return
    print(f"  {'KEY':<25} CODE LENGTH")
    print("  " + "-" * 45)
    for k in keys:
        code_len = len(k.get("code", "")) // 2
        print(f"  {k['name']:<25} {code_len} bytes")


def cmd_learn(args, device) -> None:
    """Learn a single key into a plan."""
    plan_name = args.plan
    key_name = args.key
    timeout = int(cfg.get_setting("learn_timeout"))

    plan = _get_or_create_plan(plan_name)
    if plan is None:
        return

    code = _do_learn(device, key_name, timeout)
    if code is None:
        return

    _upsert_key(plan, key_name, code)
    cfg.save_plan(plan_name, plan)
    print(f"Key '{key_name}' saved to plan '{plan_name}'.")


def cmd_learn_interactive(args, device) -> None:
    """Interactively learn multiple keys into a plan."""
    plan_name = args.plan
    timeout = int(cfg.get_setting("learn_timeout"))

    # Check for leftover tmp file
    tmp_plans = cfg.list_tmp_plans()
    if plan_name in tmp_plans:
        ans = input(
            f"Found an unfinished session for plan '{plan_name}'. Resume it? [y/N] "
        ).strip().lower()
        if ans == "y":
            plan = cfg.load_tmp_plan(plan_name)
            print(f"Resumed with {len(plan.get('keys', []))} key(s) already learned.")
        else:
            cfg.discard_tmp_plan(plan_name)
            plan = _get_or_create_plan(plan_name)
            if plan is None:
                return
    else:
        plan = _get_or_create_plan(plan_name)
        if plan is None:
            return

    print(f"\nInteractive learning mode for plan '{plan_name}'.")
    print("Type 'stop' as the key name at any time to finish.\n")

    while True:
        key_name = input("Key name (or 'stop' to finish): ").strip()
        if not key_name:
            continue
        if key_name.lower() == "stop":
            break

        code = _do_learn(device, key_name, timeout)
        if code is None:
            print("No signal captured. Skipping this key.")
            continue

        _upsert_key(plan, key_name, code, ask_overwrite=True)
        cfg.save_tmp_plan(plan_name, plan)
        print(f"  -> '{key_name}' saved to temporary plan.\n")

    if not plan.get("keys"):
        print("No keys learned. Nothing saved.")
        cfg.discard_tmp_plan(plan_name)
        return

    key_count = len(plan["keys"])
    ans = input(
        f"\nLearned {key_count} key(s). Save to plan '{plan_name}'? [Y/n] "
    ).strip().lower()
    if ans in ("", "y"):
        cfg.save_plan(plan_name, plan)
        cfg.discard_tmp_plan(plan_name)
        print(f"Plan '{plan_name}' saved with {key_count} key(s).")
    else:
        keep = input("Keep temporary file for next session? [Y/n] ").strip().lower()
        if keep not in ("", "y"):
            cfg.discard_tmp_plan(plan_name)
            print("Temporary file discarded.")
        else:
            print("Temporary file kept. Resume next time with --interactive.")


def _get_or_create_plan(plan_name: str) -> dict | None:
    """Load an existing plan or prompt to create a new one. Returns None if cancelled."""
    plans = cfg.list_plans()
    if plan_name in plans:
        return cfg.load_plan(plan_name)

    ans = input(f"Plan '{plan_name}' does not exist. Create it? [Y/n] ").strip().lower()
    if ans not in ("", "y"):
        print("Cancelled.")
        return None

    desc = input("Description (optional, press Enter to skip): ").strip()
    plan: dict = {"name": plan_name, "keys": []}
    if desc:
        plan["description"] = desc
    return plan


def _do_learn(device, key_name: str, timeout: int) -> bytes | None:
    """
    Put device into learning mode, wait for user to press the remote button,
    then read the captured IR code. Returns raw bytes or None.
    """
    print(f"\nLearning '{key_name}':")
    print("  1. Point your remote at the Broadlink device.")
    print("  2. Press the button you want to learn.")
    input("  3. Press Enter when ready to capture... ")

    print(f"  Waiting for IR signal (timeout: {timeout}s)...")
    code = learn_ir(device, timeout=timeout)

    if code is None:
        print(f"  Timeout: no signal captured within {timeout}s.")
        return None

    print(f"  Signal captured! ({len(code)} bytes)")
    return code


def _upsert_key(plan: dict, key_name: str, code: bytes, ask_overwrite: bool = False) -> None:
    """Insert or update a key in the plan dict."""
    keys: list = plan.setdefault("keys", [])
    code_hex = code.hex()

    for entry in keys:
        if entry["name"] == key_name:
            if ask_overwrite:
                ans = input(
                    f"  Key '{key_name}' already exists. Overwrite? [y/N] "
                ).strip().lower()
                if ans != "y":
                    print(f"  Skipped '{key_name}'.")
                    return
            entry["code"] = code_hex
            return

    keys.append({"name": key_name, "code": code_hex})
