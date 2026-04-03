"""Configuration file read/write helpers."""
import os
import tomllib
import tomli_w
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("REMOTE_CONFIG_DIR", Path.home() / ".config/remote"))
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEVICES_FILE = CONFIG_DIR / "devices.toml"
PLANS_DIR = CONFIG_DIR / "plans"
TMP_DIR = CONFIG_DIR / ".tmp"

DEFAULT_CONFIG: dict[str, Any] = {
    "default_device": "",
    "settings": {
        "learn_timeout": 10,
        "dhcp_cache_ttl": 86400,
    },
}


def ensure_dirs() -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def load_config() -> dict[str, Any]:
    data = load_toml(CONFIG_FILE)
    # Fill missing keys with defaults
    config = dict(DEFAULT_CONFIG)
    config.update(data)
    settings = dict(DEFAULT_CONFIG["settings"])
    settings.update(data.get("settings", {}))
    config["settings"] = settings
    return config


def save_config(config: dict[str, Any]) -> None:
    save_toml(CONFIG_FILE, config)


def get_setting(key: str) -> Any:
    return load_config()["settings"][key]


def get_default_device() -> str:
    return load_config().get("default_device", "")


def set_default_device(name: str) -> None:
    config = load_config()
    config["default_device"] = name
    save_config(config)


def load_devices() -> list[dict]:
    data = load_toml(DEVICES_FILE)
    return data.get("devices", [])


def save_devices(devices: list[dict]) -> None:
    save_toml(DEVICES_FILE, {"devices": devices})


def load_plan(name: str) -> dict:
    return load_toml(PLANS_DIR / f"{name}.toml")


def save_plan(name: str, plan: dict) -> None:
    save_toml(PLANS_DIR / f"{name}.toml", plan)


def list_plans() -> list[str]:
    if not PLANS_DIR.exists():
        return []
    return sorted(p.stem for p in PLANS_DIR.glob("*.toml"))


def tmp_plan_path(name: str) -> Path:
    return TMP_DIR / f"{name}.toml.tmp"


def load_tmp_plan(name: str) -> dict:
    return load_toml(tmp_plan_path(name))


def save_tmp_plan(name: str, plan: dict) -> None:
    save_toml(tmp_plan_path(name), plan)


def discard_tmp_plan(name: str) -> None:
    path = tmp_plan_path(name)
    if path.exists():
        path.unlink()


def list_tmp_plans() -> list[str]:
    if not TMP_DIR.exists():
        return []
    return [p.stem.removesuffix(".toml") for p in TMP_DIR.glob("*.toml.tmp")]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
