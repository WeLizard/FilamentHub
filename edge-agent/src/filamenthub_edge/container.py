"""Read Supervisor-owned options, then run the common CLI without root privileges."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from .__main__ import main as run_cli
from .config import CONNECTION_ID, NodeConfig
from .errors import StateError
from .node import MAX_KNOWN_CONNECTIONS

DATA_DIRECTORY = Path("/data")


def _state_paths(directory: Path) -> list[tuple[Path, int]]:
    paths = [(directory, 0o700)]
    for name in ("node.json", "node.lock", "connections"):
        path = directory / name
        if path.is_symlink():
            raise StateError("Container state must not contain symbolic links")
        if path.exists():
            paths.append((path, 0o700 if name == "connections" else 0o600))
    connections = directory / "connections"
    if connections.exists():
        if not connections.is_dir():
            raise StateError("Container connections path must be a directory")
        for path in connections.iterdir():
            if path.suffix != ".json" or not CONNECTION_ID.fullmatch(path.stem):
                continue
            paths.append((path, 0o600))
            if len(paths) > MAX_KNOWN_CONNECTIONS + 4:
                raise StateError("Container connection registry is too large")
    return paths


def _prepare_state(directory: Path, uid: int, gid: int) -> None:
    if sys.platform == "win32":
        raise StateError("Container bootstrap requires Linux")
    # Only the app's dedicated mount can be prepared by the root bootstrap.
    if directory != DATA_DIRECTORY or directory.is_symlink():
        raise StateError("Root container bootstrap requires the dedicated /data mount")
    paths = _state_paths(directory)
    for path, mode in paths:
        metadata = path.lstat()
        correct_type = stat.S_ISDIR if mode == 0o700 else stat.S_ISREG
        if not correct_type(metadata.st_mode) or metadata.st_uid not in {0, uid}:
            raise StateError("Container state has an unsafe type or owner")
        if mode == 0o600 and metadata.st_nlink != 1:
            raise StateError("Container state files must not have hard links")
    # No recursive chown: options.json belongs to Supervisor and stays untouched.
    for path, mode in paths:
        os.chmod(path, mode)
        os.chown(path, uid, gid)


def load_container_config() -> NodeConfig:
    if sys.platform == "win32":
        raise StateError("Container bootstrap requires Linux")
    config = NodeConfig.load()
    os.environ.pop("SUPERVISOR_TOKEN", None)
    os.environ.pop("HASSIO_TOKEN", None)
    if os.geteuid() != 0:
        return config
    import pwd

    user = pwd.getpwnam("filamenthub")
    try:
        if "--status" not in sys.argv:
            _prepare_state(config.state_directory, user.pw_uid, user.pw_gid)
        os.umask(0o077)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    except OSError as exc:
        raise StateError("Container storage or privilege setup failed") from exc
    if os.geteuid() == 0:
        raise StateError("Container runtime must not run as root")
    return config


def main() -> None:
    run_cli(config_loader=load_container_config)


if __name__ == "__main__":
    main()
