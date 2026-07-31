"""Tests for meter blob decoding and RTA accumulation."""

import struct

import pytest

from osc_mcp import meters


def make_blob(values_db: list[float]) -> bytes:
    """Encode dBFS values the way the console does: int32 count + int16 * 256."""
    raw = [int(round(v * 256)) for v in values_db]
    return struct.pack("<i", len(raw)) + struct.pack(f"<{len(raw)}h", *raw)


class TestDecodeMeterBlob:
    def test_decodes_values(self):
        assert meters.decode_meter_blob(make_blob([-6.0, -12.0, 0.0])) == [
            pytest.approx(-6.0),
            pytest.approx(-12.0),
            pytest.approx(0.0),
        ]

    def test_clamps_to_floor(self):
        assert meters.decode_meter_blob(make_blob([-120.0])) == [-80.0]

    def test_clamps_to_ceiling(self):
        assert meters.decode_meter_blob(make_blob([12.0])) == [0.0]

    def test_empty_blob(self):
        assert meters.decode_meter_blob(b"") == []

    def test_truncated_header(self):
        assert meters.decode_meter_blob(b"\x02\x00") == []

    def test_zero_count(self):
        assert meters.decode_meter_blob(struct.pack("<i", 0)) == []

    def test_negative_count(self):
        assert meters.decode_meter_blob(struct.pack("<i", -5)) == []

    def test_count_larger_than_payload_is_truncated(self):
        """A lying header must not read past the buffer."""
        blob = struct.pack("<i", 100) + struct.pack("<2h", -1536, -3072)
        assert meters.decode_meter_blob(blob) == [
            pytest.approx(-6.0),
            pytest.approx(-12.0),
        ]

    def test_count_with_no_payload(self):
        assert meters.decode_meter_blob(struct.pack("<i", 4)) == []


class TestRtaBandFrequencies:
    def test_spans_the_audio_band(self):
        freqs = meters.rta_band_frequencies(100)
        assert len(freqs) == 100
        assert freqs[0] == pytest.approx(20.0)
        assert freqs[-1] == pytest.approx(20000.0)

    def test_is_monotonic(self):
        freqs = meters.rta_band_frequencies(100)
        assert all(b > a for a, b in zip(freqs, freqs[1:]))

    def test_is_log_spaced(self):
        freqs = meters.rta_band_frequencies(100)
        ratios = [b / a for a, b in zip(freqs, freqs[1:])]
        assert max(ratios) == pytest.approx(min(ratios), rel=1e-6)

    def test_single_band(self):
        assert meters.rta_band_frequencies(1) == [20.0]


class TestRtaAccumulator:
    def test_averages_frames(self):
        acc = meters.RtaAccumulator(bands=3)
        acc.add([-10.0, -20.0, -30.0])
        acc.add([-20.0, -30.0, -40.0])
        assert [db for _, db in acc.average()] == [-15.0, -25.0, -35.0]

    def test_reports_frame_count(self):
        acc = meters.RtaAccumulator(bands=2)
        acc.add([-1.0, -2.0])
        acc.add([-3.0, -4.0])
        assert acc.frames == 2

    def test_empty_average(self):
        assert meters.RtaAccumulator(bands=4).average() == []
        assert meters.RtaAccumulator(bands=4).frames == 0

    def test_short_frames_ignored(self):
        acc = meters.RtaAccumulator(bands=4)
        acc.add([-1.0, -2.0])
        assert acc.frames == 0

    def test_longer_frames_truncated(self):
        acc = meters.RtaAccumulator(bands=2)
        acc.add([-10.0, -20.0, -30.0, -40.0])
        assert [db for _, db in acc.average()] == [-10.0, -20.0]

    def test_pairs_frequency_with_level(self):
        acc = meters.RtaAccumulator(bands=100)
        acc.add([-30.0] * 100)
        spectrum = acc.average()
        assert len(spectrum) == 100
        assert spectrum[0][0] == pytest.approx(20.0)
        assert spectrum[-1][0] == pytest.approx(20000.0)
        assert all(db == -30.0 for _, db in spectrum)

    def test_end_to_end_from_blob(self):
        acc = meters.RtaAccumulator(bands=3)
        acc.add(meters.decode_meter_blob(make_blob([-6.0, -12.0, -18.0])))
        assert [db for _, db in acc.average()] == [-6.0, -12.0, -18.0]
