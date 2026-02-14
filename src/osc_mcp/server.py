"""MCP server with tools for controlling a Behringer XR18 mixer via OSC."""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from osc_mcp.osc_client import OscClient
from osc_mcp import config, xair

mcp = FastMCP("osc-mcp")

# Global state
_client: OscClient | None = None
_registry = xair.NameRegistry()


def _sync_names(client: OscClient) -> int:
    """Query channel/bus names from the mixer and populate the registry."""
    count = 0
    for ch in range(1, xair.NUM_CHANNELS + 1):
        result = client.query(xair.ch_config_name(ch))
        if result and isinstance(result[0], str) and result[0].strip():
            try:
                _registry.assign_name("channel", ch, result[0].strip())
                count += 1
            except ValueError:
                pass  # skip duplicate names
    for bus in range(1, xair.NUM_BUSES + 1):
        result = client.query(xair.bus_config_name(bus))
        if result and isinstance(result[0], str) and result[0].strip():
            try:
                _registry.assign_name("bus", bus, result[0].strip())
                count += 1
            except ValueError:
                pass  # skip duplicate names
    return count


def _get_client() -> OscClient:
    global _client
    if _client is None:
        stored = config.load_mixer_address()
        if stored is None:
            raise ConnectionError(
                "Not connected. Use connect_mixer(ip) to connect."
            )
        ip, port = stored
        client = OscClient(ip, port)
        if client.query("/xinfo") is None:
            raise ConnectionError(
                f"Not connected. Last known mixer was at {ip}:{port} "
                "but it's not responding — it may be on a different IP "
                "on this network. Ask the user for the current mixer IP."
            )
        _client = client
        _sync_names(_client)
    return _client


def _resolve_channel(channel: str | int) -> int:
    ch = _registry.resolve("channel", channel)
    xair.validate_channel(ch)
    return ch


def _resolve_bus(bus: str | int) -> int:
    b = _registry.resolve("bus", bus)
    xair.validate_bus(b)
    return b


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


@mcp.tool()
def connect_mixer(ip: str, port: int = 10024) -> str:
    """Connect to the XR18 mixer at the given IP and port (default 10024)."""
    global _client
    client = OscClient(ip, port)
    if client.query("/xinfo") is None:
        return (
            f"Warning: mixer at {ip}:{port} is not responding. "
            "Connection saved but the mixer may be unreachable."
        )
    _client = client
    config.save_mixer_address(ip, port)
    synced = _sync_names(client)
    msg = f"Connected to mixer at {ip}:{port}. Address saved for future sessions."
    if synced:
        msg += f" Synced {synced} name(s) from mixer."
    return msg


# ---------------------------------------------------------------------------
# Naming / Aliases
# ---------------------------------------------------------------------------


@mcp.tool()
def assign_channel_name(channel: int, name: str) -> str:
    """Give a channel (1-18) a symbolic name, e.g. channel 1 = 'Kick'."""
    xair.validate_channel(channel)
    _registry.assign_name("channel", channel, name)
    return f"Channel {channel} named '{name}'"


@mcp.tool()
def assign_bus_name(bus: int, name: str) -> str:
    """Give a bus (1-6) a symbolic name, e.g. bus 2 = 'Drummer'."""
    xair.validate_bus(bus)
    _registry.assign_name("bus", bus, name)
    return f"Bus {bus} named '{name}'"


@mcp.tool()
def list_names() -> dict[str, dict[int, str]]:
    """Show all current channel and bus name assignments."""
    return {
        "channels": _registry.list_names("channel"),
        "buses": _registry.list_names("bus"),
    }


# ---------------------------------------------------------------------------
# Channels (1-18)
# ---------------------------------------------------------------------------


@mcp.tool()
def set_channel_fader(channel: str | int, level_db: float) -> str:
    """Set an input channel's fader level in dB. Channel can be a number (1-18) or name."""
    client = _get_client()
    ch = _resolve_channel(channel)
    fader_val = xair.db_to_fader(level_db)
    client.send(xair.ch_fader(ch), fader_val)
    return f"Channel {ch} fader set to {level_db} dB (float {fader_val:.4f})"


@mcp.tool()
def set_channel_mute(channel: str | int, muted: bool) -> str:
    """Mute or unmute an input channel. Channel can be a number (1-18) or name."""
    client = _get_client()
    ch = _resolve_channel(channel)
    # XR18: mix/on = 0 means muted, 1 means unmuted
    client.send(xair.ch_mute(ch), 0 if muted else 1)
    state = "muted" if muted else "unmuted"
    return f"Channel {ch} {state}"


@mcp.tool()
def get_channel_fader(channel: str | int) -> str:
    """Query the current fader level of an input channel."""
    client = _get_client()
    ch = _resolve_channel(channel)
    result = client.query(xair.ch_fader(ch))
    if result is None:
        return f"Channel {ch}: no response (timeout)"
    fader_val = result[0] if result else 0.0
    db = xair.fader_to_db(fader_val)
    return f"Channel {ch} fader: {db:.1f} dB (float {fader_val:.4f})"


# ---------------------------------------------------------------------------
# Buses / Monitors (1-6)
# ---------------------------------------------------------------------------


@mcp.tool()
def set_bus_fader(bus: str | int, level_db: float) -> str:
    """Set a bus master fader level in dB. Bus can be a number (1-6) or name."""
    client = _get_client()
    b = _resolve_bus(bus)
    fader_val = xair.db_to_fader(level_db)
    client.send(xair.bus_fader(b), fader_val)
    return f"Bus {b} fader set to {level_db} dB (float {fader_val:.4f})"


@mcp.tool()
def set_bus_mute(bus: str | int, muted: bool) -> str:
    """Mute or unmute a bus. Bus can be a number (1-6) or name."""
    client = _get_client()
    b = _resolve_bus(bus)
    client.send(xair.bus_mute(b), 0 if muted else 1)
    state = "muted" if muted else "unmuted"
    return f"Bus {b} {state}"


@mcp.tool()
def set_channel_send_to_bus(
    channel: str | int, bus: str | int, level_db: float
) -> str:
    """Set how much of a channel goes to a specific bus/monitor in dB."""
    client = _get_client()
    ch = _resolve_channel(channel)
    b = _resolve_bus(bus)
    fader_val = xair.db_to_fader(level_db)
    client.send(xair.ch_send_level(ch, b), fader_val)
    return (
        f"Channel {ch} -> Bus {b} send set to {level_db} dB "
        f"(float {fader_val:.4f})"
    )


@mcp.tool()
def get_channel_send_to_bus(channel: str | int, bus: str | int) -> str:
    """Query the current send level from a channel to a bus."""
    client = _get_client()
    ch = _resolve_channel(channel)
    b = _resolve_bus(bus)
    result = client.query(xair.ch_send_level(ch, b))
    if result is None:
        return f"Channel {ch} -> Bus {b}: no response (timeout)"
    fader_val = result[0] if result else 0.0
    db = xair.fader_to_db(fader_val)
    return f"Channel {ch} -> Bus {b} send: {db:.1f} dB (float {fader_val:.4f})"


# ---------------------------------------------------------------------------
# Main LR
# ---------------------------------------------------------------------------


@mcp.tool()
def set_main_fader(level_db: float) -> str:
    """Set the main LR output fader level in dB."""
    client = _get_client()
    fader_val = xair.db_to_fader(level_db)
    client.send(xair.main_fader(), fader_val)
    return f"Main fader set to {level_db} dB (float {fader_val:.4f})"


@mcp.tool()
def set_main_mute(muted: bool) -> str:
    """Mute or unmute the main LR output."""
    client = _get_client()
    client.send(xair.main_mute(), 0 if muted else 1)
    state = "muted" if muted else "unmuted"
    return f"Main LR {state}"


# ---------------------------------------------------------------------------
# EQ (4 bands per channel)
# ---------------------------------------------------------------------------


@mcp.tool()
def set_channel_eq(
    channel: str | int,
    band: int,
    frequency_hz: float,
    gain_db: float,
    q: float,
) -> str:
    """Set EQ parameters for a channel band (1-4)."""
    client = _get_client()
    ch = _resolve_channel(channel)
    xair.validate_eq_band(band)
    client.send(xair.ch_eq_band(ch, band, "f"), frequency_hz)
    client.send(xair.ch_eq_band(ch, band, "g"), gain_db)
    client.send(xair.ch_eq_band(ch, band, "q"), q)
    return (
        f"Channel {ch} EQ band {band}: "
        f"freq={frequency_hz}Hz, gain={gain_db}dB, Q={q}"
    )


@mcp.tool()
def set_channel_eq_on(channel: str | int, enabled: bool) -> str:
    """Enable or disable EQ on a channel."""
    client = _get_client()
    ch = _resolve_channel(channel)
    client.send(xair.ch_eq_on(ch), 1 if enabled else 0)
    state = "enabled" if enabled else "disabled"
    return f"Channel {ch} EQ {state}"


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


@mcp.tool()
def set_fx_send_fader(fx_slot: int, level_db: float) -> str:
    """Set an FX send fader level in dB (slot 1-4)."""
    client = _get_client()
    xair.validate_fx_slot(fx_slot)
    fader_val = xair.db_to_fader(level_db)
    client.send(xair.fx_send_fader(fx_slot), fader_val)
    return f"FX send {fx_slot} set to {level_db} dB (float {fader_val:.4f})"


@mcp.tool()
def set_fx_send_mute(fx_slot: int, muted: bool) -> str:
    """Mute or unmute an FX send (slot 1-4)."""
    client = _get_client()
    xair.validate_fx_slot(fx_slot)
    client.send(xair.fx_send_mute(fx_slot), 0 if muted else 1)
    state = "muted" if muted else "unmuted"
    return f"FX send {fx_slot} {state}"


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


@mcp.tool()
def get_mixer_info() -> str:
    """Query mixer info via /xinfo."""
    client = _get_client()
    result = client.query("/xinfo")
    if result is None:
        return "No response from mixer (timeout)"
    return f"Mixer info: {result}"


# ---------------------------------------------------------------------------
# Raw OSC
# ---------------------------------------------------------------------------


@mcp.tool()
def send_raw_osc(address: str, args: list[Any] | None = None) -> str:
    """Send a raw OSC message. Escape hatch for any OSC command."""
    client = _get_client()
    if args:
        client.send(address, *args)
    else:
        client.send(address)
    return f"Sent OSC: {address} {args or []}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("OSC MCP server started (stdio transport)", file=sys.stderr)
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\nServer stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
