#!/usr/bin/env python3
"""Save a DeepSeek key from stdin, never command-line arguments or output."""

import json
import os
from pathlib import Path
import sys
import tempfile


def save_key(key):
    key = key.strip()
    if not key or len(key) > 4096 or any(char.isspace() for char in key):
        return {"error": "Enter a valid API key without whitespace."}
    directory = Path.home() / ".config/omarchy/agents"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".deepseek-", dir=directory)
        with os.fdopen(fd, "w") as stream:
            stream.write(key + "\n")
        os.replace(temporary, directory / "deepseek.key")
        return {"saved": True}
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    try:
        result = save_key(sys.stdin.readline(4098))
    except OSError:
        result = {"error": "Could not save the API key. Check configuration directory permissions."}
    json.dump(result, sys.stdout)
