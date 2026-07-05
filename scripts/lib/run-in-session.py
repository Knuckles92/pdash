#!/usr/bin/env python3
"""Run a command as the leader of a new POSIX session."""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run-in-session.py COMMAND [ARG...]", file=sys.stderr)
        return 2
    os.setsid()
    os.execvp(sys.argv[1], sys.argv[1:])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
