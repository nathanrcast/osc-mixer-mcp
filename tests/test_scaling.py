"""Tests for value scaling: dB taper, EQ normalization, gain, pan."""

import pytest

from osc_mcp import scaling


class TestDbConversion:
    def test_zero_db(self):
        assert scaling.db_to_fader(0.0) == pytest.approx(0.75)

    def test_neg_inf(self):
        assert scaling.db_to_fader(-90.0) == 0.0
        assert scaling.db_to_fader(-100.0) == 0.0

    def test_plus_10(self):
        assert scaling.db_to_fader(10.0) == 1.0
        assert scaling.db_to_fader(15.0) == 1.0

    def test_neg_30(self):
        assert scaling.db_to_fader(-30.0) == pytest.approx(0.25)

    def test_neg_10(self):
        assert scaling.db_to_fader(-10.0) == pytest.approx(0.5)

    def test_fader_to_db_zero(self):
        assert scaling.fader_to_db(0.75) == pytest.approx(0.0)

    def test_fader_to_db_neg_inf(self):
        assert scaling.fader_to_db(0.0) == -90.0

    def test_fader_to_db_plus_10(self):
        assert scaling.fader_to_db(1.0) == pytest.approx(10.0)

    def test_round_trip(self):
        for db in [-60.0, -30.0, -20.0, -10.0, -5.0, 0.0, 5.0, 10.0]:
            fader = scaling.db_to_fader(db)
            assert scaling.fader_to_db(fader) == pytest.approx(db, abs=0.01)


class TestEqFrequency:
    """The regression guard for the raw-Hz bug: 1 kHz must not be sent as 1000.0."""

    def test_bounds(self):
        assert scaling.eq_freq_to_raw(20.0) == 0.0
        assert scaling.eq_freq_to_raw(20000.0) == 1.0

    def test_clamps_outside_range(self):
        assert scaling.eq_freq_to_raw(5.0) == 0.0
        assert scaling.eq_freq_to_raw(30000.0) == 1.0

    def test_midpoint_is_geometric_mean(self):
        # 0.5 normalized sits at sqrt(20 * 20000) = 632.5 Hz, not 10 kHz.
        assert scaling.raw_to_eq_freq(0.5) == pytest.approx(632.46, abs=0.1)

    def test_one_khz_is_normalized(self):
        raw = scaling.eq_freq_to_raw(1000.0)
        assert 0.0 < raw < 1.0
        assert raw == pytest.approx(0.5663, abs=0.001)

    def test_round_trip(self):
        for hz in [20.0, 100.0, 440.0, 1000.0, 5000.0, 20000.0]:
            raw = scaling.eq_freq_to_raw(hz)
            assert scaling.raw_to_eq_freq(raw) == pytest.approx(hz, rel=0.001)


class TestEqGain:
    def test_bounds(self):
        assert scaling.eq_gain_to_raw(-15.0) == 0.0
        assert scaling.eq_gain_to_raw(15.0) == 1.0

    def test_zero_is_centre(self):
        assert scaling.eq_gain_to_raw(0.0) == pytest.approx(0.5)

    def test_plus_three(self):
        assert scaling.eq_gain_to_raw(3.0) == pytest.approx(0.6)

    def test_clamps(self):
        assert scaling.eq_gain_to_raw(-40.0) == 0.0
        assert scaling.eq_gain_to_raw(40.0) == 1.0

    def test_round_trip(self):
        for db in [-15.0, -6.0, 0.0, 3.0, 15.0]:
            assert scaling.raw_to_eq_gain(scaling.eq_gain_to_raw(db)) == pytest.approx(
                db, abs=0.01
            )


class TestEqQ:
    def test_inverted_bounds(self):
        """Q runs high-to-low: Q 10 is 0.0 and Q 0.3 is 1.0."""
        assert scaling.eq_q_to_raw(10.0) == 0.0
        assert scaling.eq_q_to_raw(0.3) == 1.0

    def test_monotonically_increases_as_q_falls(self):
        assert scaling.eq_q_to_raw(5.0) < scaling.eq_q_to_raw(1.0)

    def test_round_trip(self):
        for q in [10.0, 5.0, 2.0, 1.0, 0.5, 0.3]:
            assert scaling.raw_to_eq_q(scaling.eq_q_to_raw(q)) == pytest.approx(
                q, rel=0.001
            )


class TestGain:
    def test_bounds(self):
        assert scaling.gain_db_to_raw(-12.0) == 0.0
        assert scaling.gain_db_to_raw(60.0) == 1.0

    def test_midpoint(self):
        assert scaling.gain_db_to_raw(24.0) == pytest.approx(0.5)

    def test_round_trip(self):
        for db in [-12.0, 0.0, 20.0, 45.0, 60.0]:
            assert scaling.raw_to_gain_db(scaling.gain_db_to_raw(db)) == pytest.approx(
                db, abs=0.01
            )


class TestPan:
    def test_bounds(self):
        assert scaling.pan_to_raw(-100.0) == 0.0
        assert scaling.pan_to_raw(100.0) == 1.0

    def test_centre(self):
        assert scaling.pan_to_raw(0.0) == pytest.approx(0.5)

    def test_round_trip(self):
        for pan in [-100.0, -40.0, 0.0, 25.0, 100.0]:
            assert scaling.raw_to_pan(scaling.pan_to_raw(pan)) == pytest.approx(
                pan, abs=0.01
            )
