"""Device management: scan, add, list, remove, resolve IP."""
import time
from datetime import datetime, timezone

from remote import config as cfg
from remote.broadlink_api import discover_devices, connect_device, mac_bytes_to_str


def _device_label(dev) -> str:
    return (getattr(dev, "manufacturer", "") + " " + (getattr(dev, "model", "") or dev.TYPE)).strip()


def cmd_scan(args) -> None:
    print("Scanning LAN for Broadlink devices...")
    devices = discover_devices(timeout=args.timeout)
    if not devices:
        print("No devices found.")
        return
    print(f"Found {len(devices)} device(s):\n")
    saved = {d["mac"]: d for d in cfg.load_devices()}
    for dev in devices:
        mac = mac_bytes_to_str(dev.mac)
        ip = dev.host[0]
        label = _device_label(dev) or dev.TYPE
        already = mac in saved
        status = f"  [saved as '{saved[mac]['name']}']" if already else "  [not saved]"
        print(f"  {mac}  {ip:<16}  {label}{status}")


def cmd_list(args) -> None:
    devices = cfg.load_devices()
    if not devices:
        print("No devices saved. Use 'uv run remote.py device scan' to find devices.")
        return
    default = cfg.get_default_device()
    print(f"{'NAME':<20} {'MAC':<20} {'MODE':<8} {'IP':<16} {'MODEL'}")
    print("-" * 75)
    for d in devices:
        marker = " *" if d["name"] == default else ""
        ip = d.get("ip") if d.get("ip_mode") == "static" else d.get("cached_ip", "-")
        model = d.get("model", "-")
        print(f"  {d['name']:<18} {d['mac']:<20} {d.get('ip_mode','?'):<8} {ip or '-':<16} {model}{marker}")
    if default:
        print(f"\n* default device")


def cmd_add(args) -> None:
    name = args.name
    devices = cfg.load_devices()
    if any(d["name"] == name for d in devices):
        print(f"Device '{name}' already exists.")
        return

    print(f"Scanning LAN for Broadlink devices...")
    found = discover_devices(timeout=5)
    saved_macs = {d["mac"] for d in devices}

    if not found:
        print("No devices found on LAN.")
        return

    # Filter out already-saved devices
    unsaved = [d for d in found if mac_bytes_to_str(d.mac) not in saved_macs]
    candidates = unsaved if unsaved else found

    if len(candidates) == 1:
        chosen = candidates[0]
        mac = mac_bytes_to_str(chosen.mac)
        ip = chosen.host[0]
        model = _device_label(chosen)
        print(f"Found: {mac}  {ip}  {model}")
        ans = input(f"Save this device as '{name}'? [Y/n] ").strip().lower()
        if ans not in ("", "y"):
            print("Cancelled.")
            return
    else:
        print(f"\nFound {len(candidates)} device(s):")
        for i, dev in enumerate(candidates):
            mac_s = mac_bytes_to_str(dev.mac)
            model = _device_label(dev)
            saved_note = "  [already saved]" if mac_s in saved_macs else ""
            print(f"  [{i + 1}] {mac_s}  {dev.host[0]:<16}  {model}{saved_note}")
        choice = input("\nSelect device number: ").strip()
        try:
            idx = int(choice) - 1
            if not 0 <= idx < len(candidates):
                raise ValueError
        except ValueError:
            print("Cancelled.")
            return
        chosen = candidates[idx]
        mac = mac_bytes_to_str(chosen.mac)
        ip = chosen.host[0]
        model = _device_label(chosen)

    ip_mode = ""
    while ip_mode not in ("static", "dhcp"):
        ip_mode = input("IP mode [static/dhcp] (dhcp recommended): ").strip().lower()

    entry: dict = {"name": name, "mac": mac, "ip_mode": ip_mode}
    if model:
        entry["model"] = model

    if ip_mode == "static":
        static_ip = input(f"Static IP address [{ip}]: ").strip() or ip
        entry["ip"] = static_ip
    else:
        entry["cached_ip"] = ip
        entry["cache_time"] = cfg.now_iso()

    devices.append(entry)
    cfg.save_devices(devices)
    print(f"Device '{name}' saved.")

    # Offer to set as default if no default is set
    if not cfg.get_default_device():
        ans = input(f"Set '{name}' as the default device? [Y/n] ").strip().lower()
        if ans in ("", "y"):
            cfg.set_default_device(name)
            print(f"Default device set to '{name}'.")


def cmd_remove(args) -> None:
    name = args.name
    devices = cfg.load_devices()
    new_devices = [d for d in devices if d["name"] != name]
    if len(new_devices) == len(devices):
        print(f"Device '{name}' not found.")
        return
    cfg.save_devices(new_devices)
    # Clear default if removed
    if cfg.get_default_device() == name:
        cfg.set_default_device("")
    print(f"Device '{name}' removed.")


def cmd_default(args) -> None:
    name = args.name
    devices = cfg.load_devices()
    if not any(d["name"] == name for d in devices):
        print(f"Device '{name}' not found.")
        return
    cfg.set_default_device(name)
    print(f"Default device set to '{name}'.")


def resolve_device(name: str):
    """
    Resolve and connect to a saved device by name.
    Handles DHCP cache expiry and reconnection.
    Returns an authenticated broadlink device object, or raises RuntimeError.
    """
    devices = cfg.load_devices()
    entry = next((d for d in devices if d["name"] == name), None)
    if entry is None:
        raise RuntimeError(f"Device '{name}' not found in config.")

    mac = entry["mac"]
    ip_mode = entry.get("ip_mode", "static")
    learn_timeout = int(cfg.get_setting("learn_timeout"))
    dhcp_cache_ttl = int(cfg.get_setting("dhcp_cache_ttl"))

    if ip_mode == "static":
        ip = entry.get("ip")
        if not ip:
            raise RuntimeError(f"Device '{name}' has no IP configured.")
        dev = connect_device(ip, mac, timeout=learn_timeout)
        if dev is None:
            raise RuntimeError(f"Cannot connect to device '{name}' at {ip}.")
        return dev

    # DHCP mode
    cached_ip = entry.get("cached_ip")
    cache_time_str = entry.get("cache_time")
    now = datetime.now(timezone.utc)

    cache_valid = False
    if cached_ip and cache_time_str:
        try:
            cache_time = cfg.parse_iso(cache_time_str)
            age = (now - cache_time).total_seconds()
            cache_valid = age < dhcp_cache_ttl
        except Exception:
            pass

    if cache_valid:
        dev = connect_device(cached_ip, mac, timeout=5)
        if dev is not None:
            return dev
        print(f"Cached IP {cached_ip} unreachable, rescanning...")

    # Re-scan
    found_ip = _scan_for_mac(mac)
    if not found_ip:
        raise RuntimeError(f"Cannot find device '{name}' (MAC {mac}) on LAN.")

    dev = connect_device(found_ip, mac, timeout=5)
    if dev is None:
        raise RuntimeError(f"Found IP {found_ip} but failed to connect to device '{name}'.")

    # Update cache
    entry["cached_ip"] = found_ip
    entry["cache_time"] = cfg.now_iso()
    cfg.save_devices(devices)
    return dev


def _scan_for_mac(mac: str) -> Optional[str]:
    """Scan LAN and return the IP of the device with the given MAC, or None."""
    discovered = discover_devices(timeout=5)
    for dev in discovered:
        dev_mac = mac_bytes_to_str(dev.mac)
        if dev_mac.upper() == mac.upper():
            return dev.host[0]
    return None
