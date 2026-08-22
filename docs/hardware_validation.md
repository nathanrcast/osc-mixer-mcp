# Hardware Validation

Address maps are only as good as the console that confirms them. The test suite proves internal consistency; only hardware proves the addresses are real.

**Run the sequence on the XR18 first** — it is the one model with existing behaviour to preserve — then X32, then WING. (XR18 done, 2026-08-21.)

## Status

| Family | State |
|---|---|
| X-Air (XR18) | **VALIDATED 2026-08-21** on an XR18, firmware 1.16, at 192.168.1.40. Full sequence run; one address bug found and fixed (head amps). See below. |
| X32 / M32 | Addresses from Maillot's *UNOFFICIAL X32/M32 OSC REMOTE PROTOCOL*. **Not yet run.** |
| WING | Several addresses UNVERIFIED (below). **Not yet run.** |

## XR18 run, 2026-08-21 (firmware 1.16)

Console was idle and silent throughout (81 meter frames, nothing above -60 dBFS,
main LR muted). Every parameter the run touched was snapshotted beforehand over
raw OSC and replayed afterwards; a full read-back confirmed the console was
returned to its exact pre-test state.

| Step | Result |
|---|---|
| 1. `connect_mixer` no port | PASS — detected XR18 on 10024, synced 10 names in ~1 s |
| 2. `get_mixer_info` | PASS — XR18, fw 1.16, 16 ch / 6 bus / 4 fx / 4 dca |
| 3. fader round-trip | PASS — -10 dB in, -10.0 dB back (raw 0.4995) |
| 4. mute | PASS — `muted=True` drives `/ch/01/mix/on` to **0**. Not inverted. |
| 5. `set_bus_fader` | PASS — 1-digit `/bus/1/...` is correct |
| 6. `set_main_fader` | PASS — `/lr/mix/fader` moves. Confirms the v0.4.0 fix; `/lr/0/mix/fader` was indeed a no-op |
| 7. `set_channel_eq` | PASS — 1 kHz/+3 dB/Q2 encoded as raw f=0.565 (~991 Hz), g=0.600 (+3 dB), q=0.451 (Q~2.06) |
| 8. `batch` (10 mixed ops) | PASS — all 10 landed in one round-trip and read back correctly |
| 9. `capture_rta(3)` | PASS — 60 frames, 100 bands, flat -80 dB on a silent console |
| 10. raw-OSC gates | PASS — `/node` and `/-prefs/ip/addr` refused, legitimate `/ch/01/mix/fader` allowed |
| 11. `OSC_MCP_READ_ONLY=1` | PASS — fader/mute/main/raw/batch all refused, all reads still work |
| Channel count | PASS — `/ch/16` answers, `/ch/17` is silent, `/rtn/aux` answers. The 18-vs-16 fix is correct. |

### Bug found and fixed: X-Air head amps are 1-indexed

`set_channel_gain` and `set_phantom_power` were writing to `/headamp/00/...`,
which **does not exist on the XR18** — the console never answers it. The write
was silently discarded while the tool still reported success, so an agent could
report "gain set to 20 dB" with nothing having moved.

Probing the whole range: `/headamp/00` is dead, `/headamp/01`-`/headamp/21`
answer, and the gain values line up 1:1 with the named channels (ch01-06 =
Vox 1/2/3, Acoustic, Inst Mic, Piano 57 carried real mic gains; the unused
ch07/ch08 sat at exactly 0.0 dB). So `/headamp/NN` is channel `NN`.

Fixed by overriding `ch_gain`/`ch_phantom` in `XAirProfile`. The base class
keeps the 0-indexed `/headamp/000` form, which is correct for X32/M32 — the
comment claiming both families are 0-indexed was wrong about X-Air only.
Re-verified on the console: gain 0 dB and 45 dB both round-trip exactly, and
the neighbouring `/headamp/12` stays untouched.

### Bug found and fixed: the test suite was not hermetic

`tests/test_server.py` did not redirect `config.CONFIG_FILE`, so it read the
developer's real `~/.osc_mcp/config.json`. Once a mixer address is saved,
`_get_client()` auto-reconnects from it, and `pytest` will connect to and drive
a live console if one is on the network — this surfaced as
`test_tool_reports_no_connection` failing the moment a real XR18 appeared.
The autouse fixture now points `CONFIG_DIR`/`CONFIG_FILE` at `tmp_path`, as
`tests/test_config.py` already did.

### Note, not a bug

`batch` op names are the bare forms (`channel_fader`, `bus_fader`, `send`), not
the tool names (`set_channel_fader`). The docstring lists them correctly, but
the two vocabularies differing is an easy thing for a caller to trip over.

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

All three latent v0.4.0 fixes are now confirmed on hardware: main fader (step 6),
EQ raw values (step 7), and the channel count — `/ch/01`-`/ch/16` answer,
`/ch/17` does not, and the stereo aux is `/rtn/aux`.
