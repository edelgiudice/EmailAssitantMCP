# Contributing to Email Assistant MCP

Thank you for your interest in contributing to Email Assistant MCP! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Contact](#contact)

## Code of Conduct

This project follows a simple code of conduct: Be respectful, be constructive, and help make this project better for everyone.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git for version control
- A Google Cloud account (for testing Gmail integration)

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/email_assistant_mcp.git
   cd email_assistant_mcp
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Set up Gmail credentials for testing**
   - Follow [GOOGLE_CONSOLE_SETUP.md](GOOGLE_CONSOLE_SETUP.md) to create OAuth credentials
   - Run: `uv run email-assistant-config add-gmail test-account`

4. **Verify installation**
   ```bash
   pytest
   ```

5. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Project Structure

```
email_assistant_mcp/
├── email_assistant_mcp/     # Main package
│   ├── server.py            # FastMCP server bootstrap
│   ├── config.py            # Configuration schemas
│   ├── credential_store.py  # Credential management
│   ├── email_clients/       # Email provider implementations
│   │   ├── base.py          # Abstract EmailClient interface
│   │   └── gmail_client.py  # Gmail implementation
│   └── tools/               # MCP tool definitions
│       ├── bootstrap.py     # Account setup tools
│       ├── email_ops.py     # Email operation tools
│       ├── messages.py      # Message search tools
│       ├── rules.py         # Rule management tools
│       └── manage.py        # Combined workflow tools
├── tests/                   # Unit tests (mirror package structure)
├── data/rules/              # JSON rule definitions (gitignored)
└── Playground/              # Ad-hoc notebooks and experiments
```

### Running the Server Locally

**stdio transport:**
```bash
uv run email-assistant-mcp --transport stdio
```

**SSE transport:**
```bash
uv run email-assistant-mcp --transport sse --host 127.0.0.1 --port 8000
```

### Making Changes

1. **Add new email operations** in `email_assistant_mcp/email_clients/`
2. **Add new MCP tools** in `email_assistant_mcp/tools/`
3. **Register tools** in `email_assistant_mcp/tools/__init__.py`
4. **Add tests** in `tests/` mirroring the package structure
5. **Update documentation** in README.md or relevant docs

## Code Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guide
- Use type hints for function parameters and return values
- Maximum line length: 100 characters (not strict, use judgment)
- Use descriptive variable and function names

### Type Hints

Always include type hints:

```python
from __future__ import annotations

def search_messages(
    query: str,
    folder: str = "INBOX",
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """Search for messages matching the query."""
    ...
```

### Docstrings

Use docstrings for all public functions, classes, and modules:

```python
def batch_move_emails(
    operations: list[dict[str, Any]],
    credential_store: CredentialStore,
) -> dict[str, Any]:
    """
    Move multiple emails efficiently in a single batch operation.

    Args:
        operations: List of move operations with message_id, add_labels, remove_labels
        credential_store: Store containing active account credentials

    Returns:
        Dictionary with success count and any errors

    Raises:
        ValueError: If operations list is empty or malformed
    """
    ...
```

### Logging

Use the centralized logging system with appropriate levels:

```python
import logging

logger = logging.getLogger(__name__)

# Use structured logging with context
logger.info("Processing batch operation | count=%d", len(operations))
logger.debug("Operation details | operation=%s", operation)
logger.error("Failed to move message | message_id=%s | error=%s", msg_id, str(e))
```

**Never log sensitive data** (email addresses, tokens, passwords) - the logging system automatically redacts these.

### Error Handling

- Use specific exception types
- Provide helpful error messages
- Log errors with context before raising

```python
try:
    result = client.batch_move_messages(operations)
except GoogleAPIError as e:
    logger.error("Gmail API error | operation=batch_move | error=%s", str(e))
    raise ValueError(f"Failed to move messages: {e}") from e
```

## Testing

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=email_assistant_mcp --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_email_ops.py
```

### Writing Tests

1. **Mirror package structure** - tests go in `tests/` with the same structure as `email_assistant_mcp/`
2. **Use pytest fixtures** - for common setup like mock credentials
3. **Mock external services** - use `pytest-mock` to mock Gmail API calls
4. **Test edge cases** - empty inputs, invalid data, API errors

Example test:

```python
import pytest
from email_assistant_mcp.tools.email_ops import batch_move_emails

def test_batch_move_emails_success(mocker, mock_credential_store):
    """Test successful batch move operation."""
    # Arrange
    mock_client = mocker.Mock()
    mock_client.batch_move_messages.return_value = {"success": 2, "failed": 0}
    mocker.patch("email_assistant_mcp.tools.email_ops.get_active_client", return_value=mock_client)

    operations = [
        {"message_id": "msg1", "add_labels": ["LABEL_1"], "remove_labels": ["INBOX"]},
        {"message_id": "msg2", "add_labels": ["LABEL_2"], "remove_labels": ["INBOX"]},
    ]

    # Act
    result = batch_move_emails(operations, mock_credential_store)

    # Assert
    assert result["success"] == 2
    assert result["failed"] == 0
    mock_client.batch_move_messages.assert_called_once_with(operations)
```

### Test Coverage

- Aim for >80% code coverage on new code
- All new tools must have tests
- All email client methods must have tests

## Pull Request Process

### Before Submitting

1. **Run tests** - `pytest` must pass with no failures
2. **Check coverage** - New code should have tests
3. **Update documentation** - Update README.md if adding features
4. **Run the server** - Manually test your changes work
5. **Commit message** - Use clear, descriptive commit messages

### Commit Message Format

```
<type>: <short summary>

<optional detailed description>

<optional footer>
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions or fixes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

**Examples:**
```
feat: add support for drafts in batch operations

Extends batch_move_emails to support draft messages in addition
to sent/received emails.

Closes #42
```

```
fix: prevent token expiration on inactive accounts

Adds automatic token refresh check before API calls to prevent
stale token errors.
```

### Submitting Pull Request

1. **Push your branch** to your fork
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create pull request** on GitHub
   - Use a clear, descriptive title
   - Reference any related issues (`Closes #123`, `Fixes #456`)
   - Describe what changed and why
   - Include screenshots/examples if relevant

3. **Respond to feedback** - Address review comments promptly

4. **Keep PR focused** - One feature/fix per PR (easier to review)

### PR Checklist

- [ ] Tests pass (`pytest`)
- [ ] New code has tests
- [ ] Documentation updated if needed
- [ ] Commit messages are clear
- [ ] Code follows project style
- [ ] No credentials or secrets in code
- [ ] Branch is up to date with main

## Reporting Issues

### Bug Reports

When reporting bugs, include:

1. **Description** - What happened vs. what you expected
2. **Steps to reproduce** - Detailed steps to trigger the bug
3. **Environment** - OS, Python version, package versions
4. **Logs** - Relevant log output (redact sensitive data!)
5. **Screenshots** - If applicable

**Template:**
```markdown
**Bug Description:**
The batch_move_emails tool fails when...

**Steps to Reproduce:**
1. Configure Gmail account
2. Call batch_move_emails with...
3. Error occurs

**Expected Behavior:**
Should move emails successfully

**Environment:**
- OS: Windows 11
- Python: 3.11.5
- Package version: 0.1.0

**Logs:**
```
[paste relevant logs here]
```
```

### Feature Requests

When requesting features, include:

1. **Use case** - What problem does this solve?
2. **Proposed solution** - How should it work?
3. **Alternatives** - Other approaches you considered
4. **Examples** - Mock code or API examples

## Contact

- **Issues:** Use [GitHub Issues](https://github.com/edelgiudice/email_assistant_mcp/issues)
- **Email:** emilio.delgiudice@gmail.com
- **Discussions:** Use GitHub Discussions for questions and ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing!** Your efforts help make Email Assistant MCP better for everyone.
