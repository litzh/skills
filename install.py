#!/usr/bin/env python3
"""Install/uninstall skills to ~/.local/bin as standalone commands."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.resolve()
BIN_DIR = Path.home() / ".local/bin"

SKILLS = [
    {
        "dir": "zigbee",
        "script": "zigbee.py",
        "cmd": "zigbee",
        "env": {"ZIGBEE_DATA_DIR": str(Path.home() / ".local/share/zigbee")},
        "data_dirs": [Path.home() / ".local/share/zigbee"],
    },
    {
        "dir": "remote",
        "script": "remote.py",
        "cmd": "remote",
        "env": {"REMOTE_CONFIG_DIR": str(Path.home() / ".config/remote")},
        "data_dirs": [],
        "config_init": {
            "src": SKILLS_DIR / "remote/config",
            "dst": Path.home() / ".config/remote",
        },
    },
    {
        "dir": "tieba",
        "script": "tieba.py",
        "cmd": "tieba",
        "env": {"TIEBA_CACHE_DIR": str(Path.home() / ".cache/tieba")},
        "data_dirs": [Path.home() / ".cache/tieba"],
    },
    {
        "dir": "feishu-api",
        "script": "feishu.py",
        "cmd": "feishu",
        "env": {},
        "data_dirs": [],
    },
    {
        "dir": "astock",
        "script": "main.py",
        "cmd": "astock",
        "env": {"ASTOCK_DATA_DIR": str(Path.home() / ".local/share/astock")},
        "data_dirs": [Path.home() / ".local/share/astock"],
    },
]


def run(cmd: list[str], **kwargs) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def make_wrapper(project_dir: Path, script: Path, env: dict[str, str]) -> str:
    def to_shell_path(p: Path) -> str:
        home = str(Path.home())
        s = str(p)
        if s.startswith(home):
            s = "$HOME" + s[len(home):]
        return s

    lines = [
        "#!/bin/sh",
        '[ -f "$HOME/.config/skills.env" ] && { set -a; . "$HOME/.config/skills.env"; set +a; }',
    ]
    for key, val in env.items():
        shell_val = val.replace(str(Path.home()), "$HOME")
        lines.append(f'export {key}="${{{key}:-{shell_val}}}"')
    lines.append(f'exec uv run --project {to_shell_path(project_dir)} {to_shell_path(script)} "$@"')
    return "\n".join(lines) + "\n"


def init_config(src: Path, dst: Path) -> None:
    """Copy config files from src to dst, never overwriting existing files."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        if rel.name == "devices.toml.example":
            continue
        if rel.name == "devices.toml":
            target = dst / rel
            if not target.exists():
                example = src / "devices.toml.example"
                if example.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(example, target)
                    print(f"    created {target} (from example)")
            continue
        target = dst / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        print(f"    created {target}")


def install_skill(skill: dict) -> None:
    name = skill["cmd"]
    project_dir = SKILLS_DIR / skill["dir"]
    script = project_dir / skill["script"]

    print(f"\n[{name}]")

    for d in skill.get("data_dirs", []):
        d.mkdir(parents=True, exist_ok=True)
        print(f"  data dir: {d}")

    if "config_init" in skill:
        ci = skill["config_init"]
        print(f"  config dir: {ci['dst']}")
        init_config(ci["src"], ci["dst"])

    run(["uv", "sync", "--project", str(project_dir)])

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = BIN_DIR / name
    wrapper_path.write_text(make_wrapper(project_dir, script, skill.get("env", {})))
    wrapper_path.chmod(0o755)
    print(f"  installed: {wrapper_path}")


def uninstall_targets(skill: dict) -> list[Path]:
    """Return the list of paths that uninstall would remove for a skill."""
    project_dir = SKILLS_DIR / skill["dir"]
    return [
        BIN_DIR / skill["cmd"],
        project_dir / ".venv",
    ]


def uninstall_skill(skill: dict, dry_run: bool) -> None:
    name = skill["cmd"]
    print(f"\n[{name}]")

    for path in uninstall_targets(skill):
        if not path.exists():
            print(f"  skip (not found): {path}")
            continue
        if dry_run:
            kind = "dir" if path.is_dir() else "file"
            print(f"  would remove ({kind}): {path}")
        else:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"  removed: {path}")


def cmd_install(args: argparse.Namespace) -> None:
    print(f"Skills dir: {SKILLS_DIR}")
    print(f"Bin dir:    {BIN_DIR}")

    targets = set(args.skills) if args.skills else None
    for skill in SKILLS:
        if targets and skill["cmd"] not in targets:
            continue
        install_skill(skill)

    print("\nDone.")
    if str(BIN_DIR) not in os.environ.get("PATH", ""):
        print(f"Note: add {BIN_DIR} to PATH if not already present.")


def retained_dirs(skill: dict) -> list[Path]:
    """Return data/config directories that uninstall leaves intact."""
    dirs = list(skill.get("data_dirs", []))
    if "config_init" in skill:
        dirs.append(skill["config_init"]["dst"])
    return [d for d in dirs if d.exists()]


def cmd_uninstall(args: argparse.Namespace) -> None:
    print(f"Skills dir: {SKILLS_DIR}")
    print(f"Bin dir:    {BIN_DIR}")
    if args.dry_run:
        print("(dry-run — nothing will be deleted)\n")

    targets = set(args.skills) if args.skills else None
    selected = [s for s in SKILLS if not targets or s["cmd"] in targets]

    for skill in selected:
        uninstall_skill(skill, dry_run=args.dry_run)

    # Always show retained directories
    retained = [(skill["cmd"], d) for skill in selected for d in retained_dirs(skill)]
    if retained:
        print("\nThe following data/config directories are NOT removed:")
        for cmd, d in retained:
            print(f"  [{cmd}] {d}")
        print("Remove them manually if no longer needed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install or uninstall skills.")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    p_install = sub.add_parser("install", help="Install skills (default)")
    p_install.add_argument("skills", nargs="*", metavar="SKILL",
                           help="Skills to install (default: all)")

    p_uninstall = sub.add_parser("uninstall", help="Remove wrapper scripts and venvs")
    p_uninstall.add_argument("skills", nargs="*", metavar="SKILL",
                             help="Skills to uninstall (default: all)")
    p_uninstall.add_argument("--dry-run", action="store_true",
                             help="List files that would be removed without deleting")

    args = parser.parse_args()
    if args.command == "install":
        cmd_install(args)
    else:
        cmd_uninstall(args)


if __name__ == "__main__":
    main()
