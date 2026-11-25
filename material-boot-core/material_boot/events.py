"""The install log and the machine-readable progress stream (`--progress json`). stdlib only.

Moved verbatim from material-grub's install/installer.py (release/0.8.0, 588f909); tests/test_provenance.py checks that. `LineEvents` turns everything printed
into `log` events, `Tee` copies the terminal into the persistent log, `open_log` opens it. The log is /var/log/material-grub/install.log ($MG_INSTALL_LOG
moves it): the historical name stays, like the other paths.
"""

import os
import re
import time
from pathlib import Path


class LineEvents:
    """File-like stand-in for sys.stdout/sys.stderr in --progress json mode: every printed line becomes a 'log' event."""

    def __init__(self, emit, level):
        self.emit, self.level, self.buf = emit, level, ""

    def write(self, text):
        self.buf += text
        *lines, self.buf = self.buf.split("\n")
        for ln in lines:
            if ln.strip():
                self.emit("log", text=ln.rstrip(), level=self.level)
        return len(text)

    def flush(self):
        if self.buf.strip():
            self.emit("log", text=self.buf.rstrip(), level=self.level)
        self.buf = ""

    def isatty(self):
        return False


class Tee:
    """Copies everything printed to the terminal into the install log too (colour codes stripped)."""

    def __init__(self, real, logf):
        self.real, self.logf, self.buf = real, logf, ""

    def write(self, text):
        self.real.write(text)
        self.buf += text.replace("\r", "\n")
        *lines, self.buf = self.buf.split("\n")
        for ln in lines:
            ln = re.sub(r"\x1b\[[0-9;]*m", "", ln).rstrip()
            if ln.strip():
                self.logf.write(time.strftime("%F %T ") + ln + "\n")
        self.logf.flush()
        return len(text)

    def flush(self):
        self.real.flush()

    def __getattr__(self, name):
        return getattr(self.real, name)


def open_log():
    """The persistent install log: $MG_INSTALL_LOG, else /var/log/material-grub/install.log. None when it cannot be written
    (no root, read-only /var): logging is never a reason to fail an install."""
    path = Path(os.environ.get("MG_INSTALL_LOG", "/var/log/material-grub/install.log"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 1_000_000:  # keep one old log, the file never grows without bound
            os.replace(path, str(path) + ".1")
        return open(path, "a", errors="replace")
    except OSError:
        return None
