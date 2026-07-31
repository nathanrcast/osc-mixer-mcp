"""Per-model address matrix, encoding and detection.

The EXPECTED table below is the executable spec for the protocol differences
between the three console families. Anything the hardware smoke test disproves
should be corrected here first.
"""

import pytest

from osc_mcp import profiles
from osc_mcp.profiles import PROFILES

XR18 = PROFILES["XR18"]
X32 = PROFILES["X32"]
WING = PROFILES["WING"]

# method name -> args -> {model: expected address}
EXPECTED: list[tuple[str, tuple, dict[str, str]]] = [
    ("ch_fader", (1,), {
        "XR18": "/ch/01/mix/fader",
        "X32": "/ch/01/mix/fader",
        "WING": "/ch/1/fdr",
    }),
    ("ch_fader", (12,), {
        "XR18": "/ch/12/mix/fader",
        "X32": "/ch/12/mix/fader",
        "WING": "/ch/12/fdr",
    }),
    ("ch_mute", (1,), {
        "XR18": "/ch/01/mix/on",
        "X32": "/ch/01/mix/on",
        "WING": "/ch/1/mute",
    }),
    ("ch_name", (1,), {
        "XR18": "/ch/01/config/name",
        "X32": "/ch/01/config/name",
        "WING": "/ch/1/$name",
    }),
    ("ch_pan", (1,), {
        "XR18": "/ch/01/mix/pan",
        "X32": "/ch/01/mix/pan",
        "WING": "/ch/1/pan",
    }),
    ("ch_send", (1, 2), {
        "XR18": "/ch/01/mix/02/level",
        "X32": "/ch/01/mix/02/level",
        "WING": "/ch/1/send/2/lvl",
    }),
    ("ch_eq_band", (5, 3, "g"), {
        "XR18": "/ch/05/eq/3/g",
        "X32": "/ch/05/eq/3/g",
        "WING": "/ch/5/eq/3/g",
    }),
    ("ch_eq_on", (1,), {
        "XR18": "/ch/01/eq/on",
        "X32": "/ch/01/eq/on",
        "WING": "/ch/1/eq/on",
    }),
    ("ch_gain", (1,), {
        "XR18": "/headamp/00/gain",
        "X32": "/headamp/000/gain",
        "WING": "/ch/1/in/set/g",
    }),
    ("ch_phantom", (16,), {
        "XR18": "/headamp/15/phantom",
        "X32": "/headamp/015/phantom",
        "WING": "/ch/16/in/set/vph",
    }),
    # The padding split: X-Air buses are 1-digit, X32 buses are 2-digit.
    ("bus_fader", (1,), {
        "XR18": "/bus/1/mix/fader",
        "X32": "/bus/01/mix/fader",
        "WING": "/bus/1/fdr",
    }),
    ("bus_mute", (3,), {
        "XR18": "/bus/3/mix/on",
        "X32": "/bus/03/mix/on",
        "WING": "/bus/3/mute",
    }),
    ("bus_name", (1,), {
        "XR18": "/bus/1/config/name",
        "X32": "/bus/01/config/name",
        "WING": "/bus/1/$name",
    }),
    # Main is named differently on all three.
    ("main_fader", (), {
        "XR18": "/lr/mix/fader",
        "X32": "/main/st/mix/fader",
        "WING": "/main/1/fdr",
    }),
    ("main_mute", (), {
        "XR18": "/lr/mix/on",
        "X32": "/main/st/mix/on",
        "WING": "/main/1/mute",
    }),
    ("dca_fader", (1,), {
        "XR18": "/dca/1/fader",
        "X32": "/dca/1/fader",
        "WING": "/dca/1/fdr",
    }),
    ("dca_mute", (1,), {
        "XR18": "/dca/1/on",
        "X32": "/dca/1/on",
        "WING": "/dca/1/mute",
    }),
    ("fx_send_fader", (1,), {
        "XR18": "/fxsend/1/mix/fader",
        "X32": "/fxsend/1/mix/fader",
        "WING": "/fx/1/fdr",
    }),
    ("identify_address", (), {
        "XR18": "/xinfo",
        "X32": "/info",
        "WING": "/?",
    }),
]


@pytest.mark.parametrize("method,args,expected", EXPECTED)
@pytest.mark.parametrize("model", ["XR18", "X32", "WING"])
def test_address_matrix(model, method, args, expected):
    profile = PROFILES[model]
    assert getattr(profile, method)(*args) == expected[model]


class TestPorts:
    def test_ports_differ_per_family(self):
        assert XR18.port == 10024
        assert X32.port == 10023
        assert WING.port == 2223


class TestMutePolarity:
    """The bug class that would silently unmute a live console."""

    def test_xair_mix_on_is_inverted(self):
        assert XR18.encode_mute(True) == 0
        assert XR18.encode_mute(False) == 1

    def test_x32_matches_xair(self):
        assert X32.encode_mute(True) == 0
        assert X32.encode_mute(False) == 1

    def test_wing_is_the_opposite(self):
        assert WING.encode_mute(True) == 1
        assert WING.encode_mute(False) == 0

    @pytest.mark.parametrize("model", ["XR18", "X32", "WING"])
    def test_decode_round_trips(self, model):
        profile = PROFILES[model]
        for muted in (True, False):
            assert profile.decode_mute(profile.encode_mute(muted)) is muted

    @pytest.mark.parametrize("model", ["XR18", "X32", "WING"])
    def test_plain_switches_are_not_inverted(self, model):
        """EQ on / phantom use a straight 1 = on, unlike mix/on."""
        assert PROFILES[model].encode_on(True) == 1
        assert PROFILES[model].encode_on(False) == 0


class TestFaderEncoding:
    def test_xair_and_x32_use_the_normalized_taper(self):
        assert XR18.db_to_raw(0.0) == pytest.approx(0.75)
        assert X32.db_to_raw(0.0) == pytest.approx(0.75)

    def test_wing_takes_real_db(self):
        assert WING.db_to_raw(-10.0) == -10.0
        assert WING.raw_to_db(-10.0) == -10.0

    def test_wing_clamps_to_its_range(self):
        assert WING.db_to_raw(-200.0) == -144.0
        assert WING.db_to_raw(20.0) == 10.0

    @pytest.mark.parametrize("model", ["XR18", "X32", "WING"])
    def test_db_round_trip(self, model):
        profile = PROFILES[model]
        for db in [-30.0, -10.0, -6.0, 0.0]:
            assert profile.raw_to_db(profile.db_to_raw(db)) == pytest.approx(
                db, abs=0.01
            )

    def test_wing_eq_takes_real_units(self):
        assert WING.eq_freq_to_raw(1000.0) == 1000.0
        assert WING.eq_gain_to_raw(3.0) == 3.0
        assert WING.eq_q_to_raw(2.0) == 2.0

    def test_xair_eq_is_normalized(self):
        assert 0.0 < XR18.eq_freq_to_raw(1000.0) < 1.0
        assert XR18.eq_gain_to_raw(3.0) == pytest.approx(0.6)


class TestCapabilities:
    def test_xr18_counts(self):
        # X-Air addresses /ch/01../ch/16 only; the aux in is /rtn/aux.
        assert XR18.channels == 16
        assert XR18.buses == 6
        assert XR18.fx == 4
        assert XR18.dcas == 4
        assert XR18.eq_bands == 4

    def test_x32_counts(self):
        assert X32.channels == 32
        assert X32.buses == 16
        assert X32.fx == 8
        assert X32.dcas == 8
        assert X32.matrices == 6

    def test_wing_counts(self):
        assert WING.channels == 40
        assert WING.buses == 16
        assert WING.dcas == 16
        assert WING.eq_bands == 6

    def test_capabilities_dict_reports_model(self):
        assert XR18.capabilities()["model"] == "XR18"
        assert WING.capabilities()["mains"] == 4


class TestValidation:
    def test_channel_bounds_follow_the_model(self):
        XR18.validate_channel(16)
        with pytest.raises(ValueError, match="1-16"):
            XR18.validate_channel(17)
        X32.validate_channel(17)
        with pytest.raises(ValueError, match="1-32"):
            X32.validate_channel(33)

    def test_bus_bounds(self):
        with pytest.raises(ValueError, match="1-6"):
            XR18.validate_bus(7)
        X32.validate_bus(16)

    def test_zero_and_negative_rejected(self):
        for profile in (XR18, X32, WING):
            with pytest.raises(ValueError):
                profile.validate_channel(0)
            with pytest.raises(ValueError):
                profile.validate_channel(-1)

    def test_error_names_the_model(self):
        with pytest.raises(ValueError, match="XR18"):
            XR18.validate_channel(99)

    def test_missing_capability_reports_clearly(self):
        """XR18 has no matrices, so asking for one should say so."""
        assert XR18.matrices == 0
        with pytest.raises(ValueError, match="has no Matrix"):
            XR18._validate("Matrix", 1, XR18.matrices)


class TestWingGuardrails:
    """WING paths we could not verify must refuse rather than guess."""

    def test_scene_recall_raises(self):
        with pytest.raises(NotImplementedError, match="not mapped for WING"):
            WING.scene_recall(1)

    def test_meters_unsupported(self):
        assert WING.meters_subscribe(4) is None
        assert WING.rta_meter_index is None

    def test_verification_notes_present(self):
        assert WING.verification_notes
        assert not getattr(XR18, "verification_notes", ())


class TestSecurityLists:
    @pytest.mark.parametrize("model", ["XR18", "X32", "WING"])
    def test_node_passthrough_denied_everywhere(self, model):
        assert "/node" in PROFILES[model].denied_paths

    def test_wing_hash_form_denied(self):
        """WING's /#f50f69f8 node-hash form would bypass the prefix allowlist."""
        assert "/#" in WING.denied_paths

    def test_wing_namespaces_allowed(self):
        """The X-Air allowlist would have blocked every one of these."""
        assert "/$ctl/lib/foo".startswith(WING.allowed_prefixes)
        assert "/$stat/solo".startswith(WING.allowed_prefixes)
        assert "/cfg/mute".startswith(WING.allowed_prefixes)
        assert not "/$ctl/lib/foo".startswith(XR18.allowed_prefixes)

    def test_xair_namespaces_not_granted_to_wing(self):
        assert not "/-snap/load".startswith(WING.allowed_prefixes)

    def test_xair_allows_its_own_show_paths(self):
        assert "/-snap/load".startswith(XR18.allowed_prefixes)

    def test_network_reconfig_denied(self):
        assert "/-prefs/ip/addr".startswith(XR18.denied_paths)
        assert "/cfg/net/ip".startswith(WING.denied_paths)


class TestScenes:
    def test_xair_uses_snapshots(self):
        assert XR18.scene_recall(3) == ("/-snap/load", [3])

    def test_x32_uses_the_show_file(self):
        assert X32.scene_recall(3) == ("/-action/goscene", [3])
        assert X32.scene_name(3) == "/-show/showfile/scene/003/name"


class TestKeepalive:
    def test_xair_and_x32_renew_xremote_inside_10s(self):
        for profile in (XR18, X32):
            address, args, interval = profile.keepalive()
            assert address == "/xremote"
            assert args == []
            assert interval < 10.0

    def test_wing_has_a_keepalive(self):
        assert WING.keepalive() is not None


class TestModelLookup:
    @pytest.mark.parametrize(
        "identity,expected",
        [
            ("192.168.1.50 XR18-4C-D9 XR18 1.17", "XR18"),
            ("192.168.1.60 mixer X32 4.06", "X32"),
            ("X32 RACK 4.06", "X32 RACK"),
            ("X32 COMPACT 4.06", "X32 COMPACT"),
            ("M32 4.06", "M32"),
            ("WING 3.0.6", "WING"),
            ("WING RACK 3.0.6", "WING RACK"),
            ("XR16 1.17", "XR16"),
        ],
    )
    def test_for_model(self, identity, expected):
        profile = profiles.for_model(identity)
        assert profile is not None
        assert profile.model == expected

    def test_longest_match_wins(self):
        """'X32 RACK' must not be swallowed by the 'X32' entry."""
        assert profiles.for_model("X32 RACK").model == "X32 RACK"
        assert profiles.for_model("WING COMPACT").model == "WING COMPACT"

    def test_unknown_model(self):
        assert profiles.for_model("SomeOtherDesk 1.0") is None

    def test_family_default(self):
        assert profiles.family_default(10024).family == "x-air"
        assert profiles.family_default(10023).family == "x32"
        assert profiles.family_default(2223).family == "wing"
        assert profiles.family_default(9999) is None


class TestDetect:
    def test_detects_xair_first(self):
        def probe(port, address):
            if port == 10024 and address == "/xinfo":
                return ["192.168.1.50", "XR18-4C-D9", "XR18", "1.17"]
            return None

        profile, identity = profiles.detect(probe)
        assert profile.model == "XR18"
        assert profile.port == 10024
        assert identity[2] == "XR18"

    def test_falls_through_to_x32(self):
        calls = []

        def probe(port, address):
            calls.append(port)
            if port == 10023:
                return ["mixer", "X32", "4.06"]
            return None

        profile, _ = profiles.detect(probe)
        assert profile.model == "X32"
        assert calls[0] == 10024  # X-Air probed first

    def test_falls_through_to_wing(self):
        def probe(port, address):
            return ["WING", "3.0.6"] if port == 2223 else None

        profile, _ = profiles.detect(probe)
        assert profile.family == "wing"
        assert profile.port == 2223

    def test_unknown_model_on_known_port_uses_family_default(self):
        def probe(port, address):
            return ["something", "unrecognised"] if port == 10023 else None

        profile, _ = profiles.detect(probe)
        assert profile.family == "x32"

    def test_nothing_answers(self):
        assert profiles.detect(lambda port, address: None) is None
