"""Exclusive private text files on POSIX and Windows.

Windows ignores the POSIX permission argument to os.open. Restrict the empty
file's DACL before returning a handle that callers can write sensitive data to.
"""

import os
from pathlib import Path
import re
import subprocess


def _restrict_windows_access(path: Path) -> None:
    system32 = Path(os.environ['SystemRoot']) / 'System32'
    identity = subprocess.run(
        [str(system32 / 'whoami.exe'), '/user', '/fo', 'csv', '/nh'],
        check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    match = re.search(rb'"(S-\d+(?:-\d+)+)"', identity.stdout)
    if match is None:
        raise OSError('Cannot determine the current Windows user SID')
    sid = match.group(1).decode('ascii')
    subprocess.run(
        [str(system32 / 'icacls.exe'), str(path), '/inheritance:r', '/grant:r', f'*{sid}:(F)'],
        check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def open_private_text(path: Path):
    """Create a new owner-only file; never overwrite an existing artifact."""
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if os.name == 'nt':
            _restrict_windows_access(path)
        return os.fdopen(fd, 'w', encoding='utf-8')
    except BaseException:
        os.close(fd)
        path.unlink()
        raise
