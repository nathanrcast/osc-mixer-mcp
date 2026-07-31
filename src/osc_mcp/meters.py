"""Meter blob decoding and RTA accumulation.

X-Air/X32 meter streams arrive as an OSC blob: a little-endian int32 count
followed by that many little-endian int16 samples, each 1/256 dBFS.
"""

from __future__ import annotations

import struct

METER_FLOOR_DB = -80.0
METER_CEILING_DB = 0.0

RTA_MIN_HZ = 20.0
RTA_MAX_HZ = 20000.0


def decode_meter_blob(blob: bytes) -> list[float]:
    """Decode a meter blob into a list of dBFS values.

    Returns an empty list if the blob is too short or malformed.
    """
    if len(blob) < 4:
        return []
    (count,) = struct.unpack("<i", blob[:4])
    if count <= 0:
        return []
    available = (len(blob) - 4) // 2
    count = min(count, available)
    if count <= 0:
        return []
    raw = struct.unpack(f"<{count}h", blob[4 : 4 + count * 2])
    return [
        min(METER_CEILING_DB, max(METER_FLOOR_DB, value / 256.0)) for value in raw
    ]


def rta_band_frequencies(bands: int) -> list[float]:
    """Log-spaced band centre frequencies across 20 Hz - 20 kHz."""
    if bands <= 1:
        return [RTA_MIN_HZ]
    ratio = (RTA_MAX_HZ / RTA_MIN_HZ) ** (1.0 / (bands - 1))
    return [RTA_MIN_HZ * (ratio**i) for i in range(bands)]


class RtaAccumulator:
    """Averages RTA frames over a capture window."""

    def __init__(self, bands: int = 100) -> None:
        self.bands = bands
        self._sums: list[float] = [0.0] * bands
        self._frames = 0

    @property
    def frames(self) -> int:
        return self._frames

    def add(self, values: list[float]) -> None:
        """Fold one frame in. Frames shorter than `bands` are ignored."""
        if len(values) < self.bands:
            return
        for i in range(self.bands):
            self._sums[i] += values[i]
        self._frames += 1

    def average(self) -> list[tuple[float, float]]:
        """Return [(frequency_hz, db), ...] averaged over the captured frames."""
        if self._frames == 0:
            return []
        freqs = rta_band_frequencies(self.bands)
        return [
            (round(freqs[i], 1), round(self._sums[i] / self._frames, 1))
            for i in range(self.bands)
        ]
