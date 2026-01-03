"""Pytest configuration that provides stubs for optional runtime dependencies."""

from __future__ import annotations

import sys
import types
from typing import Any, Callable, cast


class _FastMCPStub:
    """Minimal stand-in for the FastMCP class used during testing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - trivial stub
        pass

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Return a decorator that leaves the wrapped function untouched."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator


class _InstalledAppFlowStub:
    """Simplified OAuth flow that mimics google_auth_oauthlib's API."""

    @classmethod
    def from_client_config(cls, *args: Any, **kwargs: Any) -> "_InstalledAppFlowStub":
        return cls()

    def run_local_server(self, *args: Any, **kwargs: Any) -> Any:
        class _Credentials:
            refresh_token = "test-fake-refresh-token-not-real-abc"

        return _Credentials()


if "fastmcp" not in sys.modules:
    fastmcp_module = cast(Any, types.ModuleType("fastmcp"))
    fastmcp_module.FastMCP = _FastMCPStub
    sys.modules["fastmcp"] = fastmcp_module


if "google_auth_oauthlib" not in sys.modules:
    oauth_module = cast(Any, types.ModuleType("google_auth_oauthlib"))
    flow_module = cast(Any, types.ModuleType("google_auth_oauthlib.flow"))
    flow_module.InstalledAppFlow = _InstalledAppFlowStub
    oauth_module.flow = flow_module
    sys.modules["google_auth_oauthlib"] = oauth_module
    sys.modules["google_auth_oauthlib.flow"] = flow_module
