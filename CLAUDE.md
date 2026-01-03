# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastMCP-based email personal assistant that provides MCP (Model Context Protocol) tools for managing Gmail accounts. The server exposes both stdio and SSE transports for integration with MCP-compatible clients like Claude Desktop.

## Core Architecture

### Server Bootstrap (email_assistant_mcp/server.py)
- `build_server()` creates the FastMCP instance and registers all tools
- Server instructions emphasize that this is a **PROXY** - it provides access to email data but does NOT automatically execute actions
- Tools return `resource://` URIs for large payloads (folder catalogs, message lists, drafts) that must be read via MCP's `resources/read` API

### Tool Organization (email_assistant_mcp/tools/)
Tools are registered in distinct groups via `register_all_tools()`:

1. **Bootstrap tools** (`bootstrap.py`): Account setup and activation
   - `health_check`, `list_email_accounts`, `activate_email_account`
   - `setup_gmail_account` (OAuth flow)

2. **Email operations tools** (`email_ops.py`): Core email actions
   - `batch_move_emails` - optimized bulk message moves (50-100x faster than individual moves)
   - Supports different destinations per message in a single operation

3. **Message tools** (`messages.py`): Email search and retrieval
   - `search_mailbox` - returns messages matching filters
   - Internal pagination handling - fetches all pages and combines results

4. **Rule tools** (`rules.py`): Automation rule management
   - Rules stored as JSON files in `data/rules/` with pattern `rule_{id}_{slug}.json`
   - Each rule has: `id`, `name`, `summary`, `ref_command`, `version`, `prompt`, optional `expiration_date`, `auto_execute`
   - `is_rule_active()` checks expiration dates (ISO 8601 format)

5. **Manage tools** (`manage.py`): Combined workflow tool
   - `manage` tool fetches messages, rules, AND folders in one call
   - Defaults to `folder="INBOX"` to avoid processing already-triaged messages
   - Returns inline data (not resource URIs) - `messages`, `rules`, `folders` fields are directly usable
   - This is **STEP 1** of triage workflow - caller must then execute each rule's `ref_command`

### Email Client Abstraction (email_assistant_mcp/email_clients/)
- `base.py`: Abstract `EmailClient` interface defining operations all providers must support
  - `list_folders()`, `search_messages()`, `fetch_message_full()`, `batch_move_messages()`
  - Search implementations handle pagination internally and return combined results
- `gmail_client.py`: Gmail implementation using Google API (OAuth refresh tokens)

### Configuration & Credentials (email_assistant_mcp/config.py, credential_store.py)
- Provider configs: `GmailOAuthConfig`
- `CredentialStore` persists configs to `~/.email_assistant_mcp/configs.json`
- File-based caching with mtime tracking to avoid redundant disk reads
- Each config identified by a `config_id` string chosen during setup

#### Config Validation Policy
- **Required fields**: `provider`, `email_address` (if provided)
- **Optional credential fields** (`refresh_token`, `client_id`, `client_secret`):
  - Empty strings are explicitly allowed for incomplete/partial configs
  - Type validation enforced (must be strings if provided)
  - These fields are optional at config-creation time but required for actual authentication
  - Authentication will fail clearly at runtime if credentials are missing
- **Port fields**: Must be integers in range 1-65535 if provided
- This policy allows configs to be created and stored before all credentials are available

### Logging System (email_assistant_mcp/logging_*.py)
- **Setup** (`logging_setup.py`): Centralized configuration, context tracking (correlation IDs), and JSON formatting
- **Redaction** (`logging_redaction.py`): Automatically redacts email addresses, tokens, passwords from logs
- Configured via environment variables or `configure_logging()` in `server.py`
- Log file path configurable via `EMAIL_ASSISTANT_LOG_FILE` environment variable

## Development Commands

### Setup
```bash
uv sync
```

### Run Server

**stdio transport** (for IDE-based MCP clients):
```bash
uv run email-assistant-mcp --transport stdio
```

**SSE transport** (for HTTP-based clients):
```bash
uv run email-assistant-mcp --transport sse --host 127.0.0.1 --port 8280 --sse-path /sse
```

### Configuration CLI

**Add Gmail account** (launches OAuth flow):
```bash
uv run email-assistant-config add-gmail personal-gmail
```

### Testing

use Pytest as testing framework

**Run all tests**:
```bash
pytest
```


## Key Implementation Patterns

### MCP Resource URIs
- Large payloads (folder lists, message batches, drafts) are exposed via `resource://` URIs
- **Exception**: The `manage` tool returns inline data (messages/rules/folders directly in response)
- Clients must call MCP `resources/read` with the URI to fetch actual content
- Resource URIs follow pattern: `resource://email-assistant/{resource_type}/{request_id}`

### Email Triage Workflow Priority
When implementing email triage features, follow this priority:

1. **PRIORITY 1**: Apply automation rules first
   - Check `active_rule_count` in `manage` response
   - For each active rule, match messages to criteria and execute the rule's `ref_command`
   - Rules are the primary mechanism for moving messages

2. **PRIORITY 2**: LLM-based categorization for remaining messages
   - After rules are applied, categorize unprocessed messages using LLM reasoning
   - Match messages to available folders based on content/sender/subject
   - Use `batch_move_emails` for efficient bulk moves

3. **FALLBACK**: When no rules configured, suggest creating rules for common patterns

### Batch Operations
Always prefer `batch_move_emails` over individual move operations:
- Supports different destinations per message in single call
- 50-100x performance improvement over sequential moves
- Operation format: `[{message_id, add_labels, remove_labels}, ...]`

### Rule Storage
- Rules stored in `data/rules/` as JSON files
- Filename pattern: `rule_{id}_{action_type}_{slugified_name}.json`
- IDs are auto-incremented integers
- Use `RuleStore` class to manage CRUD operations

### Folder Caching
- `FolderTools` implements caching to avoid repeated API calls
- Cache invalidated on folder creation
- Use `list_folders` tool to expose available folders to LLM

## Project Structure Notes

- `Playground/`: Scratch notebooks and prototypes (not part of main package)
- `email_assistant_mcp/`: Main package code
- `tests/`: Unit tests organized by module
- `data/rules/`: JSON rule definitions
- `.prompts/`: Planning documents and implementation notes (historical context)
- `plans/`: Implementation planning documents

## Important Constraints

- **DO NOT** execute email actions automatically - the server is a proxy that requires explicit tool calls
- **DO NOT** skip executing rules returned by the `manage` tool - they must all be applied
- **DO NOT** override `folder="INBOX"` parameter in `manage` unless user explicitly requests different scope
- **DO NOT** use individual move operations when `batch_move_emails` is available
- **ALWAYS** validate rule expiration dates before executing (check `is_rule_active()`)
