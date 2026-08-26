"""Start, stop and check one local printer-adapter protocol family at a time."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.adapter-lab.yml"
SMOKE_SCRIPT = ROOT / "adapter-lab" / "smoke.py"
SERVICES = {
    "octoprint": ("octoprint",),
    "moonraker": ("moonraker-hh",),
    "bambu": ("bambu-lan",),
    "current": ("octoprint", "moonraker-hh", "bambu-lan"),
}


def services_for(target: str) -> tuple[str, ...]:
    return SERVICES[target]


def _compose(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        "filamenthub-adapter-lab",
        "--file",
        str(COMPOSE_FILE),
        *args,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="On-demand local protocol lab; a target is always explicit."
    )
    parser.add_argument("command", choices=("up", "stop", "status", "logs", "smoke"))
    parser.add_argument("target", choices=tuple(SERVICES))
    parser.add_argument(
        "--follow", action="store_true", help="follow logs until interrupted"
    )
    args = parser.parse_args()
    services = services_for(args.target)

    if args.command == "up":
        command = _compose(
            "up",
            "--detach",
            "--build",
            "--wait",
            "--wait-timeout",
            "180",
            *services,
        )
    elif args.command == "stop":
        command = _compose("stop", *services)
    elif args.command == "status":
        command = _compose("ps", *services)
    elif args.command == "logs":
        command = _compose("logs", "--tail", "200")
        if args.follow:
            command.append("--follow")
        command.extend(services)
    else:
        if args.follow:
            parser.error("--follow is only valid with logs")
        command = [sys.executable, str(SMOKE_SCRIPT), args.target]

    if args.follow and args.command != "logs":
        parser.error("--follow is only valid with logs")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
