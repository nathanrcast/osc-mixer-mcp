"""Tests for xair module: NameRegistry, address builders, dB conversion."""

import pytest

from osc_mcp.xair import (
    NameRegistry,
    ch_fader,
    ch_mute,
    ch_send_level,
    ch_eq_band,
    ch_eq_on,
    ch_config_name,
    bus_fader,
    bus_mute,
    bus_config_name,
    main_fader,
    main_mute,
    fx_send_fader,
    fx_send_mute,
    db_to_fader,
    fader_to_db,
    validate_channel,
    validate_bus,
    validate_fx_slot,
    validate_eq_band,
)


# ---------------------------------------------------------------------------
# NameRegistry
# ---------------------------------------------------------------------------


class TestNameRegistry:
    def test_assign_and_resolve_by_name(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        assert reg.resolve("channel", "Kick") == 1

    def test_resolve_by_number_int(self):
        reg = NameRegistry()
        assert reg.resolve("channel", 5) == 5

    def test_resolve_by_number_string(self):
        reg = NameRegistry()
        assert reg.resolve("channel", "5") == 5

    def test_case_insensitive_lookup(self):
        reg = NameRegistry()
        reg.assign_name("bus", 2, "Drummer")
        assert reg.resolve("bus", "drummer") == 2
        assert reg.resolve("bus", "DRUMMER") == 2

    def test_duplicate_name_error(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        with pytest.raises(ValueError, match="already assigned"):
            reg.assign_name("channel", 2, "Kick")

    def test_reassign_same_number(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        reg.assign_name("channel", 1, "BassDrum")
        assert reg.resolve("channel", "BassDrum") == 1
        with pytest.raises(ValueError):
            reg.resolve("channel", "Kick")

    def test_unknown_name_error(self):
        reg = NameRegistry()
        with pytest.raises(ValueError, match="Unknown channel name"):
            reg.resolve("channel", "NonExistent")

    def test_list_names(self):
        reg = NameRegistry()
        reg.assign_name("channel", 1, "Kick")
        reg.assign_name("channel", 3, "Snare")
        names = reg.list_names("channel")
        assert names == {1: "Kick", 3: "Snare"}

    def test_list_names_empty(self):
        reg = NameRegistry()
        assert reg.list_names("bus") == {}

    def test_invalid_kind(self):
        reg = NameRegistry()
        with pytest.raises(ValueError, match="Kind must be"):
            reg.assign_name("fx", 1, "Reverb")


# ---------------------------------------------------------------------------
# Address builders
# ---------------------------------------------------------------------------


class TestAddressBuilders:
    def test_ch_fader(self):
        assert ch_fader(1) == "/ch/01/mix/fader"
        assert ch_fader(18) == "/ch/18/mix/fader"

    def test_ch_mute(self):
        assert ch_mute(1) == "/ch/01/mix/on"

    def test_ch_send_level(self):
        assert ch_send_level(1, 2) == "/ch/01/mix/02/level"
        assert ch_send_level(12, 6) == "/ch/12/mix/06/level"

    def test_ch_eq_band(self):
        assert ch_eq_band(1, 1, "f") == "/ch/01/eq/1/f"
        assert ch_eq_band(5, 3, "g") == "/ch/05/eq/3/g"
        assert ch_eq_band(1, 2, "q") == "/ch/01/eq/2/q"

    def test_ch_eq_on(self):
        assert ch_eq_on(1) == "/ch/01/eq/on"

    def test_bus_fader(self):
        assert bus_fader(1) == "/bus/1/mix/fader"
        assert bus_fader(6) == "/bus/6/mix/fader"

    def test_bus_mute(self):
        assert bus_mute(3) == "/bus/3/mix/on"

    def test_main_fader(self):
        assert main_fader() == "/lr/0/mix/fader"

    def test_main_mute(self):
        assert main_mute() == "/lr/0/mix/on"

    def test_fx_send_fader(self):
        assert fx_send_fader(1) == "/fxsend/1/mix/fader"
        assert fx_send_fader(4) == "/fxsend/4/mix/fader"

    def test_fx_send_mute(self):
        assert fx_send_mute(2) == "/fxsend/2/mix/on"

    def test_ch_config_name(self):
        assert ch_config_name(1) == "/ch/01/config/name"
        assert ch_config_name(18) == "/ch/18/config/name"

    def test_bus_config_name(self):
        assert bus_config_name(1) == "/bus/1/config/name"
        assert bus_config_name(6) == "/bus/6/config/name"


# ---------------------------------------------------------------------------
# dB conversion
# ---------------------------------------------------------------------------


class TestDbConversion:
    def test_zero_db(self):
        assert db_to_fader(0.0) == pytest.approx(0.75)

    def test_neg_inf(self):
        assert db_to_fader(-90.0) == 0.0
        assert db_to_fader(-100.0) == 0.0

    def test_plus_10(self):
        assert db_to_fader(10.0) == 1.0
        assert db_to_fader(15.0) == 1.0

    def test_neg_30(self):
        assert db_to_fader(-30.0) == pytest.approx(0.25)

    def test_neg_10(self):
        assert db_to_fader(-10.0) == pytest.approx(0.5)

    def test_fader_to_db_zero(self):
        assert fader_to_db(0.75) == pytest.approx(0.0)

    def test_fader_to_db_neg_inf(self):
        assert fader_to_db(0.0) == -90.0

    def test_fader_to_db_plus_10(self):
        assert fader_to_db(1.0) == pytest.approx(10.0)

    def test_round_trip(self):
        for db in [-60.0, -30.0, -20.0, -10.0, -5.0, 0.0, 5.0, 10.0]:
            fader = db_to_fader(db)
            result = fader_to_db(fader)
            assert result == pytest.approx(db, abs=0.01)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_channel(self):
        validate_channel(1)
        validate_channel(18)

    def test_invalid_channel(self):
        with pytest.raises(ValueError):
            validate_channel(0)
        with pytest.raises(ValueError):
            validate_channel(19)

    def test_valid_bus(self):
        validate_bus(1)
        validate_bus(6)

    def test_invalid_bus(self):
        with pytest.raises(ValueError):
            validate_bus(0)
        with pytest.raises(ValueError):
            validate_bus(7)

    def test_valid_fx_slot(self):
        validate_fx_slot(1)
        validate_fx_slot(4)

    def test_invalid_fx_slot(self):
        with pytest.raises(ValueError):
            validate_fx_slot(0)
        with pytest.raises(ValueError):
            validate_fx_slot(5)

    def test_valid_eq_band(self):
        validate_eq_band(1)
        validate_eq_band(4)

    def test_invalid_eq_band(self):
        with pytest.raises(ValueError):
            validate_eq_band(0)
        with pytest.raises(ValueError):
            validate_eq_band(5)
