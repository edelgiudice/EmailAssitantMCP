# Email Assistant MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.13.3-green.svg)](https://github.com/jlowin/fastmcp)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A FastMCP-based email personal assistant that provides MCP (Model Context Protocol) tools for managing Gmail accounts. The server exposes both stdio and SSE transports for integration with MCP-compatible clients like Claude Desktop.

## Features

- **Multi-account Gmail support** via OAuth 2.0 with refresh tokens
- **Rule-based email automation** - create, manage, and apply rules for automatic email triage
- **Batch operations** - move multiple emails efficiently (50-100x faster than individual moves)
- **Integrated workflows** - `manage` tool combines messages, rules, and folders in one call
- **Multiple transports** - stdio (for IDEs) and SSE (for web clients)
- **Comprehensive logging** - configurable file-based logging with sensitive data redaction

## Prerequisites

- [uv](https://docs.astral.sh/uv/) - handles virtual environment and dependency management
- Python 3.11+ - automatically installed by `uv sync`

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure Gmail account

Set up OAuth credentials and authenticate (see [Google Console Configuration Guide](Documentation/GOOGLE_CONSOLE_SETUP.md) for detailed setup):

```bash
uv run email-assistant-config add-gmail personal-gmail
```

This launches Google's OAuth consent screen, captures the refresh token, and stores it in `~/.email_assistant_mcp/configs.json`.

### 3. Launch the server

**For Claude Desktop (stdio transport):**
```bash
uv run email-assistant-mcp --transport stdio
```

**For web clients (SSE transport):**
```bash
uv run email-assistant-mcp --transport sse --host 127.0.0.1 --port 8000 --sse-path /sse
```

**To use with Claude Desktop:** See the [Claude Desktop Setup Guide](Documentation/CLAUDE_DESKTOP_SETUP.md) for detailed instructions on configuring the MCP server in Claude Desktop.

## Available Tools

The MCP server provides the following tool groups:

### Bootstrap Tools
- `health_check` - verify server is running
- `list_email_accounts` - show configured accounts
- `activate_email_account` - switch active account
- `setup_gmail_account` - configure new Gmail account via OAuth

### Email Operations
- `batch_move_emails` - efficiently move multiple emails (supports different destinations per message)

### Message Tools
- `search_mailbox` - find emails matching criteria

### Rule Tools
- `create_rule` - define automation rules for email triage
- `list_rules` - show all configured rules
- `update_rule` - modify existing rules
- `delete_rule` - remove rules

### Manage Tool
- `manage` - integrated workflow that fetches messages, active rules, and folders in one call

### Folder Tools
- `list_folders` - retrieve available email folders/labels

## MCP Resources

Some tools use `resource://` URIs for large payloads, requiring MCP clients to call `resources/read` with the URI to fetch the actual content:

- `list_email_folders` - folder lists exposed as resources
- `fetch_email_full` - full message content with all headers and attachments
- `draft_email` - draft preview data

**Tools that return inline data (no resource URIs needed):**
- `get_emails` - returns messages directly in response
- `manage` - returns messages, rules, and folders directly in response for integrated workflow convenience

## Configuration

### Email Accounts

Email account credentials are stored in `~/.email_assistant_mcp/configs.json`. Each account has a `config_id` and contains:

```json
{
  "provider": "gmail",
  "email_address": "me@example.com",
  "display_name": "My Name",
  "refresh_token": "<oauth-refresh-token>",
  "client_id": "<google-oauth-client-id>",
  "client_secret": "<google-oauth-client-secret>"
}
```

**Important:** See [GOOGLE_CONSOLE_SETUP.md](Documentation/GOOGLE_CONSOLE_SETUP.md) for instructions on preventing OAuth tokens from expiring after 7 days.

### Logging

Configure logging via environment variables:

- `EMAIL_ASSISTANT_LOG_FILE` - path to log file (default: `~/.email_assistant_mcp/logs/server.log`)
- `EMAIL_ASSISTANT_LOG_LEVEL` - log level (default: `INFO`)

Logs automatically redact sensitive data (email addresses, tokens, passwords).

## Development

### Project Structure

```
email_assistant_mcp/
├── email_assistant_mcp/    # Main package
│   ├── server.py           # FastMCP server bootstrap
│   ├── config.py           # Configuration schemas
│   ├── credential_store.py # Credential management
│   ├── email_clients/      # Email provider implementations
│   └── tools/              # MCP tool definitions
├── tests/                  # Unit tests
├── data/
│   └── rules/              # JSON rule definitions
└── Playground/             # Ad-hoc notebooks and prototypes
```

### Running Tests

```bash
pytest
```

Or with coverage:

```bash
pytest --cov=email_assistant_mcp
```

### Adding Features

1. New email operations go in `email_assistant_mcp/email_clients/`
2. New MCP tools go in `email_assistant_mcp/tools/`
3. Register new tools in `email_assistant_mcp/tools/__init__.py`
4. Add tests under `tests/`

## Documentation

Comprehensive guides are available in the [Documentation](Documentation/) folder:

- **[Claude Desktop Setup Guide](Documentation/CLAUDE_DESKTOP_SETUP.md)** - Configure Claude Desktop to use this MCP server
- **[Google Console Setup Guide](Documentation/GOOGLE_CONSOLE_SETUP.md)** - Set up OAuth credentials and prevent token expiration
- **[Contributing Guide](Documentation/CONTRIBUTING.md)** - Development guidelines, code standards, and PR process
- **[Project Guide (CLAUDE.md)](Documentation/CLAUDE.md)** - Internal architecture and implementation patterns

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](Documentation/CONTRIBUTING.md) for details on:

- Setting up your development environment
- Code standards and style guide
- Testing requirements
- Pull request process
- Reporting bugs and requesting features

For questions or support, please open an issue on GitHub.
