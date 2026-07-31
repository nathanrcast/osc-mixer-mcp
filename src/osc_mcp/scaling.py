"""Value scaling shared by the X-Air and X32 families.

X-Air and X32 encode almost every continuous parameter as a normalized
0.0-1.0 float. WING takes real units on most paths and overrides these.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# dB <-> fader float conversion
#
# The X-Air/X32 fader uses a non-linear 0.0-1.0 range. We use piecewise-linear
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
MAX_DB = 10.0


def db_to_fader(db: float) -> float:
    """Convert a dB value to the fader float (0.0-1.0).

    Values below -90 dB are clamped to 0.0 (negative infinity).
    Values above +10 dB are clamped to 1.0.
    """
    if db <= NEG_INF_DB:
        return 0.0
    if db >= MAX_DB:
        return 1.0

    for i in range(len(_DB_TABLE) - 1):
        db_lo, fader_lo = _DB_TABLE[i]
        db_hi, fader_hi = _DB_TABLE[i + 1]
        if db_lo <= db <= db_hi:
            t = (db - db_lo) / (db_hi - db_lo)
            return fader_lo + t * (fader_hi - fader_lo)

    return 0.0


def fader_to_db(val: float) -> float:
    """Convert a fader float (0.0-1.0) back to dB.

    Returns -90.0 for fader value 0.0 (representing negative infinity).
    """
    if val <= 0.0:
        return NEG_INF_DB
    if val >= 1.0:
        return MAX_DB

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
# EQ parameter normalization
#
# The mixer expects 0.0-1.0 for frequency, gain and Q -- not the real-world
# values. Sending raw Hz/dB silently lands the band somewhere unrelated.
# ---------------------------------------------------------------------------

EQ_FREQ_MIN_HZ = 20.0
EQ_FREQ_MAX_HZ = 20000.0
EQ_GAIN_MIN_DB = -15.0
EQ_GAIN_MAX_DB = 15.0
# Q runs high-to-low: normalized 0.0 is Q 10, 1.0 is Q 0.3.
EQ_Q_AT_ZERO = 10.0
EQ_Q_AT_ONE = 0.3

_EQ_FREQ_DECADES = math.log10(EQ_FREQ_MAX_HZ / EQ_FREQ_MIN_HZ)
_EQ_Q_DECADES = math.log10(EQ_Q_AT_ZERO / EQ_Q_AT_ONE)


def _clamp01(val: float) -> float:
    return min(1.0, max(0.0, val))


def eq_freq_to_raw(hz: float) -> float:
    """Hz -> 0.0-1.0, logarithmic over 20 Hz - 20 kHz."""
    if hz <= EQ_FREQ_MIN_HZ:
        return 0.0
    if hz >= EQ_FREQ_MAX_HZ:
        return 1.0
    return _clamp01(math.log10(hz / EQ_FREQ_MIN_HZ) / _EQ_FREQ_DECADES)


def raw_to_eq_freq(raw: float) -> float:
    """0.0-1.0 -> Hz."""
    return EQ_FREQ_MIN_HZ * (10 ** (_clamp01(raw) * _EQ_FREQ_DECADES))


def eq_gain_to_raw(db: float) -> float:
    """dB -> 0.0-1.0, linear over -15 dB - +15 dB."""
    span = EQ_GAIN_MAX_DB - EQ_GAIN_MIN_DB
    return _clamp01((db - EQ_GAIN_MIN_DB) / span)


def raw_to_eq_gain(raw: float) -> float:
    """0.0-1.0 -> dB."""
    span = EQ_GAIN_MAX_DB - EQ_GAIN_MIN_DB
    return EQ_GAIN_MIN_DB + _clamp01(raw) * span


def eq_q_to_raw(q: float) -> float:
    """Q -> 0.0-1.0, logarithmic and inverted (Q 10 = 0.0, Q 0.3 = 1.0)."""
    if q >= EQ_Q_AT_ZERO:
        return 0.0
    if q <= EQ_Q_AT_ONE:
        return 1.0
    return _clamp01(math.log10(EQ_Q_AT_ZERO / q) / _EQ_Q_DECADES)


def raw_to_eq_q(raw: float) -> float:
    """0.0-1.0 -> Q."""
    return EQ_Q_AT_ZERO / (10 ** (_clamp01(raw) * _EQ_Q_DECADES))


# ---------------------------------------------------------------------------
# Head amp gain
# ---------------------------------------------------------------------------

GAIN_MIN_DB = -12.0
GAIN_MAX_DB = 60.0


def gain_db_to_raw(db: float) -> float:
    """Preamp gain dB -> 0.0-1.0, linear over -12 dB - +60 dB."""
    span = GAIN_MAX_DB - GAIN_MIN_DB
    return _clamp01((db - GAIN_MIN_DB) / span)


def raw_to_gain_db(raw: float) -> float:
    """0.0-1.0 -> preamp gain dB."""
    span = GAIN_MAX_DB - GAIN_MIN_DB
    return GAIN_MIN_DB + _clamp01(raw) * span


# ---------------------------------------------------------------------------
# Pan
# ---------------------------------------------------------------------------


def pan_to_raw(pan: float) -> float:
    """Pan -100 (hard left) .. +100 (hard right) -> 0.0-1.0."""
    return _clamp01((pan + 100.0) / 200.0)


def raw_to_pan(raw: float) -> float:
    """0.0-1.0 -> pan -100 .. +100."""
    return _clamp01(raw) * 200.0 - 100.0
