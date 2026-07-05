# OSC XR18 MCP — repo facts

OSC_MCP is an MCP (Model Context Protocol) Server that implements the Open Sound Control (OSC) protocol. It allows AI assistants to send and receive OSC messages to control a Behringer X-Air XR18 digital mixer and other OSC-compatible applications.

## Tech Stack

- **Python** >=3.11
- **MCP SDK**: `mcp[cli]` (FastMCP with `@mcp.tool()` decorators)
- **OSC**: `python-osc` (SimpleUDPClient)
- **Package manager**: `uv`
- **Transport**: stdio

## Project Structure

- `src/osc_mcp/server.py` — MCP server + all tool definitions
- `src/osc_mcp/osc_client.py` — OSC UDP send/query wrapper
- `src/osc_mcp/xair.py` — XR18-specific address patterns, dB conversion, NameRegistry
- `tests/` — pytest test suite

## Commands

- `uv sync` — install/update dependencies
- `uv run pytest` — run full test suite
- `uv run pytest tests/test_xair.py -k test_name` — run a specific test
- `uv run osc-mcp` — run MCP server via stdio
- `uv run mcp dev src/osc_mcp/server.py` — MCP inspector for interactive testing

## Testing Policy

Every feature must have tests before delivery. Run `uv run pytest` and ensure all tests pass before committing.

## License

Apache License 2.0
