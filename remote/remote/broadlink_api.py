"""Thin wrapper around python-broadlink for IR operations."""
import time

import broadlink
from broadlink.exceptions import ReadError, NetworkTimeoutError, StorageError


def discover_devices(timeout: int = 5) -> list:
    """Scan LAN and return all discovered Broadlink devices (authenticated)."""
    devices = broadlink.discover(timeout=timeout)
    result = []
    for dev in devices:
        try:
            dev.auth()
            result.append(dev)
        except Exception:
            pass
    return result


def connect_device(ip: str, mac_str: str, timeout: int = 5):
    """Connect to a device by IP and verify MAC address."""
    try:
        dev = broadlink.hello(ip, timeout=timeout)
        dev_mac = ":".join(format(b, "02X") for b in dev.mac)
        if dev_mac.upper() != mac_str.upper():
            return None
        dev.auth()
        return dev
    except Exception:
        return None


def mac_bytes_to_str(mac: bytes) -> str:
    return ":".join(format(b, "02X") for b in mac)


def learn_ir(dev, timeout: int = 10) -> bytes | None:
    """
    Enter learning mode and wait for the user to press a button.
    Returns raw IR code bytes, or None on timeout.
    """
    # Drain any leftover data from a previous learning session to avoid StorageError
    try:
        dev.check_data()
    except Exception:
        pass

    dev.enter_learning()
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        try:
            data = dev.check_data()
            return data
        except (ReadError, StorageError):
            continue
    return None


def send_ir(dev, code_hex: str) -> None:
    """Send an IR code (hex string) via the device."""
    dev.send_data(bytes.fromhex(code_hex))
