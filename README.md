# OSC Mixer MCP Server

Hardened MCP server for controlling Behringer digital mixers via Open Sound Control (OSC). One tool vocabulary drives three console families — the model is detected at connect time and a profile supplies every address, encoding and capability count from there on.

| Family | Models | UDP port |
|---|---|---|
| **X-Air** | XR12, XR16, XR18, X18, MR18 | 10024 |
| **X32** | X32, X32 Compact/Producer/Rack, Midas M32 | 10023 |
| **WING** | WING, WING Compact, WING Rack | 2223 |

Forked from [darkwings/OSC_MCP](https://github.com/darkwings/OSC_MCP) with added security controls for use in an LLM tool-use environment.

## Why a profile layer

The families are not interchangeable, and the differences are the kind that fail silently on a live console:

| Concept | X-Air | X32 / M32 | WING |
|---|---|---|---|
| Channel fader | `/ch/01/mix/fader` (0–1) | `/ch/01/mix/fader` (0–1) | `/ch/1/fdr` (**real dB**) |
| Channel mute | `/ch/01/mix/on`, **1 = unmuted** | `/ch/01/mix/on`, **1 = unmuted** | `/ch/1/mute`, **1 = MUTED** |
| Channel name | `/ch/01/config/name` | `/ch/01/config/name` | `/ch/1/$name` |
| Bus fader | `/bus/1/…` (1-digit) | `/bus/01/…` (**2-digit**) | `/bus/1/fdr` |
| Main | `/lr/mix/fader` | `/main/st/mix/fader` | `/main/1/fdr` |
| Head amp | `/headamp/00/gain` | `/headamp/000/gain` | `/ch/1/in/set/g` |
| Identify | `/xinfo` | `/info` | `/?` |
| Raw namespaces | `/-stat/ /-snap/ /-show/` | same + show paths | `/$stat/ /$ctl/ /cfg/` |
| Counts | 16 ch, 6 bus, 4 fx, 4 dca | 32 ch, 16 bus, 8 fx, 8 dca | 40 ch, 16 bus, 16 dca |

Everything above lives in `src/osc_mcp/profiles/` and is pinned by an executable spec in `tests/test_profiles.py`.

## Hardening

- **Network allowlist** — `connect_mixer` and the auto-reconnect path reject any IP outside the allowed networks (`src/osc_mcp/config.py`, or `OSC_MCP_ALLOWED_NETWORKS`). Prevents the server from being aimed at arbitrary LAN hosts by a compromised or prompt-injected client.
- **Per-model OSC allow/deny lists** — `send_raw_osc` and `osc_get` gate on the *connected* model's namespaces. Network reconfiguration, show-wipe, `/node` pass-through and WING's `/#hash` form are denied on every model.
- **Read-only mode** — set `OSC_MCP_READ_ONLY=1` and every write is refused and no subscription is taken. Worth using during a live service, and necessary on WING if another controller already holds the console's single OSC subscription.
- **Source-IP check on replies** — UDP from anyone other than the configured mixer IP is dropped, defeating trivial LAN spoofing.
- **Address-correlated queries** — replies are matched to the request by OSC address, so a stray state push cannot be mistaken for the answer to a different query.
- **Resilient OSC parser** — malformed packets are ignored instead of surfacing parser exceptions or killing the receiver.
- **Model-swap guard** — if the saved IP answers as a different console than last time, auto-reconnect refuses rather than driving it.
- **Pinned dependencies** + committed `uv.lock`.

## Features

- **Faders, mutes, pan** on channels, buses, DCAs, FX sends and main — always in dB
- **Bus sends**, **4/6-band EQ**, **preamp gain and phantom power**
- **Scene/snapshot recall** (X-Air snapshots, X32 show scenes)
- **Batch operations** — many changes in one call instead of N round-trips
- **Pipelined queries** — `query_many` collapses an X32's 56 strip-name lookups into roughly one round-trip
- **Metering and RTA capture** — 100-band averaged spectrum on X-Air/X32
- **Symbolic naming** — address strips as "Kick" or "Drummer"; names sync from the console on connect
- **Raw OSC read and write** escape hatches, both gated

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- A supported mixer on an allowed network

## Installation

```bash
git clone https://github.com/nathanrcast/osc-xr18-mcp.git
cd osc-xr18-mcp
uv sync
```

If the mixer lives outside `192.168.1.0/24`, either set `OSC_MCP_ALLOWED_NETWORKS` or edit `ALLOWED_NETWORKS` in `src/osc_mcp/config.py`.

## Configuration

| Variable | Effect |
|---|---|
| `OSC_MCP_READ_ONLY` | `1`/`true`/`yes`/`on` blocks every write and suppresses the keepalive subscription |
| `OSC_MCP_ALLOWED_NETWORKS` | Comma-separated CIDRs replacing the built-in allowlist, e.g. `192.168.10.0/24,10.1.2.0/24` |

## Running the Server

```bash
# stdio (used by MCP clients)
uv run osc-mixer-mcp

# MCP inspector for interactive testing
uv run mcp dev src/osc_mcp/server.py
```

`osc-xr18-mcp` remains as an alias so existing client registrations keep working.

## Adding to an MCP Client

### Claude Code

```bash
claude mcp add osc-mixer -- uv run --directory /absolute/path/to/osc-xr18-mcp osc-mixer-mcp
```

Or manually:

```json
{
  "mcpServers": {
    "osc-mixer": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/osc-xr18-mcp", "osc-mixer-mcp"]
    }
  }
}
```

### Claude Desktop

```bash
uv run mcp install src/osc_mcp/server.py --name "OSC Mixer"
```

## Usage

1. **Connect**: `connect_mixer("192.168.1.50")` — probes 10024, 10023 and 2223, identifies the model, saves it
2. **Check ranges**: `get_mixer_info()` — the valid channel/bus/DCA numbers depend on the console
3. **Name strips**: names sync automatically; `assign_channel_name(1, "Kick")` adds your own
4. **Control**: `set_channel_fader("Kick", -5)`, `set_channel_send_to_bus("Kick", "Drummer", -10)`
5. **Batch**: `batch([{"op": "channel_fader", "channel": "Kick", "level_db": -6}, {"op": "main_mute", "muted": false}])`

## Available Tools

| Tool | Description |
|---|---|
| `connect_mixer` | Connect and auto-detect the model (allowlist enforced) |
| `get_mixer_info` | Model, firmware, and the console's real ranges |
| `assign_channel_name` / `assign_bus_name` | Add a symbolic name |
| `list_names` / `find_strip` | List or search channel/bus/DCA names |
| `set_channel_fader` / `get_channel_fader` | Channel level in dB |
| `set_channel_mute` | Mute/unmute a channel |
| `set_channel_pan` | Pan a channel (-100 … +100) |
| `set_channel_gain` / `set_phantom_power` | Preamp gain in dB, +48V |
| `get_strip_status` | Name, fader, mute and pan in one round-trip |
| `set_bus_fader` / `set_bus_mute` | Bus master control |
| `set_channel_send_to_bus` / `get_channel_send_to_bus` | Channel→bus send level |
| `set_main_fader` / `set_main_mute` | Main output |
| `set_dca_fader` / `set_dca_mute` | DCA groups |
| `set_channel_eq` / `set_channel_eq_on` | EQ in real Hz/dB/Q |
| `set_fx_send_fader` / `set_fx_send_mute` | FX sends |
| `recall_scene` / `get_scene_name` | Scenes and snapshots |
| `get_meters` / `capture_rta` | Metering and 100-band RTA |
| `batch` | Many changes in one call |
| `send_raw_osc` / `osc_get` / `osc_get_many` | Raw OSC, gated per model |

## Model coverage caveats

X-Air and X32 addresses are drawn from the published OSC specs and verified in the test matrix. **Several WING addresses — sends, preamp gain, phantom, EQ and the subscription token — are from secondary sources and are marked `UNVERIFIED` in `src/osc_mcp/profiles/wing.py`.** Where guessing would mean firing an unknown message at a live console, the profile refuses instead: WING scene recall and metering raise rather than send. `get_mixer_info()` reports these caveats when connected to a WING.

## Running Tests

```bash
uv run pytest
```

The suite runs entirely offline — transport tests drive a loopback UDP console, so no hardware is needed.

## License

Apache License 2.0 (inherited from upstream)
