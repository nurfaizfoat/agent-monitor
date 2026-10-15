# Agent Monitor

A native **Omarchy shell** bar widget for **OpenAI** and **DeepSeek**.
Theme-colored speedometer in the bar, provider logos in the popup.

- **OpenAI:** ChatGPT subscription plan, Codex five-hour and weekly allowances,
  remaining percentage, and reset countdowns. Meters show allowance **left**.
- **DeepSeek:** prepaid API balance, topped-up credits, and granted credits in
  the currencies returned by your account.
- Independent background requests, five-minute refresh, last-known-data labels,
  and an alert at 90% OpenAI usage.

## Install

Requires the Quickshell-based Omarchy shell with plugin support and Python 3.
This is a source plugin: **no compilation or pip packages are needed**.
It does not support Waybar or older Waybar-based Omarchy installations.

```sh
omarchy plugin add https://github.com/nurfaizfoat/agent-monitor --enable
```

Alternatively, clone this repository and install the local source:

```sh
git clone https://github.com/nurfaizfoat/agent-monitor.git
cd agent-monitor
./install.sh
```

The local installer refuses to overwrite an existing plugin. Manage git-based
installs using `omarchy plugin update nurfaizfoat.agent-monitor`.

## First-time setup

When credentials are missing, **hover over the bar icon** to open setup. It
opens automatically once per shell session; click the icon to return later.
Either provider can work independently; configuring both is optional.

### DeepSeek

Enter your API key in the masked field and choose **Save DeepSeek key**.
The key is sent to the helper over stdin, not command-line arguments, and saved
atomically to `~/.config/omarchy/agents/deepseek.key` with owner-only (`0600`)
permissions. The field clears after submitting or closing the panel.

Credential lookup order:

1. `DEEPSEEK_API_KEY` in the shell process environment.
2. `~/.config/omarchy/agents/deepseek.key`.
3. DeepSeek credentials already stored in OpenCode's `auth.json`.

To replace a saved key, edit that private file or remove it and refresh to show
setup again. An environment variable takes precedence over a saved key.

### OpenAI

Use OpenCode's `/connect`, select OpenAI, and sign in with your **ChatGPT
subscription using browser OAuth**, then refresh the widget. In OpenCode V2,
the widget reads the managed credential store using `opencode api get
/api/credential`, with output captured privately. It prefers a compatible
active login, otherwise uses a saved browser login without changing your
active OpenCode account. Token-sharing logins can run models but cannot read
this usage endpoint; they are skipped. If only token-sharing is configured,
add a browser OAuth login as well.

When the V2 API is unavailable, it falls back to the legacy login at
`$XDG_DATA_HOME/opencode/auth.json` (default:
`~/.local/share/opencode/auth.json`). It does not copy or refresh OAuth tokens.
If the browser login expires, reconnect that account through OpenCode.

**An OpenAI API key cannot provide these subscription meters.** This widget
does not show OpenAI API spending or every ChatGPT model's chat limits. The
ChatGPT usage endpoint is unofficial and can change without notice.

## Controls

Click to toggle. Middle-click, Enter, or **R** refreshes both providers.
Escape closes the popup. Opening refreshes data older than one minute.

```sh
omarchy-shell nurfaizfoat.agent-monitor open
omarchy-shell nurfaizfoat.agent-monitor close
omarchy-shell nurfaizfoat.agent-monitor toggle
omarchy-shell nurfaizfoat.agent-monitor refresh
```

## Privacy and development

No keys, tokens, account identifiers, or balance snapshots are distributed.
Credentials remain in your own home directory, outside the plugin. Requests go
directly to `api.deepseek.com` and `chatgpt.com`, with no telemetry or proxy.
Helpers return sanitized status/errors and never emit credentials. Saved keys
are plaintext protected by filesystem permissions, not encrypted storage.
Never commit credential files, screenshots containing account data, or logs
with authorization headers.

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

OpenAI and DeepSeek names and logos belong to their respective owners. This
project is independent and is not endorsed by either provider. The OpenAI
symbol is sourced from Wikimedia Commons (`OpenAI_logo_2025_(symbol).svg`);
the DeepSeek mark is the provider's whale symbol.
