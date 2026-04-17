# OSC XR18 MCP Server

Hardened MCP server for controlling a Behringer X-Air XR18 digital mixer via Open Sound Control (OSC).

Forked from [darkwings/OSC_MCP](https://github.com/darkwings/OSC_MCP) with added security controls for use in an LLM tool-use environment.

## Hardening (vs. upstream)

- **Network allowlist** — `connect_mixer` and the auto-reconnect path reject any IP outside `ALLOWED_NETWORKS` (see `src/osc_mcp/config.py`). Prevents the server from being aimed at arbitrary LAN hosts by a compromised or prompt-injected client.
- **OSC prefix allowlist** — `send_raw_osc` only permits addresses under safe prefixes (`/ch/`, `/bus/`, `/lr/`, `/fxsend/`, `/fx/`, `/headamp/`, `/xinfo`, `/status`). Scene save/load, show recall, and prefs paths are blocked.
- **Source-IP check on query replies** — UDP responses from anyone other than the configured mixer IP are dropped, defeating trivial LAN spoofing.
- **Resilient OSC parser** — malformed packets return `None` instead of surfacing parser exceptions to the tool caller.
- **Pinned dependencies** + committed `uv.lock`.

## Features

- **18 input channels** with fader, mute, EQ (4 bands), and bus sends
- **6 buses** (monitor/aux) with fader and mute
- **Main LR output** control
- **4 FX slots** with send level and mute
- **Symbolic naming** — refer to channels and buses by name (e.g. "Kick", "Drummer") instead of numbers
- **dB-to-float conversion** — work in dB, the server handles the XR18's non-linear fader scale
- **Persistent connection** — the server remembers the last mixer IP across sessions
- **Raw OSC escape hatch** (prefix-restricted, see above)

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- A Behringer XR18 (or other X-Air mixer) on an allowed network

## Installation

```bash
git clone https://github.com/nathanrcast/osc-xr18-mcp.git
cd osc-xr18-mcp
uv sync
```

If the mixer lives on a subnet other than `192.168.1.0/24`, edit `ALLOWED_NETWORKS` in `src/osc_mcp/config.py` before first connect.

## Running the Server

```bash
# stdio (used by MCP clients)
uv run osc-xr18-mcp

# MCP inspector for interactive testing
uv run mcp dev src/osc_mcp/server.py
```

## Adding to an MCP Client

### Claude Code

```bash
claude mcp add osc-xr18 -- uv run --directory /absolute/path/to/osc-xr18-mcp osc-xr18-mcp
```

Or manually:

```json
{
  "mcpServers": {
    "osc-xr18": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/osc-xr18-mcp", "osc-xr18-mcp"]
    }
  }
}
```

### Claude Desktop

```bash
uv run mcp install src/osc_mcp/server.py --name "OSC XR18"
```

## Usage

1. **Connect**: `connect_mixer("192.168.1.50")` — IP is checked against `ALLOWED_NETWORKS`, then saved
2. **Name channels**: `assign_channel_name(1, "Kick")`, `assign_bus_name(2, "Drummer")`
3. **Control**: `set_channel_fader("Kick", -5)`, `set_channel_send_to_bus("Kick", "Drummer", -10)`

## Available Tools

| Tool | Description |
|---|---|
| `connect_mixer` | Connect to mixer at IP:port (allowlist enforced) |
| `assign_channel_name` | Name a channel (1-18) |
| `assign_bus_name` | Name a bus (1-6) |
| `list_names` | Show all name assignments |
| `set_channel_fader` | Set channel level in dB |
| `set_channel_mute` | Mute/unmute a channel |
| `get_channel_fader` | Query current channel level |
| `set_bus_fader` | Set bus level in dB |
| `set_bus_mute` | Mute/unmute a bus |
| `set_channel_send_to_bus` | Set channel→bus send level |
| `get_channel_send_to_bus` | Query channel→bus send level |
| `set_main_fader` | Set main LR level |
| `set_main_mute` | Mute/unmute main LR |
| `set_channel_eq` | Set EQ band parameters |
| `set_channel_eq_on` | Enable/disable channel EQ |
| `set_fx_send_fader` | Set FX send level |
| `set_fx_send_mute` | Mute/unmute FX send |
| `get_mixer_info` | Query mixer info |
| `send_raw_osc` | Send raw OSC (prefix-allowlisted) |

## Running Tests

```bash
uv run pytest
```

## License

Apache License 2.0 (inherited from upstream)
