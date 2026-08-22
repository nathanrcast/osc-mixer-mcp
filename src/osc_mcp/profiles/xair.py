"""X-Air family: XR12, XR16, XR18, X18, MR18. UDP 10024."""

from __future__ import annotations

from osc_mcp.profiles.base import MixerProfile

ALLOWED_PREFIXES: tuple[str, ...] = (
    # Input strips
    "/ch/",
    "/auxin/",
    "/rtn/",
    # Output strips
    "/bus/",
    "/lr/",
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
    "/-snap/",
    "/-show/",
    # Status / info / metering
    "/-stat/",
    "/-usb/",
    "/xinfo",
    "/xremote",
    "/info",
    "/status",
    "/meters",
    "/batchsubscribe",
    "/subscribe",
    "/unsubscribe",
    "/renew",
)

DENIED_PATHS: tuple[str, ...] = (
    # Network/IP changes would disconnect the mixer until X AIR rediscovers it
    "/-prefs/ip/",
    "/-prefs/net/",
    # Show-wipe clears saved scene/cue library in one call
    "/-action/newshow",
    "/-action/clearshow",
    # /node takes an arbitrary OSC address as a string argument, which would
    # bypass the prefix allowlist entirely
    "/node",
)


class XAirProfile(MixerProfile):
    """X-Air. Channels are 2-digit, buses 1-digit, main is /lr."""

    family = "x-air"
    model = "XR18"
    port = 10024

    channels = 16
    buses = 6
    fx = 4
    dcas = 4
    matrices = 0
    aux_ins = 2
    eq_bands = 4
    headamps = 16

    allowed_prefixes = ALLOWED_PREFIXES
    denied_paths = DENIED_PATHS

    def main_fader(self) -> str:
        return "/lr/mix/fader"

    def main_mute(self) -> str:
        return "/lr/mix/on"

    def main_name(self) -> str:
        return "/lr/config/name"

    def ch_gain(self, ch: int) -> str:
        """X-Air head amps are 1-indexed: /headamp/01 is channel 1.

        Verified on an XR18 (fw 1.16): /headamp/00 never answers, while
        /headamp/01../headamp/16 map 1:1 onto /ch/01../ch/16. The X32's
        0-indexed scheme in the base class silently writes to a
        non-existent address here.
        """
        return f"/headamp/{self._pad(ch)}/gain"

    def ch_phantom(self, ch: int) -> str:
        return f"/headamp/{self._pad(ch)}/phantom"

    def identify_address(self) -> str:
        return "/xinfo"

    def keepalive(self) -> tuple[str, list, float]:
        # /xremote expires after ~10 s; renew inside that window.
        return ("/xremote", [], 9.0)

    def meters_subscribe(self, index: int) -> tuple[str, list]:
        return ("/meters", [f"/meters/{index}"])

    rta_meter_index = 4

    def scene_recall(self, number: int) -> tuple[str, list]:
        return ("/-snap/load", [number])

    def scene_name(self, number: int) -> str:
        return f"/-snap/{self._pad(number)}/name"


class XR18Profile(XAirProfile):
    model = "XR18"


class X18Profile(XAirProfile):
    model = "X18"


class MR18Profile(XAirProfile):
    model = "MR18"


class XR16Profile(XAirProfile):
    model = "XR16"
    channels = 16
    headamps = 12


class XR12Profile(XAirProfile):
    model = "XR12"
    channels = 12
    buses = 2
    fx = 2
    headamps = 8
