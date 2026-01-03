# Claude Desktop Configuration Guide

This guide walks you through configuring Claude Desktop to use the Email Assistant MCP server locally. Once configured, you'll be able to manage your Gmail account directly through conversations with Claude.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Locate Configuration File](#locate-configuration-file)
3. [Configure MCP Server](#configure-mcp-server)
4. [Restart Claude Desktop](#restart-claude-desktop)
5. [Verify Connection](#verify-connection)
6. [Using the Tools](#using-the-tools)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

Before configuring Claude Desktop, ensure you have:

1. **Claude Desktop installed**
   - Download from [claude.ai/download](https://claude.ai/download)
   - Version 0.7.0 or later (with MCP support)

2. **Email Assistant MCP set up**
   ```bash
   cd /path/to/email_assistant_mcp
   uv sync
   ```

3. **Gmail account configured**
   - Follow [GOOGLE_CONSOLE_SETUP.md](GOOGLE_CONSOLE_SETUP.md) to set up OAuth credentials
   - Run: `uv run email-assistant-config add-gmail personal-gmail`

4. **Python 3.11+ with uv**
   - Verify: `uv --version`

## Locate Configuration File

Claude Desktop stores its configuration in a JSON file. The location depends on your operating system:

### macOS
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

To open in terminal:
```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Windows
```
%APPDATA%\Claude\claude_desktop_config.json
```

To open in File Explorer:
1. Press `Win + R`
2. Type: `%APPDATA%\Claude`
3. Open `claude_desktop_config.json` in a text editor

### Linux
```
~/.config/Claude/claude_desktop_config.json
```

To open in terminal:
```bash
nano ~/.config/Claude/claude_desktop_config.json
```

**Note:** If the file doesn't exist, create it with an empty JSON object: `{}`

## Configure MCP Server

### Option 1: Local Server with uv (Recommended)

This configuration uses `uv` to run the server in stdio mode. Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "email-assistant": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/email_assistant_mcp",
        "email-assistant-mcp",
        "--transport",
        "stdio"
      ],
      "env": {
        "EMAIL_ASSISTANT_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Important:** Replace `/absolute/path/to/email_assistant_mcp` with the actual absolute path to your project directory.

**Examples:**
- macOS/Linux: `/Users/yourname/projects/email_assistant_mcp`
- Windows: `C:\\Users\\YourName\\projects\\email_assistant_mcp` (use double backslashes)

### Option 2: Python Virtual Environment

If you prefer to use the virtual environment directly:

```json
{
  "mcpServers": {
    "email-assistant": {
      "command": "/absolute/path/to/email_assistant_mcp/.venv/bin/python",
      "args": [
        "-m",
        "email_assistant_mcp",
        "--transport",
        "stdio"
      ],
      "env": {
        "EMAIL_ASSISTANT_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Windows path example:**
```json
"command": "C:\\Users\\YourName\\projects\\email_assistant_mcp\\.venv\\Scripts\\python.exe"
```

### Multiple MCP Servers

If you already have other MCP servers configured, add the email-assistant to the existing `mcpServers` object:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/files"]
    },
    "email-assistant": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/email_assistant_mcp",
        "email-assistant-mcp",
        "--transport",
        "stdio"
      ],
      "env": {
        "EMAIL_ASSISTANT_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Environment Variables (Optional)

You can customize logging and other settings:

```json
{
  "mcpServers": {
    "email-assistant": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/email_assistant_mcp", "email-assistant-mcp", "--transport", "stdio"],
      "env": {
        "EMAIL_ASSISTANT_LOG_LEVEL": "DEBUG",
        "EMAIL_ASSISTANT_LOG_FILE": "/Users/yourname/logs/email_assistant.log"
      }
    }
  }
}
```

**Log levels:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## Restart Claude Desktop

After modifying the configuration file:

1. **Quit Claude Desktop completely**
   - macOS: `Cmd + Q` or Claude → Quit Claude
   - Windows: Right-click system tray icon → Exit
   - Linux: Close all windows and ensure the process has stopped

2. **Restart Claude Desktop**
   - Launch the application normally

3. **Wait for initialization**
   - The MCP server will start automatically when Claude Desktop launches
   - This may take a few seconds on first run

## Verify Connection

### Check Server Status

1. Open a conversation in Claude Desktop
2. Look for the MCP server indicator (usually shown as a tools icon or connection status)
3. You should see "email-assistant" listed as a connected server

### Test with a Simple Query

Try asking Claude:

```
Can you check my email assistant connection?
```

Claude should be able to call the `health_check` tool and confirm the server is running.

### List Available Accounts

Ask Claude:

```
What email accounts are configured?
```

Claude will use the `list_email_accounts` tool and show your configured Gmail accounts.

## Using the Tools

Once connected, you can interact with your Gmail account naturally through Claude. Here are some examples:

### Activating an Account

```
Activate my personal-gmail account
```

### Searching Emails

```
Show me unread emails from the last 3 days
```

```
Search for emails from john@example.com about the project proposal
```

### Managing Emails

```
Manage my inbox and organize today's emails
```

This will trigger the `manage` tool, which fetches messages, applies automation rules, and can categorize emails.

### Creating Automation Rules

```
Create a rule to automatically move newsletters to a "Newsletters" folder
```

### Batch Operations

```
Move all emails from sender@example.com to the Archive folder
```

Claude will use `batch_move_emails` for efficient bulk operations.

## Troubleshooting

### Server Not Appearing in Claude Desktop

**Symptoms:** Email-assistant doesn't show up in available tools

**Solutions:**
1. Check `claude_desktop_config.json` syntax - must be valid JSON
2. Verify absolute paths are correct (no `~` or relative paths)
3. Ensure `uv` is in your system PATH
4. Check Claude Desktop version supports MCP (0.7.0+)
5. Look for error messages in Claude Desktop's developer console

### "Command not found: uv"

**Cause:** `uv` is not in Claude Desktop's PATH

**Solutions:**
1. Install uv globally: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Or use absolute path to uv:
   ```json
   "command": "/Users/yourname/.local/bin/uv"
   ```
3. On Windows, use the full path: `C:\\Users\\YourName\\.cargo\\bin\\uv.exe`

### Server Starts But Tools Don't Work

**Symptoms:** Server connects but tool calls fail

**Solutions:**
1. Verify Gmail account is configured: `uv run email-assistant-config add-gmail test`
2. Check credentials are valid and not expired
3. Ensure you added yourself as a test user in Google Console (see [GOOGLE_CONSOLE_SETUP.md](GOOGLE_CONSOLE_SETUP.md))
4. Review logs at `~/.email_assistant_mcp/logs/server.log`
5. Try increasing log level to DEBUG in config

### "Module not found" or Import Errors

**Cause:** Dependencies not installed

**Solution:**
```bash
cd /path/to/email_assistant_mcp
uv sync
```

### OAuth Token Expired After 7 Days

**Cause:** Not added as test user in Google Console

**Solution:**
1. Go to Google Cloud Console → OAuth consent screen
2. Add your Gmail address as a test user
3. Re-authenticate: `uv run email-assistant-config add-gmail personal-gmail`
4. See [GOOGLE_CONSOLE_SETUP.md](GOOGLE_CONSOLE_SETUP.md) for details

### Finding Logs

**Default log location:**
- `~/.email_assistant_mcp/logs/server.log`

**Custom log location:**
Set in `claude_desktop_config.json`:
```json
"env": {
  "EMAIL_ASSISTANT_LOG_FILE": "/custom/path/to/logfile.log"
}
```

**View logs:**
```bash
tail -f ~/.email_assistant_mcp/logs/server.log
```

### Server Crashes on Startup

**Solutions:**
1. Test the server manually:
   ```bash
   cd /path/to/email_assistant_mcp
   uv run email-assistant-mcp --transport stdio
   ```
2. Check for error messages in the terminal
3. Verify Python version: `python --version` (must be 3.11+)
4. Check Claude Desktop logs (location varies by OS)

### Windows-Specific Issues

**Path separators:** Use double backslashes `\\` in JSON:
```json
"command": "C:\\Users\\YourName\\path\\to\\uv.exe"
```

**Long paths:** Enable long path support in Windows:
1. Run as Administrator: `reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1`
2. Restart computer

### Verifying Configuration Syntax

Use a JSON validator to check your config file:
```bash
python -m json.tool ~/.config/Claude/claude_desktop_config.json
```

If valid, it will output the formatted JSON. If invalid, it will show the error.

## Advanced Configuration

### Running Multiple Instances

You can configure different Gmail accounts as separate MCP servers:

```json
{
  "mcpServers": {
    "email-personal": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/email_assistant_mcp", "email-assistant-mcp"],
      "env": {
        "EMAIL_ASSISTANT_DEFAULT_ACCOUNT": "personal-gmail"
      }
    },
    "email-work": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/email_assistant_mcp", "email-assistant-mcp"],
      "env": {
        "EMAIL_ASSISTANT_DEFAULT_ACCOUNT": "work-gmail"
      }
    }
  }
}
```

### Development Mode

For development with verbose logging:

```json
{
  "mcpServers": {
    "email-assistant-dev": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/email_assistant_mcp", "email-assistant-mcp"],
      "env": {
        "EMAIL_ASSISTANT_LOG_LEVEL": "DEBUG",
        "EMAIL_ASSISTANT_LOG_FILE": "/tmp/email_assistant_dev.log"
      }
    }
  }
}
```

## Security Considerations

1. **Credentials are stored locally** in `~/.email_assistant_mcp/configs.json`
2. **Logs are redacted** - sensitive data is automatically removed from log files
3. **Access tokens are temporary** - refreshed automatically using stored refresh tokens
4. **Claude Desktop has full access** - the MCP server can read, move, and send emails
5. **Audit logs** - review `~/.email_assistant_mcp/logs/server.log` to see all operations

## Additional Resources

- [Claude Desktop Documentation](https://docs.anthropic.com/claude/docs/claude-desktop)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Email Assistant MCP Repository](https://github.com/edelgiudice/email_assistant_mcp)
- [Google Console Setup Guide](GOOGLE_CONSOLE_SETUP.md)
- [Contributing Guide](CONTRIBUTING.md)

## Getting Help

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review server logs at `~/.email_assistant_mcp/logs/server.log`
3. Test the server manually with `uv run email-assistant-mcp --transport stdio`
4. Open an issue on [GitHub](https://github.com/edelgiudice/email_assistant_mcp/issues) with:
   - Your operating system
   - Claude Desktop version
   - Relevant log excerpts (redact sensitive data!)
   - Configuration snippet (redact paths)

---

**Happy email management with Claude!** 📧✨
