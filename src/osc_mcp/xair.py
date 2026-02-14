"""XR18-specific constants, OSC address builders, dB conversion, and name registry."""

from __future__ import annotations

import math

# XR18 constants
NUM_CHANNELS = 18
NUM_BUSES = 6
NUM_FX_SLOTS = 4
NUM_FX_RETURNS = 4
NUM_EQ_BANDS = 4

# ---------------------------------------------------------------------------
# dB <-> fader float conversion
#
# The XR18 fader uses a non-linear 0.0–1.0 range. We use piecewise-linear
# interpolation between known reference points measured from the hardware.
# ---------------------------------------------------------------------------

_DB_TABLE: list[tuple[float, float]] = [
    (-90.0, 0.0),
    (-60.0, 0.0625),
    (-30.0, 0.25),
    (-10.0, 0.5),
    (0.0, 0.75),
    (10.0, 1.0),
]

NEG_INF_DB = -90.0


def db_to_fader(db: float) -> float:
    """Convert a dB value to the XR18 fader float (0.0–1.0).

    Values below -90 dB are clamped to 0.0 (negative infinity).
    Values above +10 dB are clamped to 1.0.
    """
    if db <= NEG_INF_DB:
        return 0.0
    if db >= 10.0:
        return 1.0

    for i in range(len(_DB_TABLE) - 1):
        db_lo, fader_lo = _DB_TABLE[i]
        db_hi, fader_hi = _DB_TABLE[i + 1]
        if db_lo <= db <= db_hi:
            t = (db - db_lo) / (db_hi - db_lo)
            return fader_lo + t * (fader_hi - fader_lo)

    return 0.0


def fader_to_db(val: float) -> float:
    """Convert an XR18 fader float (0.0–1.0) back to dB.

    Returns -90.0 for fader value 0.0 (representing negative infinity).
    """
    if val <= 0.0:
        return NEG_INF_DB
    if val >= 1.0:
        return 10.0

    for i in range(len(_DB_TABLE) - 1):
        _, fader_lo = _DB_TABLE[i]
        _, fader_hi = _DB_TABLE[i + 1]
        if fader_lo <= val <= fader_hi:
            db_lo = _DB_TABLE[i][0]
            db_hi = _DB_TABLE[i + 1][0]
            t = (val - fader_lo) / (fader_hi - fader_lo)
            return db_lo + t * (db_hi - db_lo)

    return NEG_INF_DB


# ---------------------------------------------------------------------------
# OSC address builders
# ---------------------------------------------------------------------------


def _pad(n: int) -> str:
    """Zero-pad a number to two digits."""
    return f"{n:02d}"


def ch_fader(ch: int) -> str:
    """Channel fader: /ch/01/mix/fader"""
    return f"/ch/{_pad(ch)}/mix/fader"


def ch_mute(ch: int) -> str:
    """Channel mute: /ch/01/mix/on"""
    return f"/ch/{_pad(ch)}/mix/on"


def ch_send_level(ch: int, bus: int) -> str:
    """Channel send to bus level: /ch/01/mix/01/level"""
    return f"/ch/{_pad(ch)}/mix/{_pad(bus)}/level"


def ch_eq_band(ch: int, band: int, param: str) -> str:
    """Channel EQ band parameter: /ch/01/eq/1/f, /ch/01/eq/1/g, /ch/01/eq/1/q"""
    return f"/ch/{_pad(ch)}/eq/{band}/{param}"


def ch_eq_on(ch: int) -> str:
    """Channel EQ on/off: /ch/01/eq/on"""
    return f"/ch/{_pad(ch)}/eq/on"


def bus_fader(bus: int) -> str:
    """Bus fader: /bus/1/mix/fader"""
    return f"/bus/{bus}/mix/fader"


def bus_mute(bus: int) -> str:
    """Bus mute: /bus/1/mix/on"""
    return f"/bus/{bus}/mix/on"


def main_fader() -> str:
    """Main LR fader: /lr/0/mix/fader"""
    return "/lr/0/mix/fader"


def main_mute() -> str:
    """Main LR mute: /lr/0/mix/on"""
    return "/lr/0/mix/on"


def fx_send_fader(slot: int) -> str:
    """FX send fader: /fxsend/1/mix/fader"""
    return f"/fxsend/{slot}/mix/fader"


def fx_send_mute(slot: int) -> str:
    """FX send mute: /fxsend/1/mix/on"""
    return f"/fxsend/{slot}/mix/on"


def ch_config_name(ch: int) -> str:
    """Channel config name: /ch/01/config/name"""
    return f"/ch/{_pad(ch)}/config/name"


def bus_config_name(bus: int) -> str:
    """Bus config name: /bus/1/config/name"""
    return f"/bus/{bus}/config/name"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_channel(ch: int) -> None:
    if not 1 <= ch <= NUM_CHANNELS:
        raise ValueError(f"Channel must be 1-{NUM_CHANNELS}, got {ch}")


def validate_bus(bus: int) -> None:
    if not 1 <= bus <= NUM_BUSES:
        raise ValueError(f"Bus must be 1-{NUM_BUSES}, got {bus}")


def validate_fx_slot(slot: int) -> None:
    if not 1 <= slot <= NUM_FX_SLOTS:
        raise ValueError(f"FX slot must be 1-{NUM_FX_SLOTS}, got {slot}")


def validate_eq_band(band: int) -> None:
    if not 1 <= band <= NUM_EQ_BANDS:
        raise ValueError(f"EQ band must be 1-{NUM_EQ_BANDS}, got {band}")


# ---------------------------------------------------------------------------
# Name Registry
# ---------------------------------------------------------------------------


class NameRegistry:
    """Bidirectional mapping of symbolic names to numbers for channels and buses."""

    def __init__(self) -> None:
        self._name_to_number: dict[str, dict[str, int]] = {
            "channel": {},
            "bus": {},
        }
        self._number_to_name: dict[str, dict[int, str]] = {
            "channel": {},
            "bus": {},
        }

    def _validate_kind(self, kind: str) -> None:
        if kind not in ("channel", "bus"):
            raise ValueError(f"Kind must be 'channel' or 'bus', got '{kind}'")

    def assign_name(self, kind: str, number: int, name: str) -> None:
        """Assign a symbolic name to a channel or bus number."""
        self._validate_kind(kind)
        key = name.lower()

        # Check if name is already used for a different number
        existing = self._name_to_number[kind].get(key)
        if existing is not None and existing != number:
            raise ValueError(
                f"Name '{name}' is already assigned to {kind} {existing}"
            )

        # Remove old name for this number if it exists
        old_name = self._number_to_name[kind].get(number)
        if old_name is not None:
            del self._name_to_number[kind][old_name.lower()]

        self._name_to_number[kind][key] = number
        self._number_to_name[kind][number] = name

    def resolve(self, kind: str, name_or_number: str | int) -> int:
        """Resolve a name or number to a number.

        Accepts an int, a string that parses as int, or a symbolic name.
        """
        self._validate_kind(kind)

        if isinstance(name_or_number, int):
            return name_or_number

        # Try parsing as integer
        try:
            return int(name_or_number)
        except (ValueError, TypeError):
            pass

        # Look up as name (case-insensitive)
        key = name_or_number.lower()
        number = self._name_to_number[kind].get(key)
        if number is None:
            raise ValueError(
                f"Unknown {kind} name: '{name_or_number}'. "
                f"Use assign_{kind}_name() first or pass a number."
            )
        return number

    def list_names(self, kind: str) -> dict[int, str]:
        """Return dict of number -> name for the given kind."""
        self._validate_kind(kind)
        return dict(self._number_to_name[kind])
