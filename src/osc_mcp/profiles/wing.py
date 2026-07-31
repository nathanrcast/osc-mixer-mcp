"""WING family: WING, WING Compact, WING Rack. UDP 2223.

WING diverges from X-Air/X32 far more than they diverge from each other:

* Faders take **real dB**, not a normalized 0-1 taper.
* Mute polarity is **inverted** -- `/ch/1/mute 1` means muted, whereas X-Air's
  `/ch/01/mix/on 1` means *un*muted.
* Indices are 1-digit, names live at `$name`, and the namespace roots are
  `/$stat/`, `/$ctl/` and `/cfg/`.
* Only **one** OSC client may hold a subscription at a time, so the keepalive
  thread can steal the console away from an operator's other tool. Run
  read-only if something else is already subscribed.

Addresses marked UNVERIFIED are drawn from secondary sources rather than a
console. They are wired up so the hardware smoke test can confirm them; where
guessing would mean firing an unknown message at a live console (scenes,
meters) the profile raises instead.
"""

from __future__ import annotations

from osc_mcp.profiles.base import MixerProfile

ALLOWED_PREFIXES: tuple[str, ...] = (
    # Input strips
    "/ch/",
    "/aux/",
    "/fxr/",
    # Output strips
    "/bus/",
    "/mtx/",
    "/main/",
    "/dca/",
    # FX and config
    "/fx/",
    "/cfg/",
    "/io/",
    # Status / control / metering
    "/$stat/",
    "/$ctl/",
    "/?",
    "/*S",
    "/*N",
)

DENIED_PATHS: tuple[str, ...] = (
    # Network reconfiguration would drop the console off the LAN
    "/cfg/net",
    "/$stat/net",
    # Library/show wipes
    "/$ctl/lib/$actionclear",
    "/$ctl/lib/$actiondelete",
    # WING accepts a node-hash form (/#f50f69f8) that resolves to an arbitrary
    # parameter and would bypass the prefix allowlist entirely.
    "/#",
    "/node",
)

# WING fader range in dB: -144 is -inf, +10 is the top of the throw.
NEG_INF_DB = -144.0
MAX_DB = 10.0


class WingProfile(MixerProfile):
    """WING. Real-unit values, 1-digit indices, inverted mute."""

    family = "wing"
    model = "WING"
    port = 2223

    channels = 40
    buses = 16
    fx = 16
    dcas = 16
    matrices = 8
    aux_ins = 8
    mains = 4
    eq_bands = 6
    headamps = 40

    allowed_prefixes = ALLOWED_PREFIXES
    denied_paths = DENIED_PATHS

    verification_notes: tuple[str, ...] = (
        "Send, gain, phantom and EQ addresses are UNVERIFIED - confirm against "
        "WING Remote Protocols before trusting them on a live console.",
        "Scene recall and metering are not mapped yet; they raise rather than "
        "guess.",
        "WING permits a single OSC subscriber - the keepalive may displace "
        "another controller.",
    )

    # ------------------------------------------------------------------
    # Addresses
    # ------------------------------------------------------------------

    def _ch_idx(self, ch: int) -> str:
        return str(ch)

    def ch_fader(self, ch: int) -> str:
        return f"/ch/{ch}/fdr"

    def ch_mute(self, ch: int) -> str:
        return f"/ch/{ch}/mute"

    def ch_pan(self, ch: int) -> str:
        return f"/ch/{ch}/pan"

    def ch_name(self, ch: int) -> str:
        return f"/ch/{ch}/$name"

    def ch_send(self, ch: int, bus: int) -> str:
        # UNVERIFIED: destination may be a token ("BUS1") rather than an index.
        return f"/ch/{ch}/send/{bus}/lvl"

    def ch_eq_band(self, ch: int, band: int, param: str) -> str:
        return f"/ch/{ch}/eq/{band}/{param}"

    def ch_eq_on(self, ch: int) -> str:
        return f"/ch/{ch}/eq/on"

    def ch_gain(self, ch: int) -> str:
        # UNVERIFIED
        return f"/ch/{ch}/in/set/g"

    def ch_phantom(self, ch: int) -> str:
        # UNVERIFIED
        return f"/ch/{ch}/in/set/vph"

    def bus_fader(self, bus: int) -> str:
        return f"/bus/{bus}/fdr"

    def bus_mute(self, bus: int) -> str:
        return f"/bus/{bus}/mute"

    def bus_name(self, bus: int) -> str:
        return f"/bus/{bus}/$name"

    def main_fader(self, main: int = 1) -> str:
        return f"/main/{main}/fdr"

    def main_mute(self, main: int = 1) -> str:
        return f"/main/{main}/mute"

    def main_name(self, main: int = 1) -> str:
        return f"/main/{main}/$name"

    def dca_fader(self, dca: int) -> str:
        return f"/dca/{dca}/fdr"

    def dca_mute(self, dca: int) -> str:
        return f"/dca/{dca}/mute"

    def dca_name(self, dca: int) -> str:
        return f"/dca/{dca}/$name"

    def fx_send_fader(self, slot: int) -> str:
        return f"/fx/{slot}/fdr"

    def fx_send_mute(self, slot: int) -> str:
        return f"/fx/{slot}/mute"

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def identify_address(self) -> str:
        return "/?"

    def parse_identity(self, args: list) -> dict[str, str]:
        strings = [a for a in args if isinstance(a, str)]
        return {
            "raw": ", ".join(str(a) for a in args),
            "model": strings[0] if strings else "WING",
            "firmware": strings[1] if len(strings) > 1 else "",
        }

    def keepalive(self) -> tuple[str, list, float]:
        # UNVERIFIED renewal token. WING allows one subscriber at a time.
        return ("/*S", [], 5.0)

    def meters_subscribe(self, index: int) -> None:
        return None

    rta_meter_index = None

    def scene_recall(self, number: int) -> tuple[str, list]:
        raise NotImplementedError(
            "Scene recall is not mapped for WING yet. Confirm the address in "
            "WING Remote Protocols and add it to WingProfile.scene_recall; "
            "until then use send_raw_osc explicitly."
        )

    def scene_name(self, number: int) -> str:
        raise NotImplementedError(
            "Scene names are not mapped for WING yet."
        )

    # ------------------------------------------------------------------
    # Encoding -- real units, inverted mute
    # ------------------------------------------------------------------

    def encode_mute(self, muted: bool) -> int:
        """WING is the opposite of X-Air: 1 means MUTED."""
        return 1 if muted else 0

    def decode_mute(self, raw: float | int) -> bool:
        return bool(raw)

    def db_to_raw(self, db: float) -> float:
        return min(MAX_DB, max(NEG_INF_DB, db))

    def raw_to_db(self, raw: float) -> float:
        return min(MAX_DB, max(NEG_INF_DB, raw))

    def eq_freq_to_raw(self, hz: float) -> float:
        return hz

    def eq_gain_to_raw(self, db: float) -> float:
        return db

    def eq_q_to_raw(self, q: float) -> float:
        return q

    def gain_to_raw(self, db: float) -> float:
        return db

    def raw_to_gain(self, raw: float) -> float:
        return raw

    def pan_to_raw(self, pan: float) -> float:
        return min(100.0, max(-100.0, pan))

    def raw_to_pan(self, raw: float) -> float:
        return min(100.0, max(-100.0, raw))

    def capabilities(self) -> dict[str, int | str]:
        caps = super().capabilities()
        caps["mains"] = self.mains
        return caps


class WingCompactProfile(WingProfile):
    model = "WING COMPACT"


class WingRackProfile(WingProfile):
    model = "WING RACK"
