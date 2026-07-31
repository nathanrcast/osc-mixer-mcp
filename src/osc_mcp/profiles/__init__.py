"""Mixer profile registry and model auto-detection."""

from __future__ import annotations

from typing import Callable

from osc_mcp.profiles.base import MixerProfile
from osc_mcp.profiles.wing import (
    WingCompactProfile,
    WingProfile,
    WingRackProfile,
)
from osc_mcp.profiles.x32 import (
    M32Profile,
    X32CompactProfile,
    X32ProducerProfile,
    X32Profile,
    X32RackProfile,
)
from osc_mcp.profiles.xair import (
    MR18Profile,
    X18Profile,
    XR12Profile,
    XR16Profile,
    XR18Profile,
    XAirProfile,
)

__all__ = [
    "MixerProfile",
    "PROFILES",
    "PROBE_ORDER",
    "detect",
    "for_model",
    "family_default",
]

# Ordered longest-first so "X32 RACK" wins over "X32" and "WING RACK" over
# "WING" when substring-matching an identity reply.
_REGISTRY: tuple[tuple[str, MixerProfile], ...] = (
    ("X32 PRODUCER", X32ProducerProfile()),
    ("X32 COMPACT", X32CompactProfile()),
    ("X32 RACK", X32RackProfile()),
    ("WING COMPACT", WingCompactProfile()),
    ("WING RACK", WingRackProfile()),
    ("XR18", XR18Profile()),
    ("XR16", XR16Profile()),
    ("XR12", XR12Profile()),
    ("MR18", MR18Profile()),
    ("X18", X18Profile()),
    ("X32", X32Profile()),
    ("M32", M32Profile()),
    ("WING", WingProfile()),
)

PROFILES: dict[str, MixerProfile] = {name: prof for name, prof in _REGISTRY}

# (port, identify_address, fallback profile) tried in order during detection.
PROBE_ORDER: tuple[tuple[int, str, MixerProfile], ...] = (
    (10024, "/xinfo", XR18Profile()),
    (10023, "/info", X32Profile()),
    (2223, "/?", WingProfile()),
)


def for_model(model: str) -> MixerProfile | None:
    """Match a model string from an identity reply to a profile."""
    upper = model.upper()
    for name, profile in _REGISTRY:
        if name in upper:
            return profile
    return None


def family_default(port: int) -> MixerProfile | None:
    """Profile to assume when a port answers but the model string is unknown."""
    for probe_port, _, profile in PROBE_ORDER:
        if probe_port == port:
            return profile
    return None


def detect(
    probe: Callable[[int, str], list | None],
) -> tuple[MixerProfile, list] | None:
    """Identify the console by probing each family's port and identify address.

    `probe(port, address)` should send the address to that port and return the
    reply args, or None on timeout. Returns (profile, identity_args) or None if
    nothing answered.
    """
    for port, address, fallback in PROBE_ORDER:
        reply = probe(port, address)
        if reply is None:
            continue
        joined = " ".join(str(a) for a in reply)
        profile = for_model(joined) or fallback
        return profile, reply
    return None
