#!/usr/bin/env python3
"""Fetch Agent Monitor's DeepSeek credit without exposing the key to the UI."""

import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def credential():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    keyfile = Path.home() / ".config/omarchy/agents/deepseek.key"
    if keyfile.is_file():
        key = keyfile.read_text().strip()
        if key:
            return key

    authfile = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "opencode/auth.json"
    if authfile.is_file():
        auth = json.loads(authfile.read_text())
        if not isinstance(auth, dict):
            return ""
        entry = auth.get("deepseek", {})
        if isinstance(entry, dict):
            return str(entry.get("key") or "").strip()
    return ""


def fetch():
    try:
        key = credential()
    except (OSError, ValueError, TypeError):
        return {"error": "Could not read DeepSeek credentials."}
    if not key:
        return {"needs_setup": True, "error": "Add your DeepSeek API key below to get started."}

    request = Request("https://api.deepseek.com/user/balance", headers={"Authorization": "Bearer " + key})
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("balance_infos"), list):
            return {"error": "Unexpected response from DeepSeek."}
        return {
            "available": data.get("is_available") is True,
            "balances": [
                {
                    "currency": entry.get("currency", ""),
                    "total": entry.get("total_balance", "0"),
                    "granted": entry.get("granted_balance", "0"),
                    "topped_up": entry.get("topped_up_balance", "0"),
                }
                for entry in data["balance_infos"]
                if isinstance(entry, dict)
            ],
        }
    except HTTPError as exc:
        if exc.code in (401, 403):
            return {"error": "DeepSeek rejected this API key. Check your API credentials."}
        return {"error": "DeepSeek balance request failed (HTTP %s)." % exc.code}
    except (URLError, TimeoutError, OSError):
        return {"error": "Could not reach DeepSeek. Check your connection and retry."}
    except (ValueError, TypeError):
        return {"error": "Unexpected response from DeepSeek."}


if __name__ == "__main__":
    json.dump(fetch(), sys.stdout)
