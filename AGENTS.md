# OSC Mixer MCP — agent notes

MCP server that controls Behringer digital mixers over OSC/UDP. The console family is detected at connect time; a `MixerProfile` then supplies every OSC address, value encoding and capability count. Supports X-Air (XR12/16/18, X18, MR18), X32/M32 and WING.

Renamed from `osc-xr18-mcp` at v0.4.0 when it stopped being XR18-only. `osc-xr18-mcp` survives as a console-script alias so older MCP client registrations keep launching.

Python ≥3.11, `uv`, FastMCP (`mcp[cli]`) over stdio. `python-osc` only builds and parses messages — the socket is ours.

## Commands

- `uv sync` · `uv run pytest` — the gate: every feature ships with tests, and the suite passes before a commit. No hardware needed; transport tests drive a real loopback UDP console (`FakeMixer` in `tests/test_osc_client.py`), not a mocked socket.
- `uv run pytest tests/test_profiles.py -k wing` — a subset
- `uv run osc-mixer-mcp` — the server over stdio (`osc-xr18-mcp` is a kept alias); `uv run mcp dev src/osc_mcp/server.py` — MCP inspector

## Layout

`src/osc_mcp/`: `server.py` (all tool definitions), `osc_client.py` (persistent UDP socket, receiver thread, correlated `query`/`query_many`, keepalive), `profiles/` (`base.py` is the contract; `xair.py`, `x32.py`, `wing.py`; registry + `detect` in `__init__.py`), `scaling.py` (dB taper and EQ/gain/pan normalization for X-Air + X32; WING overrides with identity), `config.py` (network allowlist, read-only gate, persisted mixer address).

## Invariants

- **Adding a parameter means adding a profile method**, not an inline address string. There are no OSC address literals in `server.py` outside the raw-OSC gates.
- **Anything that differs per family goes on the profile**: addresses, index padding, mute polarity, value scaling, allow/deny lists, identify/keepalive.
- `tests/test_profiles.py` holds the per-model address matrix — it is the executable spec. Correct it there first when hardware disproves an address.
- **Never guess a WING address into a send.** Unverified paths are commented `UNVERIFIED`; where a wrong guess would hit a live console (scenes, meters) the profile raises instead.
- Read-only mode must gate every write tool via the `@writes` decorator, and must suppress the keepalive — WING allows only one OSC subscriber.

## Traps

1. **Mute polarity is inverted between families.** X-Air/X32 `mix/on` sends 1 for *unmuted*; WING `mute` sends 1 for *muted*. Always go through `profile.encode_mute()`. Plain switches (EQ on, phantom) use `encode_on()` and are not inverted.
2. **EQ takes normalized 0–1 on X-Air/X32**, not Hz/dB/Q. Sending raw values lands the band somewhere unrelated — this was a live bug before v0.4.0.
3. **Bus index padding differs**: `/bus/1` on X-Air, `/bus/01` on X32.
4. **X-Air OSC channels are `/ch/01`–`/ch/16`.** The XR18's "18" counts the stereo aux input, which is `/rtn/aux`, not `/ch/17`.
5. **Queries must be correlated by address.** The socket is shared with subscriptions and state pushes; anything else risks answering a query with an unrelated packet.
6. **`_sync_names` uses `query_many`.** Sequential queries would take ~30 s on an X32.

## Live console safety

- Before driving a real console, check it is idle: subscribe to `/meters` and confirm nothing is above -60 dBFS.
- Snapshot every parameter you intend to write via raw OSC and replay it afterwards — consoles carry a hand-dialled gain structure worth preserving.
- Finding a console: sweep the subnet with an identify probe — X-Air `/xinfo` on UDP 10024, X32 `/info` on 10023, WING `/?` on 2223. It replies with ip, name, model and firmware. Mixers may not appear in the router's client list.

## Hardware validation

Address maps are only as good as the console that confirms them. Sequence and per-model results: `docs/hardware_validation.md`. Run it on the XR18 first (the one model with existing behaviour to preserve), then X32, then WING.

## Review focus

- OSC address literals outside a profile; writes that bypass `@writes`; unverified WING paths reaching a send.
- Mute/on encoding going around `profile.encode_mute()` / `encode_on()`.

License: Apache 2.0. **Public repo** — lab details (console IPs, hosts) go in the gitignored `CLAUDE.local.md`.
