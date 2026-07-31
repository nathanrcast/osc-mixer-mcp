# Hardware Validation

Address maps are only as good as the console that confirms them. The test suite proves internal consistency; only hardware proves the addresses are real.

**Run the sequence on the XR18 first** — it is the one model with existing behaviour to preserve — then X32, then WING.

## Status

| Family | State |
|---|---|
| X-Air (XR18) | Addresses from the published X-Air OSC spec. **Smoke test not yet run against v0.4.0.** |
| X32 / M32 | Addresses from Maillot's *UNOFFICIAL X32/M32 OSC REMOTE PROTOCOL*. **Not yet run.** |
| WING | Several addresses UNVERIFIED (below). **Not yet run.** |

## WING paths needing confirmation

Marked `UNVERIFIED` in `src/osc_mcp/profiles/wing.py`. Confirm against *WING Remote Protocols v3.0.x* and the console, then correct the matrix in `tests/test_profiles.py` first.

| Method | Current guess | Note |
|---|---|---|
| `ch_send` | `/ch/{n}/send/{bus}/lvl` | Destination may be a token (`BUS1`) rather than an index |
| `ch_gain` | `/ch/{n}/in/set/g` | |
| `ch_phantom` | `/ch/{n}/in/set/vph` | |
| `ch_eq_band` | `/ch/{n}/eq/{band}/{f,g,q}` | Real units assumed, not normalized |
| `keepalive` | `/*S` @ 5 s | Renewal token unconfirmed |
| `identify_address` | `/?` | |

Deliberately **not** guessed — these raise instead of firing an unknown message at a live console:

- `scene_recall` / `scene_name`
- `meters_subscribe` / RTA

Fill them in only once confirmed.

## Smoke test sequence

Run identically on each console — the point of v0.4.0 is that one vocabulary drives all three.

1. **`connect_mixer(<ip>)` with no port.** Asserts detection picked the right model *and* port (10024 / 10023 / 2223), and that names synced in ~1 s rather than ~30.
2. **`get_mixer_info()`.** Correct model, firmware, and true channel/bus/DCA/FX counts.
3. **`set_channel_fader(1, -10)` then `get_channel_fader(1)`.** Round-trips to ≈ −10 dB. Catches WING's dB-vs-taper split.
4. **`set_channel_mute(1, True)`.** Confirm the strip is **actually muted on the console surface**, not unmuted. Catches an inverted `encode_mute` — the failure mode that silently opens a channel mid-service.
5. **`set_bus_fader(1, -6)`.** Catches the `/bus/1` vs `/bus/01` padding split.
6. **`set_main_fader(-6)`.** Catches `/lr/mix/fader` vs `/main/st/mix/fader` vs `/main/1/fdr`. On X-Air this specifically confirms the v0.4.0 fix — `/lr/0/mix/fader` was a no-op.
7. **`set_channel_eq(1, band=2, frequency_hz=1000, gain_db=3, q=2)`.** Console must show **1 kHz / +3 dB / Q 2**, not garbage. Regression test for the raw-value bug fixed in v0.4.0.
8. **`batch([...])` with ~10 mixed ops.** All land, one round-trip.
9. **`capture_rta(seconds=3)`** with pink noise. Plausible 100-band spectrum.
10. **`send_raw_osc("/node", …)`** → refused. On WING, confirm a legitimate `/$ctl/…` call is *allowed* (proves the allowlist went per-profile).
11. **`OSC_MCP_READ_ONLY=1`, restart.** Writes refused, reads still work. On **WING**, confirm the console does not lose its other OSC client — the keepalive must not be taken in read-only mode.

## Also worth confirming on the XR18

Three latent bugs were fixed in v0.4.0 on the strength of the published spec. Steps 6 and 7 cover two; the third:

- **Channel count.** `/ch/01`–`/ch/16` only; the stereo aux is `/rtn/aux`. Confirm channel 16 responds and that there is no `/ch/17`.
