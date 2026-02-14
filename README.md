# OSC MCP Server

MCP Server for controlling a Behringer X-Air XR18 digital mixer via Open Sound Control (OSC) protocol.

## Features

- **18 input channels** with fader, mute, EQ (4 bands), and bus sends
- **6 buses** (monitor/aux) with fader and mute
- **Main LR output** control
- **4 FX slots** with send level and mute
- **Symbolic naming** — refer to channels and buses by name (e.g. "Kick", "Drummer") instead of numbers
- **dB-to-float conversion** — work in dB, the server handles the XR18's non-linear fader scale
- **Persistent connection** — the server remembers the last mixer IP across sessions
- **Raw OSC escape hatch** for any unsupported command

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- A Behringer XR18 (or other X-Air mixer) on your local network

## Installation

```bash
git clone https://github.com/your-username/OSC_MCP.git
cd OSC_MCP
uv sync
```

## Running the Server

```bash
# Run via stdio (used by MCP clients)
uv run osc-mcp

# Or use the MCP inspector for interactive testing
uv run mcp dev src/osc_mcp/server.py
```

## Adding to an MCP Client

### Claude Desktop

Add the following to your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "osc-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/OSC_MCP", "osc-mcp"]
    }
  }
}
```

### Claude Code

Add to your project's `.mcp.json` or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "osc-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/OSC_MCP", "osc-mcp"]
    }
  }
}
```

### Cursor

Go to **Settings > MCP Servers > Add Server** and use:

- **Type**: stdio
- **Command**: `uv run --directory /absolute/path/to/OSC_MCP osc-mcp`

### Generic MCP Client

Any MCP-compatible client can connect using the stdio transport:

```bash
uv run --directory /absolute/path/to/OSC_MCP osc-mcp
```

Replace `/absolute/path/to/OSC_MCP` with the actual path where you cloned the repository.

## Usage

Once the server is running in your MCP client:

1. **Connect**: `connect_mixer("192.168.1.1")` — the IP is saved for future sessions
2. **Name your channels**: `assign_channel_name(1, "Kick")`, `assign_bus_name(2, "Drummer")`
3. **Control**: `set_channel_fader("Kick", -5)`, `set_channel_send_to_bus("Kick", "Drummer", -10)`

On subsequent sessions, the server automatically reconnects to the last known mixer IP. If the mixer is unreachable (e.g. different network), the agent is prompted to ask for the new IP.

## Available Tools

| Tool | Description |
|---|---|
| `connect_mixer` | Connect to mixer at IP:port |
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
| `send_raw_osc` | Send any raw OSC message |

## Running Tests

```bash
uv run pytest
```

## License

Apache License 2.0
