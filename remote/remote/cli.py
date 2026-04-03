"""CLI entry point."""
import argparse
import sys

from remote import config as cfg
from remote import device as dev_mod
from remote import plan as plan_mod
from remote import control as ctrl_mod


def _resolve_device_name(args) -> str:
    """Return the device name from --device arg or fall back to default."""
    name = getattr(args, "device", None)
    if name:
        return name
    default = cfg.get_default_device()
    if default:
        return default
    print(
        "No device specified and no default device set.\n"
        "Use --device <name> or set a default with: uv run remote.py device default <name>"
    )
    sys.exit(1)


def _get_device(args):
    """Resolve device name and return an authenticated broadlink device object."""
    name = _resolve_device_name(args)
    try:
        return dev_mod.resolve_device(name)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


# ---------- device subcommands ----------

def handle_device(args) -> None:
    cfg.ensure_dirs()
    if args.device_cmd == "scan":
        dev_mod.cmd_scan(args)
    elif args.device_cmd == "list":
        dev_mod.cmd_list(args)
    elif args.device_cmd == "add":
        dev_mod.cmd_add(args)
    elif args.device_cmd == "remove":
        dev_mod.cmd_remove(args)
    elif args.device_cmd == "default":
        dev_mod.cmd_default(args)
    else:
        print("Unknown device subcommand.")


# ---------- plan subcommands ----------

def handle_plan(args) -> None:
    cfg.ensure_dirs()
    if args.plan_cmd == "list":
        plan_mod.cmd_list(args)
    elif args.plan_cmd == "show":
        plan_mod.cmd_show(args)
    elif args.plan_cmd == "learn":
        if args.interactive:
            device = _get_device(args)
            plan_mod.cmd_learn_interactive(args, device)
        else:
            device = _get_device(args)
            plan_mod.cmd_learn(args, device)
    else:
        print("Unknown plan subcommand.")


# ---------- control subcommand ----------

def handle_control(args) -> None:
    cfg.ensure_dirs()
    device = _get_device(args)
    ctrl_mod.cmd_control(args, device)


# ---------- parser setup ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remote",
        description="Broadlink IR remote control CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ---- device ----
    p_device = sub.add_parser("device", help="Manage Broadlink devices")
    device_sub = p_device.add_subparsers(dest="device_cmd", metavar="<subcommand>")
    device_sub.required = True

    p_scan = device_sub.add_parser("scan", help="Scan LAN for devices")
    p_scan.add_argument("--timeout", type=int, default=5, help="Scan timeout in seconds")

    device_sub.add_parser("list", help="List saved devices")

    p_add = device_sub.add_parser("add", help="Add a device interactively or manually")
    p_add.add_argument("name", help="Name/alias for the device")
    p_add.add_argument("--ip", metavar="IP", help="Device IP address (skip LAN scan)")
    p_add.add_argument("--mac", metavar="MAC", help="Device MAC address (required with --ip)")
    p_add.add_argument("--model", metavar="MODEL", help="Device model label (optional, with --ip)")
    p_add.add_argument(
        "--ip-mode", metavar="MODE", choices=["static", "dhcp"], default="static",
        help="IP mode: static (default) or dhcp (with --ip)",
    )

    p_remove = device_sub.add_parser("remove", help="Remove a saved device")
    p_remove.add_argument("name", help="Device name to remove")

    p_default = device_sub.add_parser("default", help="Set the default device")
    p_default.add_argument("name", help="Device name to set as default")

    # ---- plan ----
    p_plan = sub.add_parser("plan", help="Manage IR remote plans")
    plan_sub = p_plan.add_subparsers(dest="plan_cmd", metavar="<subcommand>")
    plan_sub.required = True

    plan_sub.add_parser("list", help="List all saved plans")

    p_show = plan_sub.add_parser("show", help="Show keys in a plan")
    p_show.add_argument("plan", help="Plan name")

    p_learn = plan_sub.add_parser("learn", help="Learn IR key(s) into a plan")
    p_learn.add_argument("plan", help="Plan name")
    p_learn.add_argument("key", nargs="?", help="Key name (omit with --interactive)")
    p_learn.add_argument(
        "--interactive", "-i", action="store_true",
        help="Interactively learn multiple keys",
    )
    p_learn.add_argument(
        "--device", "-d", metavar="NAME",
        help="Device to use for learning (overrides default)",
    )

    # ---- control ----
    p_control = sub.add_parser("control", help="Send an IR command")
    p_control.add_argument(
        "--device", "-d", metavar="NAME",
        help="Device to use (overrides default)",
    )
    p_control.add_argument("plan", help="Plan name")
    p_control.add_argument("key", help="Key name")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate: non-interactive learn requires key
    if (
        getattr(args, "command", None) == "plan"
        and getattr(args, "plan_cmd", None) == "learn"
        and not getattr(args, "interactive", False)
        and not getattr(args, "key", None)
    ):
        print("Error: 'uv run remote.py plan learn' requires a key name, or use --interactive.")
        sys.exit(1)

    if args.command == "device":
        handle_device(args)
    elif args.command == "plan":
        handle_plan(args)
    elif args.command == "control":
        handle_control(args)
