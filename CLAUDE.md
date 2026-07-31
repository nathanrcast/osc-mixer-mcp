# OSC Mixer MCP — repo facts

MCP server that controls Behringer digital mixers over OSC/UDP. The console family is detected at connect time; a `MixerProfile` then supplies every OSC address, value encoding and capability count. Supports X-Air (XR12/16/18, X18, MR18), X32/M32 and WING.

Repo is still named `osc-xr18-mcp` for history; the server and console script are `osc-mixer-mcp`.

## Tech Stack

- **Python** >=3.11
- **MCP SDK**: `mcp[cli]` (FastMCP with `@mcp.tool()` decorators)
- **OSC**: `python-osc` (message build/parse only — the socket is ours)
- **Package manager**: `uv`
- **Transport**: stdio

## Project Structure

- `src/osc_mcp/server.py` — MCP server + all tool definitions
- `src/osc_mcp/osc_client.py` — persistent UDP socket, receiver thread, correlated query/query_many, keepalive
- `src/osc_mcp/profiles/` — `base.py` (the contract), `xair.py`, `x32.py`, `wing.py`, `__init__.py` (registry + `detect`)
- `src/osc_mcp/scaling.py` — dB taper, EQ/gain/pan normalization (X-Air + X32; WING overrides with identity)
- `src/osc_mcp/names.py` — `NameRegistry`, model-agnostic
- `src/osc_mcp/meters.py` — meter blob decode + RTA accumulator
- `src/osc_mcp/config.py` — network allowlist, read-only gate, persisted mixer address/model
- `tests/` — pytest suite, no hardware required

## Commands

- `uv sync` — install/update dependencies
- `uv run pytest` — run full test suite
- `uv run pytest tests/test_profiles.py -k wing` — run a subset
- `uv run osc-mixer-mcp` — run MCP server via stdio (`osc-xr18-mcp` is a kept alias)
- `uv run mcp dev src/osc_mcp/server.py` — MCP inspector for interactive testing

## Conventions

- **Adding a parameter means adding a profile method**, not an inline address string. There are no OSC address literals in `server.py` outside the raw-OSC gates.
- **Anything that differs per family goes on the profile**: addresses, index padding, mute polarity, value scaling, allow/deny lists, identify/keepalive.
- `tests/test_profiles.py` holds the per-model address matrix — it is the executable spec. Correct it there first when hardware disproves an address.
- **Never guess a WING address into a send.** Unverified paths are commented `UNVERIFIED`; where a wrong guess would hit a live console (scenes, meters) the profile raises instead.
- Read-only mode must gate every write tool via the `@writes` decorator, and must suppress the keepalive — WING allows only one OSC subscriber.

## Gotchas

1. **Mute polarity is inverted between families.** X-Air/X32 `mix/on` sends 1 for *unmuted*; WING `mute` sends 1 for *muted*. Always go through `profile.encode_mute()`. Plain switches (EQ on, phantom) use `encode_on()` and are not inverted.
2. **EQ takes normalized 0–1 on X-Air/X32**, not Hz/dB/Q. Sending raw values lands the band somewhere unrelated — this was a live bug before v0.4.0.
3. **Bus index padding differs**: `/bus/1` on X-Air, `/bus/01` on X32.
4. **X-Air OSC channels are `/ch/01`–`/ch/16`.** The XR18's "18" counts the stereo aux input, which is `/rtn/aux`, not `/ch/17`.
5. **Queries must be correlated by address.** The socket is shared with subscriptions and state pushes; anything else risks answering a query with an unrelated packet.
6. **`_sync_names` uses `query_many`.** Sequential queries would take ~30 s on an X32.

## Testing Policy

Every feature must have tests before delivery. Run `uv run pytest` and ensure all tests pass before committing. Transport tests drive a real loopback UDP console (`FakeMixer` in `tests/test_osc_client.py`) rather than mocking the socket.

## Hardware Validation

Address maps are only as good as the console that confirms them. See the smoke-test sequence in the project plan; run it on the XR18 first (the one model with existing behaviour to preserve), then X32, then WING.

## License

Apache License 2.0
