"""The MixerProfile contract.

A profile owns everything that differs between console families: capability
counts, OSC address shapes, value encoding, the identify/keepalive handshake,
and the raw-OSC security lists. Everything else in the server is model-agnostic.
"""

from __future__ import annotations

from osc_mcp import scaling


class MixerProfile:
    """Base profile. Defaults follow the X-Air convention; subclasses override."""

    model: str = "unknown"
    family: str = "unknown"
    port: int = 10024

    # Capability counts
    channels: int = 0
    buses: int = 0
    fx: int = 0
    dcas: int = 0
    matrices: int = 0
    aux_ins: int = 0
    eq_bands: int = 0
    headamps: int = 0

    # Raw-OSC gating
    allowed_prefixes: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Index formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _pad(n: int) -> str:
        return f"{n:02d}"

    def _ch_idx(self, ch: int) -> str:
        return self._pad(ch)

    def _bus_idx(self, bus: int) -> str:
        return str(bus)

    # ------------------------------------------------------------------
    # Channel addresses
    # ------------------------------------------------------------------

    def ch_fader(self, ch: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/mix/fader"

    def ch_mute(self, ch: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/mix/on"

    def ch_pan(self, ch: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/mix/pan"

    def ch_name(self, ch: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/config/name"

    def ch_send(self, ch: int, bus: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/mix/{self._pad(bus)}/level"

    def ch_eq_band(self, ch: int, band: int, param: str) -> str:
        return f"/ch/{self._ch_idx(ch)}/eq/{band}/{param}"

    def ch_eq_on(self, ch: int) -> str:
        return f"/ch/{self._ch_idx(ch)}/eq/on"

    def ch_gain(self, ch: int) -> str:
        """Preamp gain. X32/M32 head amps are 0-indexed, one below the channel.

        X-Air is the exception and overrides this — see XAirProfile.
        """
        return f"/headamp/{self._pad(ch - 1)}/gain"

    def ch_phantom(self, ch: int) -> str:
        return f"/headamp/{self._pad(ch - 1)}/phantom"

    # ------------------------------------------------------------------
    # Bus / main / DCA / FX addresses
    # ------------------------------------------------------------------

    def bus_fader(self, bus: int) -> str:
        return f"/bus/{self._bus_idx(bus)}/mix/fader"

    def bus_mute(self, bus: int) -> str:
        return f"/bus/{self._bus_idx(bus)}/mix/on"

    def bus_name(self, bus: int) -> str:
        return f"/bus/{self._bus_idx(bus)}/config/name"

    def main_fader(self) -> str:
        raise NotImplementedError

    def main_mute(self) -> str:
        raise NotImplementedError

    def dca_fader(self, dca: int) -> str:
        return f"/dca/{dca}/fader"

    def dca_mute(self, dca: int) -> str:
        return f"/dca/{dca}/on"

    def dca_name(self, dca: int) -> str:
        return f"/dca/{dca}/config/name"

    def fx_send_fader(self, slot: int) -> str:
        return f"/fxsend/{slot}/mix/fader"

    def fx_send_mute(self, slot: int) -> str:
        return f"/fxsend/{slot}/mix/on"

    # ------------------------------------------------------------------
    # Protocol handshake
    # ------------------------------------------------------------------

    def identify_address(self) -> str:
        """Address that returns the model/firmware identity."""
        raise NotImplementedError

    def parse_identity(self, args: list) -> dict[str, str]:
        """Pull a readable identity out of the identify reply."""
        strings = [a for a in args if isinstance(a, str)]
        return {
            "raw": ", ".join(str(a) for a in args),
            "model": strings[2] if len(strings) > 2 else "",
            "firmware": strings[3] if len(strings) > 3 else "",
        }

    def keepalive(self) -> tuple[str, list, float] | None:
        """(address, args, renew_interval_seconds) or None if not applicable."""
        return None

    def meters_subscribe(self, index: int) -> tuple[str, list] | None:
        """Subscription message for meter stream `index`, or None if unsupported."""
        return None

    rta_meter_index: int | None = None
    rta_bands: int = 100

    def scene_recall(self, number: int) -> tuple[str, list]:
        raise NotImplementedError

    def scene_name(self, number: int) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Value encoding
    # ------------------------------------------------------------------

    def encode_mute(self, muted: bool) -> int:
        """X-Air/X32 use `mix/on`: 1 means unmuted."""
        return 0 if muted else 1

    def decode_mute(self, raw: float | int) -> bool:
        return not bool(raw)

    def encode_on(self, enabled: bool) -> int:
        """Plain on/off switches (EQ on, phantom) are NOT inverted."""
        return 1 if enabled else 0

    def db_to_raw(self, db: float) -> float:
        return scaling.db_to_fader(db)

    def raw_to_db(self, raw: float) -> float:
        return scaling.fader_to_db(raw)

    def eq_freq_to_raw(self, hz: float) -> float:
        return scaling.eq_freq_to_raw(hz)

    def eq_gain_to_raw(self, db: float) -> float:
        return scaling.eq_gain_to_raw(db)

    def eq_q_to_raw(self, q: float) -> float:
        return scaling.eq_q_to_raw(q)

    def gain_to_raw(self, db: float) -> float:
        return scaling.gain_db_to_raw(db)

    def raw_to_gain(self, raw: float) -> float:
        return scaling.raw_to_gain_db(raw)

    def pan_to_raw(self, pan: float) -> float:
        return scaling.pan_to_raw(pan)

    def raw_to_pan(self, raw: float) -> float:
        return scaling.raw_to_pan(raw)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, label: str, value: int, limit: int) -> None:
        if limit == 0:
            raise ValueError(f"{self.model} has no {label}s")
        if not 1 <= value <= limit:
            raise ValueError(f"{label} must be 1-{limit} on {self.model}, got {value}")

    def validate_channel(self, ch: int) -> None:
        self._validate("Channel", ch, self.channels)

    def validate_bus(self, bus: int) -> None:
        self._validate("Bus", bus, self.buses)

    def validate_fx_slot(self, slot: int) -> None:
        self._validate("FX slot", slot, self.fx)

    def validate_dca(self, dca: int) -> None:
        self._validate("DCA", dca, self.dcas)

    def validate_eq_band(self, band: int) -> None:
        self._validate("EQ band", band, self.eq_bands)

    def validate_headamp(self, ch: int) -> None:
        self._validate("Head amp channel", ch, self.headamps)

    # ------------------------------------------------------------------

    def capabilities(self) -> dict[str, int | str]:
        return {
            "model": self.model,
            "family": self.family,
            "port": self.port,
            "channels": self.channels,
            "buses": self.buses,
            "fx": self.fx,
            "dcas": self.dcas,
            "matrices": self.matrices,
            "aux_ins": self.aux_ins,
            "eq_bands": self.eq_bands,
            "headamps": self.headamps,
        }

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.model} port={self.port}>"
