"""Reading a file the way the lint promises to: never through a symlink,
anywhere on its path, and never anything but a regular file. The files it
judges and the policy it applies are both read here, so neither path can
reach what the other refuses.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


class Unreadable(Exception):
    pass


def symlink_on_the_way(base: Path, name: str) -> str | None:
    """The first leading part of `name`, as written, that is a symlink."""
    walked = Path()
    for part in Path(name).parts:
        walked = walked / part
        if (base / walked).is_symlink():
            return str(walked)
    return None


def read(base: Path, name: str) -> bytes:
    """The bytes of `name`, written relative to `base`."""
    link = symlink_on_the_way(base, name)
    if link is not None:
        raise Unreadable(f"{name}: {link} is a symlink; name the file it points to")
    try:
        # O_NOFOLLOW refuses a symlink in the last component at open time, so
        # nothing can swap one in between the check above and the read;
        # O_NONBLOCK keeps a FIFO from blocking the open, and the fstat then
        # refuses it, a device, or anything else that is not a regular file
        # before a byte is read.
        fd = os.open(base / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Unreadable(f"{name} is not a regular file")
            return file.read()
    except OSError as error:
        raise Unreadable(f"cannot read {name}: {error.strerror}") from error
