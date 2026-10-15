#!/usr/bin/env python3
"""Read Codex allowances using OpenCode's login, without copying or rotating it."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def normalize(data):
    limits = []
    rate = data.get("rate_limit") or {}
    for key in ("primary_window", "secondary_window"):
        window = rate.get(key)
        if not isinstance(window, dict) or window.get("used_percent") is None:
            continue
        percent = float(window["used_percent"])
        seconds = int(window.get("limit_window_seconds") or 0)
        reset = int(window.get("reset_at") or 0)
        if not math.isfinite(percent):
            raise ValueError("Invalid percentage")
        label = "5-hour limit" if seconds == 18000 else "Weekly limit" if seconds == 604800 else "%sh limit" % (seconds / 3600)
        limits.append({"label": label, "used": max(0, min(100, percent)), "resetAt": reset})
    if not limits:
        return {"error": "OpenAI did not report any subscription limits."}
    return {"plan": str(data.get("plan_type") or "Subscription"), "limits": limits}


def credentials():
    """Use V2's managed store; auth.json is only a legacy fallback.

    Capture output privately: credential.list includes secret values. Never
    forward stdout/stderr, persist it, or modify/activate any credentials.
    """
    try:
        result = subprocess.run(
            ["opencode", "api", "get", "/api/credential"],
            capture_output=True, text=True, timeout=20, check=True,
        )
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ValueError("Unexpected credential API response")
        entries = [entry for entry in data["data"]
                   if isinstance(entry, dict) and entry.get("integrationID") == "openai"]
        # A compatible active account wins; otherwise use a saved browser
        # account without switching the account OpenCode uses for inference.
        entries.sort(key=lambda entry: entry.get("active") is True, reverse=True)
        return [entry["value"] for entry in entries if isinstance(entry.get("value"), dict)]
    except (OSError, subprocess.SubprocessError, ValueError):
        home = Path.home()
        data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        try:
            data = json.loads((data_home / "opencode/auth.json").read_text())
        except FileNotFoundError:
            return []
        entry = data.get("openai", {}) if isinstance(data, dict) else {}
        return [entry] if isinstance(entry, dict) else []


def fetch():
    try:
        entries = [entry for entry in credentials()
                   if entry.get("type") == "oauth" and isinstance(entry.get("access"), str) and entry["access"]]
        if not entries:
            return {"needs_setup": True, "error": "Connect your ChatGPT subscription using OpenCode /connect, then refresh. An OpenAI API key cannot read Codex subscription limits."}
        compatible = [entry for entry in entries if entry.get("methodID") != "chatgpt-token-sharing"]
        if not compatible:
            return {"needs_setup": True, "error": "OpenAI token-sharing login cannot read usage limits. Add a ChatGPT browser OAuth login in OpenCode /connect, then refresh."}
        rejected = False
        for entry in compatible:
            if entry.get("expires") and float(entry["expires"]) <= time.time() * 1000:
                continue
            headers = {"Authorization": "Bearer " + entry["access"], "User-Agent": "AgentMonitor/2.1", "Accept": "application/json"}
            metadata = entry.get("metadata") or {}
            account = metadata.get("accountID") or entry.get("accountId")
            if account:
                headers["ChatGPT-Account-Id"] = account
            request = Request("https://chatgpt.com/backend-api/wham/usage", headers=headers)
            try:
                with urlopen(request, timeout=15) as response:
                    return normalize(json.load(response))
            except HTTPError as exc:
                if exc.code == 401:
                    rejected = True
                    continue
                return {"error": "OpenAI limits request failed (HTTP %s)." % exc.code}
        if rejected:
            return {"needs_setup": True, "error": "OpenAI rejected the saved login for usage access (HTTP 401). Reconnect with ChatGPT browser OAuth in OpenCode /connect, then refresh."}
        return {"needs_setup": True, "error": "Saved ChatGPT browser login expired. Reconnect that browser account in OpenCode /connect, then refresh."}
    except (URLError, TimeoutError, OSError):
        return {"error": "Could not reach OpenAI. Check your connection and retry."}
    except (ValueError, TypeError, AttributeError, KeyError):
        return {"error": "Could not read OpenAI subscription limits."}


if __name__ == "__main__":
    json.dump(fetch(), sys.stdout)
