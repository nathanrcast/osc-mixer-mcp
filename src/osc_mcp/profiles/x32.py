"""X32 family: X32, X32 Compact/Producer/Rack, Midas M32. UDP 10023.

Shares the X-Air value encoding and most of its address tree. What differs:
bus/matrix indices are zero-padded, main is /main/st, head amps are 3-digit,
identity is /info, and scenes live in the show file rather than snapshots.
"""

from __future__ import annotations

from osc_mcp.profiles.base import MixerProfile

ALLOWED_PREFIXES: tuple[str, ...] = (
    # Input strips
    "/ch/",
    "/auxin/",
    "/fxrtn/",
    "/rtn/",
    # Output strips
    "/bus/",
    "/mtx/",
    "/main/",
    "/dca/",
    # FX
    "/fx/",
    "/fxsend/",
    # I/O and global config
    "/headamp/",
    "/config/",
    "/outputs/",
    # Show / scene / library (destructive subset denied below)
    "/-action/",
    "/-prefs/",
    "/-libs/",
    "/-show/",
    # Status / info / metering
    "/-stat/",
    "/-usb/",
    "/info",
    "/status",
    "/xremote",
    "/meters",
    "/batchsubscribe",
    "/subscribe",
    "/unsubscribe",
    "/renew",
    "/formatsubscribe",
)

DENIED_PATHS: tuple[str, ...] = (
    "/-prefs/ip/",
    "/-prefs/net/",
    # Show-wipe clears the entire scene/cue library in one call
    "/-action/newshow",
    "/-action/clearshow",
    "/-action/delshow",
    "/-action/deletescene",
    # /node takes an arbitrary OSC address as a string argument, which would
    # bypass the prefix allowlist entirely
    "/node",
)


class X32Profile(MixerProfile):
    """X32/M32. Buses and matrices are zero-padded; main is /main/st."""

    family = "x32"
    model = "X32"
    port = 10023

    channels = 32
    buses = 16
    fx = 8
    dcas = 8
    matrices = 6
    aux_ins = 8
    eq_bands = 4
    headamps = 32

    allowed_prefixes = ALLOWED_PREFIXES
    denied_paths = DENIED_PATHS

    def _bus_idx(self, bus: int) -> str:
        # The one shape difference that bites hardest: /bus/01, not /bus/1.
        return self._pad(bus)

    def ch_gain(self, ch: int) -> str:
        # X32 head amps are 3-digit and 0-indexed: /headamp/000 .. /headamp/127
        return f"/headamp/{ch - 1:03d}/gain"

    def ch_phantom(self, ch: int) -> str:
        return f"/headamp/{ch - 1:03d}/phantom"

    def main_fader(self) -> str:
        return "/main/st/mix/fader"

    def main_mute(self) -> str:
        return "/main/st/mix/on"

    def main_name(self) -> str:
        return "/main/st/config/name"

    def mtx_fader(self, mtx: int) -> str:
        return f"/mtx/{self._pad(mtx)}/mix/fader"

    def identify_address(self) -> str:
        return "/info"

    def keepalive(self) -> tuple[str, list, float]:
        return ("/xremote", [], 9.0)

    def meters_subscribe(self, index: int) -> tuple[str, list]:
        return ("/meters", [f"/meters/{index}"])

    rta_meter_index = 4

    def scene_recall(self, number: int) -> tuple[str, list]:
        return ("/-action/goscene", [number])

    def scene_name(self, number: int) -> str:
        return f"/-show/showfile/scene/{number:03d}/name"


class X32RackProfile(X32Profile):
    model = "X32 RACK"
    headamps = 16


class X32ProducerProfile(X32Profile):
    model = "X32 PRODUCER"
    headamps = 16


class X32CompactProfile(X32Profile):
    model = "X32 COMPACT"
    headamps = 16


class M32Profile(X32Profile):
    model = "M32"
