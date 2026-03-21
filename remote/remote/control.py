"""Control: send an IR command from a plan via a device."""
from remote import config as cfg
from remote.broadlink_api import send_ir


def cmd_control(args, device) -> None:
    plan_name = args.plan
    key_name = args.key

    plans = cfg.list_plans()
    if plan_name not in plans:
        print(f"Plan '{plan_name}' not found.")
        return

    plan = cfg.load_plan(plan_name)
    keys = plan.get("keys", [])
    entry = next((k for k in keys if k["name"] == key_name), None)

    if entry is None:
        available = ", ".join(k["name"] for k in keys) or "(none)"
        print(f"Key '{key_name}' not found in plan '{plan_name}'.")
        print(f"Available keys: {available}")
        return

    code_hex = entry.get("code", "")
    if not code_hex:
        print(f"Key '{key_name}' has no IR code stored.")
        return

    send_ir(device, code_hex)
    print(f"Sent '{key_name}' via plan '{plan_name}'.")
