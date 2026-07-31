"""MCP server for controlling Behringer X-Air, X32/M32 and WING mixers via OSC.

The console family is detected at connect time and a MixerProfile supplies every
address, encoding and capability count from there on. Tools are model-agnostic;
call get_mixer_info() for the connected console's real ranges.
"""

from __future__ import annotations

import functools
import sys
import time
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from osc_mcp import config, meters, profiles
from osc_mcp.names import NameRegistry
from osc_mcp.osc_client import OscClient
from osc_mcp.profiles import MixerProfile

mcp = FastMCP("osc-mixer-mcp")

# Global state — one mixer at a time.
_client: OscClient | None = None
_profile: MixerProfile | None = None
_registry = NameRegistry()

READ_ONLY_MESSAGE = (
    "Refused: OSC_MCP_READ_ONLY is set, so this server is in read-only mode. "
    "Unset it and restart to allow writes."
)


def writes(fn: Callable) -> Callable:
    """Gate a tool behind read-only mode."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if config.is_read_only():
            return READ_ONLY_MESSAGE
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Connection and detection
# ---------------------------------------------------------------------------


def _probe_for(ip: str, timeout: float = 0.6) -> Callable[[int, str], list | None]:
    """Build a probe callable that opens a short-lived client per candidate port."""

    def probe(port: int, address: str) -> list | None:
        client = OscClient(ip, port)
        try:
            return client.query(address, timeout=timeout)
        except (OSError, ConnectionError):
            return None
        finally:
            client.disconnect()

    return probe


def _sync_names(client: OscClient, profile: MixerProfile) -> int:
    """Pull strip names off the mixer in one round-trip window."""
    _registry.clear()
    wanted: list[tuple[str, int, str]] = []
    for ch in range(1, profile.channels + 1):
        wanted.append(("channel", ch, profile.ch_name(ch)))
    for bus in range(1, profile.buses + 1):
        wanted.append(("bus", bus, profile.bus_name(bus)))
    for dca in range(1, profile.dcas + 1):
        wanted.append(("dca", dca, profile.dca_name(dca)))

    replies = client.query_many([addr for _, _, addr in wanted], timeout=1.5)

    count = 0
    for kind, number, address in wanted:
        result = replies.get(address)
        if result and isinstance(result[0], str) and result[0].strip():
            try:
                _registry.assign_name(kind, number, result[0].strip())
                count += 1
            except ValueError:
                pass  # skip duplicate names
    return count


def _establish(ip: str, port: int | None) -> tuple[OscClient, MixerProfile, list]:
    """Detect the console (or use the given port) and open a client."""
    if port is None:
        found = profiles.detect(_probe_for(ip))
        if found is None:
            raise ConnectionError(
                f"No mixer answered at {ip} on 10024 (X-Air), 10023 (X32) or "
                "2223 (WING). Check the IP and that the console is on the network."
            )
        profile, identity = found
        port = profile.port
    else:
        probe = _probe_for(ip)
        profile_default = profiles.family_default(port)
        address = profile_default.identify_address() if profile_default else "/xinfo"
        identity = probe(port, address)
        if identity is None:
            raise ConnectionError(
                f"Mixer at {ip}:{port} is not responding to {address}."
            )
        joined = " ".join(str(a) for a in identity)
        profile = profiles.for_model(joined) or profile_default
        if profile is None:
            raise ConnectionError(
                f"Port {port} is not a known mixer port and the reply "
                f"({joined!r}) did not identify a model."
            )

    client = OscClient(ip, port)
    keepalive = profile.keepalive()
    if keepalive and not config.is_read_only():
        client.start_keepalive(*keepalive)
    return client, profile, identity


def _get_client() -> OscClient:
    global _client, _profile
    if _client is None:
        stored = config.load_mixer_address()
        if stored is None:
            raise ConnectionError("Not connected. Use connect_mixer(ip) to connect.")
        ip, port = stored
        if not config.is_allowed_ip(ip):
            raise ConnectionError(
                f"Stored mixer IP {ip} is not in the allowed networks. "
                "Refusing auto-connect. Reconnect with connect_mixer(ip)."
            )
        try:
            client, profile, _ = _establish(ip, port)
        except ConnectionError:
            raise ConnectionError(
                f"Not connected. Last known mixer was at {ip}:{port} "
                "but it's not responding — it may be on a different IP "
                "on this network. Ask the user for the current mixer IP."
            )
        stored_model = config.load_mixer_model()
        if stored_model and stored_model != profile.model:
            raise ConnectionError(
                f"Mixer at {ip}:{port} identifies as {profile.model} but "
                f"{stored_model} was saved. Reconnect with connect_mixer(ip) "
                "to confirm the change."
            )
        _client = client
        _profile = profile
        _sync_names(_client, _profile)
    return _client


def _get_profile() -> MixerProfile:
    _get_client()
    assert _profile is not None
    return _profile


def _resolve_channel(channel: str | int) -> int:
    ch = _registry.resolve("channel", channel)
    _get_profile().validate_channel(ch)
    return ch


def _resolve_bus(bus: str | int) -> int:
    b = _registry.resolve("bus", bus)
    _get_profile().validate_bus(b)
    return b


def _resolve_dca(dca: str | int) -> int:
    d = _registry.resolve("dca", dca)
    _get_profile().validate_dca(d)
    return d


@mcp.tool()
def connect_mixer(ip: str, port: int | None = None) -> str:
    """Connect to a mixer and auto-detect its model.

    Leave port unset to probe 10024 (X-Air), 10023 (X32/M32) and 2223 (WING)
    in turn. Supported: XR12/XR16/XR18/X18/MR18, X32 and variants, M32,
    WING/Compact/Rack.
    """
    global _client, _profile
    if not config.is_allowed_ip(ip):
        allowed = ", ".join(str(n) for n in config.allowed_networks())
        return (
            f"Refused: {ip} is not in the allowed networks ({allowed}). "
            "Set OSC_MCP_ALLOWED_NETWORKS or edit src/osc_mcp/config.py."
        )

    try:
        client, profile, identity = _establish(ip, port)
    except ConnectionError as exc:
        return f"Refused: {exc}"

    if _client is not None:
        _client.disconnect()
    _client, _profile = client, profile
    config.save_mixer_address(ip, profile.port, profile.model)

    info = profile.parse_identity(identity)
    synced = _sync_names(client, profile)
    msg = (
        f"Connected to {profile.model} at {ip}:{profile.port} "
        f"(firmware {info['firmware'] or 'unknown'}). Address saved."
    )
    if synced:
        msg += f" Synced {synced} name(s) from the mixer."
    if config.is_read_only():
        msg += " READ-ONLY mode is active; writes will be refused."
    notes = getattr(profile, "verification_notes", ())
    if notes:
        msg += " Caveats: " + " ".join(notes)
    return msg


@mcp.tool()
def get_mixer_info() -> dict[str, Any]:
    """Report the connected console: model, firmware, and its real ranges.

    Call this before addressing channels/buses/DCAs — the valid numbers differ
    per model (XR18 has 16 channels and 6 buses; X32 has 32 and 16; WING 40
    and 16).
    """
    client = _get_client()
    profile = _get_profile()
    identity = client.query(profile.identify_address())
    info = profile.parse_identity(identity or [])
    result: dict[str, Any] = {
        "connected": f"{client.ip}:{client.port}",
        "firmware": info["firmware"],
        "identity": info["raw"],
        "read_only": config.is_read_only(),
        **profile.capabilities(),
    }
    notes = getattr(profile, "verification_notes", ())
    if notes:
        result["caveats"] = list(notes)
    return result


# ---------------------------------------------------------------------------
# Naming / aliases
# ---------------------------------------------------------------------------


@mcp.tool()
def assign_channel_name(channel: int, name: str) -> str:
    """Give a channel a symbolic name, e.g. channel 1 = 'Kick'."""
    _get_profile().validate_channel(channel)
    _registry.assign_name("channel", channel, name)
    return f"Channel {channel} named '{name}'"


@mcp.tool()
def assign_bus_name(bus: int, name: str) -> str:
    """Give a bus a symbolic name, e.g. bus 2 = 'Drummer'."""
    _get_profile().validate_bus(bus)
    _registry.assign_name("bus", bus, name)
    return f"Bus {bus} named '{name}'"


@mcp.tool()
def list_names() -> dict[str, dict[int, str]]:
    """Show all current channel, bus and DCA name assignments."""
    return {
        "channels": _registry.list_names("channel"),
        "buses": _registry.list_names("bus"),
        "dcas": _registry.list_names("dca"),
    }


@mcp.tool()
def find_strip(query: str) -> dict[str, list[dict[str, Any]]]:
    """Search channel/bus/DCA names for a partial match, best match first."""
    return {
        kind: [{"number": n, "name": name} for n, name in _registry.find(kind, query)]
        for kind in ("channel", "bus", "dca")
    }


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_channel_fader(channel: str | int, level_db: float) -> str:
    """Set an input channel's fader level in dB. Channel can be a number or name."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    raw = profile.db_to_raw(level_db)
    client.send(profile.ch_fader(ch), raw)
    return f"Channel {ch} fader set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_channel_mute(channel: str | int, muted: bool) -> str:
    """Mute or unmute an input channel. Channel can be a number or name."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    client.send(profile.ch_mute(ch), profile.encode_mute(muted))
    return f"Channel {ch} {'muted' if muted else 'unmuted'}"


@mcp.tool()
def get_channel_fader(channel: str | int) -> str:
    """Query the current fader level of an input channel."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    result = client.query(profile.ch_fader(ch))
    if result is None:
        return f"Channel {ch}: no response (timeout)"
    raw = result[0] if result else 0.0
    return f"Channel {ch} fader: {profile.raw_to_db(raw):.1f} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_channel_pan(channel: str | int, pan: float) -> str:
    """Pan a channel. -100 is hard left, 0 centre, +100 hard right."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    client.send(profile.ch_pan(ch), profile.pan_to_raw(pan))
    return f"Channel {ch} panned to {pan}"


@mcp.tool()
@writes
def set_channel_gain(channel: str | int, gain_db: float) -> str:
    """Set a channel's preamp (head amp) gain in dB, -12 to +60."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    profile.validate_headamp(ch)
    client.send(profile.ch_gain(ch), profile.gain_to_raw(gain_db))
    return f"Channel {ch} preamp gain set to {gain_db} dB"


@mcp.tool()
@writes
def set_phantom_power(channel: str | int, enabled: bool) -> str:
    """Switch +48V phantom power on a channel's preamp."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    profile.validate_headamp(ch)
    client.send(profile.ch_phantom(ch), profile.encode_on(enabled))
    return f"Channel {ch} phantom power {'on' if enabled else 'off'}"


@mcp.tool()
def get_strip_status(channel: str | int) -> dict[str, Any]:
    """Read a channel's name, fader, mute and pan in one round-trip."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    addresses = {
        "name": profile.ch_name(ch),
        "fader": profile.ch_fader(ch),
        "mute": profile.ch_mute(ch),
        "pan": profile.ch_pan(ch),
    }
    replies = client.query_many(list(addresses.values()))

    def first(key: str) -> Any:
        reply = replies.get(addresses[key])
        return reply[0] if reply else None

    fader, mute, pan = first("fader"), first("mute"), first("pan")
    return {
        "channel": ch,
        "name": first("name"),
        "level_db": round(profile.raw_to_db(fader), 1) if fader is not None else None,
        "muted": profile.decode_mute(mute) if mute is not None else None,
        "pan": round(profile.raw_to_pan(pan), 1) if pan is not None else None,
    }


# ---------------------------------------------------------------------------
# Buses / sends
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_bus_fader(bus: str | int, level_db: float) -> str:
    """Set a bus master fader level in dB. Bus can be a number or name."""
    client = _get_client()
    profile = _get_profile()
    b = _resolve_bus(bus)
    raw = profile.db_to_raw(level_db)
    client.send(profile.bus_fader(b), raw)
    return f"Bus {b} fader set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_bus_mute(bus: str | int, muted: bool) -> str:
    """Mute or unmute a bus. Bus can be a number or name."""
    client = _get_client()
    profile = _get_profile()
    b = _resolve_bus(bus)
    client.send(profile.bus_mute(b), profile.encode_mute(muted))
    return f"Bus {b} {'muted' if muted else 'unmuted'}"


@mcp.tool()
@writes
def set_channel_send_to_bus(
    channel: str | int, bus: str | int, level_db: float
) -> str:
    """Set how much of a channel goes to a specific bus/monitor in dB."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    b = _resolve_bus(bus)
    raw = profile.db_to_raw(level_db)
    client.send(profile.ch_send(ch, b), raw)
    return f"Channel {ch} -> Bus {b} send set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
def get_channel_send_to_bus(channel: str | int, bus: str | int) -> str:
    """Query the current send level from a channel to a bus."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    b = _resolve_bus(bus)
    result = client.query(profile.ch_send(ch, b))
    if result is None:
        return f"Channel {ch} -> Bus {b}: no response (timeout)"
    raw = result[0] if result else 0.0
    return (
        f"Channel {ch} -> Bus {b} send: {profile.raw_to_db(raw):.1f} dB "
        f"(raw {raw:.4f})"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_main_fader(level_db: float) -> str:
    """Set the main output fader level in dB."""
    client = _get_client()
    profile = _get_profile()
    raw = profile.db_to_raw(level_db)
    client.send(profile.main_fader(), raw)
    return f"Main fader set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_main_mute(muted: bool) -> str:
    """Mute or unmute the main output."""
    client = _get_client()
    profile = _get_profile()
    client.send(profile.main_mute(), profile.encode_mute(muted))
    return f"Main {'muted' if muted else 'unmuted'}"


# ---------------------------------------------------------------------------
# DCAs
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_dca_fader(dca: str | int, level_db: float) -> str:
    """Set a DCA group's fader level in dB. DCA can be a number or name."""
    client = _get_client()
    profile = _get_profile()
    d = _resolve_dca(dca)
    raw = profile.db_to_raw(level_db)
    client.send(profile.dca_fader(d), raw)
    return f"DCA {d} fader set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_dca_mute(dca: str | int, muted: bool) -> str:
    """Mute or unmute a DCA group."""
    client = _get_client()
    profile = _get_profile()
    d = _resolve_dca(dca)
    client.send(profile.dca_mute(d), profile.encode_mute(muted))
    return f"DCA {d} {'muted' if muted else 'unmuted'}"


# ---------------------------------------------------------------------------
# EQ
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_channel_eq(
    channel: str | int,
    band: int,
    frequency_hz: float,
    gain_db: float,
    q: float,
) -> str:
    """Set EQ frequency, gain and Q for one band of a channel.

    Takes real-world units — Hz, dB, Q — and normalizes them for the console.
    """
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    profile.validate_eq_band(band)
    client.send(profile.ch_eq_band(ch, band, "f"), profile.eq_freq_to_raw(frequency_hz))
    client.send(profile.ch_eq_band(ch, band, "g"), profile.eq_gain_to_raw(gain_db))
    client.send(profile.ch_eq_band(ch, band, "q"), profile.eq_q_to_raw(q))
    return (
        f"Channel {ch} EQ band {band}: freq={frequency_hz}Hz, "
        f"gain={gain_db}dB, Q={q}"
    )


@mcp.tool()
@writes
def set_channel_eq_on(channel: str | int, enabled: bool) -> str:
    """Enable or disable EQ on a channel."""
    client = _get_client()
    profile = _get_profile()
    ch = _resolve_channel(channel)
    client.send(profile.ch_eq_on(ch), profile.encode_on(enabled))
    return f"Channel {ch} EQ {'enabled' if enabled else 'disabled'}"


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def set_fx_send_fader(fx_slot: int, level_db: float) -> str:
    """Set an FX send fader level in dB."""
    client = _get_client()
    profile = _get_profile()
    profile.validate_fx_slot(fx_slot)
    raw = profile.db_to_raw(level_db)
    client.send(profile.fx_send_fader(fx_slot), raw)
    return f"FX send {fx_slot} set to {level_db} dB (raw {raw:.4f})"


@mcp.tool()
@writes
def set_fx_send_mute(fx_slot: int, muted: bool) -> str:
    """Mute or unmute an FX send."""
    client = _get_client()
    profile = _get_profile()
    profile.validate_fx_slot(fx_slot)
    client.send(profile.fx_send_mute(fx_slot), profile.encode_mute(muted))
    return f"FX send {fx_slot} {'muted' if muted else 'unmuted'}"


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


@mcp.tool()
@writes
def recall_scene(number: int) -> str:
    """Recall a saved scene/snapshot by number.

    This changes the whole console state — confirm with the operator first.
    """
    client = _get_client()
    profile = _get_profile()
    try:
        address, args = profile.scene_recall(number)
    except NotImplementedError as exc:
        return f"Refused: {exc}"
    client.send(address, *args)
    return f"Recalled scene {number} on {profile.model}"


@mcp.tool()
def get_scene_name(number: int) -> str:
    """Read the name of a saved scene/snapshot."""
    client = _get_client()
    profile = _get_profile()
    try:
        address = profile.scene_name(number)
    except NotImplementedError as exc:
        return f"Unavailable: {exc}"
    result = client.query(address)
    if not result:
        return f"Scene {number}: no response (timeout)"
    return f"Scene {number}: {result[0]}"


# ---------------------------------------------------------------------------
# Metering
# ---------------------------------------------------------------------------


def _collect_meters(stream: int, seconds: float) -> tuple[str, list[list[float]]]:
    """Subscribe to a meter stream and gather decoded frames for `seconds`."""
    client = _get_client()
    profile = _get_profile()
    subscribe = profile.meters_subscribe(stream)
    if subscribe is None:
        raise NotImplementedError(
            f"Metering is not mapped for {profile.model} yet."
        )
    address = f"/meters/{stream}"
    frames: list[list[float]] = []

    def handler(args: list[Any]) -> None:
        for arg in args:
            if isinstance(arg, (bytes, bytearray)):
                decoded = meters.decode_meter_blob(bytes(arg))
                if decoded:
                    frames.append(decoded)

    client.add_meter_handler(address, handler)
    try:
        deadline = time.monotonic() + seconds
        sub_address, sub_args = subscribe
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            # Meter subscriptions lapse after ~10 s; renew well inside that.
            client.send(sub_address, *sub_args)
            time.sleep(min(2.0, remaining))
    finally:
        client.remove_meter_handler(address)
    return address, frames


@mcp.tool()
def get_meters(stream: int = 0, seconds: float = 1.0) -> dict[str, Any]:
    """Sample a meter stream and report peak dBFS per slot.

    Stream 0 is the general input/output meter set on X-Air and X32.
    """
    seconds = min(10.0, max(0.2, seconds))
    try:
        address, frames = _collect_meters(stream, seconds)
    except NotImplementedError as exc:
        return {"error": str(exc)}
    if not frames:
        return {"address": address, "frames": 0, "error": "no meter data received"}
    width = min(len(f) for f in frames)
    peaks = [round(max(f[i] for f in frames), 1) for i in range(width)]
    return {"address": address, "frames": len(frames), "peak_db": peaks}


@mcp.tool()
def capture_rta(seconds: float = 3.0) -> dict[str, Any]:
    """Capture the RTA spectrum, averaged over a window.

    Returns 100 (frequency_hz, db) pairs across 20 Hz - 20 kHz. Play pink noise
    or programme material while capturing.
    """
    seconds = min(30.0, max(2.0, seconds))
    profile = _get_profile()
    if profile.rta_meter_index is None:
        return {"error": f"RTA is not mapped for {profile.model} yet."}
    try:
        _, frames = _collect_meters(profile.rta_meter_index, seconds)
    except NotImplementedError as exc:
        return {"error": str(exc)}
    accumulator = meters.RtaAccumulator(profile.rta_bands)
    for frame in frames:
        accumulator.add(frame)
    if accumulator.frames == 0:
        return {
            "frames": 0,
            "error": (
                "no RTA frames received — check that the console is streaming "
                f"/meters/{profile.rta_meter_index}"
            ),
        }
    return {
        "seconds": seconds,
        "frames": accumulator.frames,
        "spectrum": [
            {"hz": hz, "db": db} for hz, db in accumulator.average()
        ],
    }


# ---------------------------------------------------------------------------
# Batch and raw OSC
# ---------------------------------------------------------------------------

_BATCH_OPS: dict[str, Callable[[MixerProfile, dict], tuple[str, list]]] = {
    "channel_fader": lambda p, c: (
        p.ch_fader(_resolve_channel(c["channel"])),
        [p.db_to_raw(float(c["level_db"]))],
    ),
    "channel_mute": lambda p, c: (
        p.ch_mute(_resolve_channel(c["channel"])),
        [p.encode_mute(bool(c["muted"]))],
    ),
    "channel_pan": lambda p, c: (
        p.ch_pan(_resolve_channel(c["channel"])),
        [p.pan_to_raw(float(c["pan"]))],
    ),
    "bus_fader": lambda p, c: (
        p.bus_fader(_resolve_bus(c["bus"])),
        [p.db_to_raw(float(c["level_db"]))],
    ),
    "bus_mute": lambda p, c: (
        p.bus_mute(_resolve_bus(c["bus"])),
        [p.encode_mute(bool(c["muted"]))],
    ),
    "send": lambda p, c: (
        p.ch_send(_resolve_channel(c["channel"]), _resolve_bus(c["bus"])),
        [p.db_to_raw(float(c["level_db"]))],
    ),
    "dca_fader": lambda p, c: (
        p.dca_fader(_resolve_dca(c["dca"])),
        [p.db_to_raw(float(c["level_db"]))],
    ),
    "dca_mute": lambda p, c: (
        p.dca_mute(_resolve_dca(c["dca"])),
        [p.encode_mute(bool(c["muted"]))],
    ),
    "main_fader": lambda p, c: (p.main_fader(), [p.db_to_raw(float(c["level_db"]))]),
    "main_mute": lambda p, c: (p.main_mute(), [p.encode_mute(bool(c["muted"]))]),
}


@mcp.tool()
@writes
def batch(commands: list[dict[str, Any]]) -> str:
    """Apply many mixer changes in one call.

    Each command is a dict with an "op" key plus its arguments:

      {"op": "channel_fader", "channel": "Kick", "level_db": -6}
      {"op": "channel_mute",  "channel": 3, "muted": true}
      {"op": "channel_pan",   "channel": 3, "pan": -40}
      {"op": "bus_fader",     "bus": 1, "level_db": -10}
      {"op": "bus_mute",      "bus": 1, "muted": false}
      {"op": "send",          "channel": 1, "bus": 2, "level_db": -12}
      {"op": "dca_fader",     "dca": 1, "level_db": 0}
      {"op": "dca_mute",      "dca": 1, "muted": true}
      {"op": "main_fader",    "level_db": -3}
      {"op": "main_mute",     "muted": false}

    Commands are validated first; if any is malformed nothing is sent.
    """
    client = _get_client()
    profile = _get_profile()

    planned: list[tuple[str, list]] = []
    for index, command in enumerate(commands):
        op = command.get("op")
        handler = _BATCH_OPS.get(op or "")
        if handler is None:
            return (
                f"Refused: command {index} has unknown op {op!r}. "
                f"Valid ops: {', '.join(sorted(_BATCH_OPS))}"
            )
        try:
            planned.append(handler(profile, command))
        except (KeyError, TypeError, ValueError) as exc:
            return f"Refused: command {index} ({op}) is invalid — {exc}"

    for address, args in planned:
        client.send(address, *args)
    return f"Applied {len(planned)} command(s) to {profile.model}"


def _gate_address(address: str, profile: MixerProfile) -> str | None:
    """Return a refusal message if the address fails the profile's OSC gates."""
    if address.startswith(profile.denied_paths):
        return (
            f"Refused (denylist): {address!r}. "
            f"Denied on {profile.model}: {profile.denied_paths}"
        )
    if not address.startswith(profile.allowed_prefixes):
        return (
            f"Refused: {address!r} is not under an allowed prefix for "
            f"{profile.model}. Allowed: {profile.allowed_prefixes}"
        )
    return None


@mcp.tool()
@writes
def send_raw_osc(address: str, args: list[Any] | None = None) -> str:
    """Send a raw OSC message. Escape hatch for any OSC command.

    Two layers of safety, both per-model: the profile's denylist blocks
    destructive operations (IP/network reconfig, show-wipe, node pass-through),
    and its allowlist gates the overall surface to normal mix, routing, config
    and show addresses.
    """
    client = _get_client()
    profile = _get_profile()
    refusal = _gate_address(address, profile)
    if refusal:
        return refusal
    client.send(address, *(args or []))
    return f"Sent OSC: {address} {args or []}"


@mcp.tool()
def osc_get(address: str) -> dict[str, Any]:
    """Read any single OSC parameter by address. Same gating as send_raw_osc."""
    client = _get_client()
    profile = _get_profile()
    refusal = _gate_address(address, profile)
    if refusal:
        return {"error": refusal}
    result = client.query(address)
    if result is None:
        return {"address": address, "error": "no response (timeout)"}
    return {"address": address, "value": result}


@mcp.tool()
def osc_get_many(addresses: list[str]) -> dict[str, Any]:
    """Read many OSC parameters in one round-trip. Same gating as send_raw_osc."""
    client = _get_client()
    profile = _get_profile()
    for address in addresses:
        refusal = _gate_address(address, profile)
        if refusal:
            return {"error": refusal}
    replies = client.query_many(addresses, timeout=1.5)
    return {
        "values": {
            address: value for address, value in replies.items() if value is not None
        },
        "timed_out": [address for address, value in replies.items() if value is None],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mode = " [READ-ONLY]" if config.is_read_only() else ""
    print(f"OSC mixer MCP server started (stdio transport){mode}", file=sys.stderr)
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\nServer stopped.", file=sys.stderr)
    finally:
        if _client is not None:
            _client.disconnect()


if __name__ == "__main__":
    main()
