"""Private, bounded atomic JSON storage and a single-writer node lease."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from .errors import StateError


def process_user_id() -> int:
    getter = getattr(os, "geteuid", None)
    if getter is None:
        raise StateError("Edge process ownership cannot be verified")
    return int(getter())


class JsonStateFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_document(self, *, max_bytes: int) -> dict[str, Any] | None:
        try:
            self._check_directory(create=False)
            if self.path.is_symlink():
                raise StateError("Edge state file must not be a symbolic link")
            if not self.path.exists():
                return None
            self._check_file()
            with self.path.open("rb") as handle:
                payload = handle.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise StateError("Edge state file exceeds the size limit")
            decoded = json.loads(payload)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise StateError("Edge state file is invalid") from exc
        if not isinstance(decoded, dict):
            raise StateError("Edge state must be a JSON object")
        return decoded

    def write_document(self, data: dict[str, Any], *, max_bytes: int) -> None:
        temporary: Path | None = None
        try:
            self._check_directory(create=True)
            if self.path.is_symlink():
                raise StateError("Edge state file must not be a symbolic link")
            if self.path.exists():
                self._check_file()
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            if len(payload.encode("utf-8")) > max_bytes:
                raise StateError("Edge state exceeds the size limit")
            descriptor, name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            if os.name == "posix":
                self.path.chmod(0o600)
                descriptor = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            self._check_file()
        except OSError as exc:
            raise StateError("Edge state could not be saved") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _check_directory(self, *, create: bool) -> None:
        directory = self.path.parent
        if any(parent.is_symlink() for parent in (directory, *directory.parents)):
            raise StateError("Edge state directory must not be a symbolic link")
        if not directory.exists():
            if not create:
                return
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not directory.is_dir():
            raise StateError("Edge state directory is invalid")
        if os.name == "posix":
            metadata = directory.stat()
            if metadata.st_uid != process_user_id():
                raise StateError("Edge state directory must be owned by the Edge process")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise StateError("Edge state directory permissions must be 0700 or stricter")

    def _check_file(self) -> None:
        metadata = self.path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise StateError("Edge state file must be a regular file")
        if os.name == "posix":
            if metadata.st_uid != process_user_id():
                raise StateError("Edge state file must be owned by the Edge process")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise StateError("Edge state file permissions must be 0600 or stricter")


class NodeLease:
    """Prevent simultaneous processes from replaying or replacing the same state."""

    def __init__(self, directory: Path) -> None:
        self.file = JsonStateFile(directory / "node.lock")
        self.descriptor: int | None = None

    def __enter__(self) -> "NodeLease":
        try:
            self.file._check_directory(create=True)
            if self.file.path.is_symlink():
                raise StateError("Edge node lock must not be a symbolic link")
            if self.file.path.exists():
                self.file._check_file()
            descriptor = os.open(
                self.file.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
        except OSError as exc:
            raise StateError("Edge node lock could not be opened") from exc
        try:
            self.file._check_file()
            if sys.platform == "win32":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            raise StateError("Another Edge process is using this state directory") from exc
        except BaseException:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        return self

    def __exit__(self, *args: object) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
