#!/usr/bin/env python3
"""Read Codex allowances using OpenCode's login, without copying or rotating it."""

import json
import math
import os
from pathlib import Path
import sys
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


def fetch():
    try:
        home = Path.home()
        data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        entry = json.loads((data_home / "opencode/auth.json").read_text()).get("openai", {})
        if not isinstance(entry, dict) or entry.get("type") != "oauth" or not entry.get("access"):
            return {"needs_setup": True, "error": "Connect your ChatGPT subscription in OpenCode (opencode auth login), then refresh. An OpenAI API key cannot read Codex subscription limits."}
        headers = {"Authorization": "Bearer " + entry["access"], "User-Agent": "AgentMonitor/2.0", "Accept": "application/json"}
        if entry.get("accountId"):
            headers["ChatGPT-Account-Id"] = entry["accountId"]
        request = Request("https://chatgpt.com/backend-api/wham/usage", headers=headers)
        with urlopen(request, timeout=15) as response:
            return normalize(json.load(response))
    except FileNotFoundError:
        return {"needs_setup": True, "error": "Connect your ChatGPT subscription in OpenCode (opencode auth login), then refresh. An OpenAI API key cannot read Codex subscription limits."}
    except HTTPError as exc:
        if exc.code == 401:
            return {"error": "OpenAI login expired. Reconnect OpenAI in OpenCode, then refresh."}
        return {"error": "OpenAI limits request failed (HTTP %s)." % exc.code}
    except (URLError, TimeoutError, OSError):
        return {"error": "Could not reach OpenAI. Check your connection and retry."}
    except (ValueError, TypeError, AttributeError, KeyError):
        return {"error": "Could not read OpenAI subscription limits."}


if __name__ == "__main__":
    json.dump(fetch(), sys.stdout)
