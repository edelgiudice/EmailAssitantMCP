"""Shared testing utilities for FastMCP server registrations."""

from __future__ import annotations

import inspect
from typing import Any, Callable


class RegisteredResource:
    """Lightweight representation of a FastMCP resource decorator output."""

    def __init__(
        self,
        *,
        uri: str,
        name: str,
        description: str,
        mime_type: str,
        reader: Callable[..., Any],
    ) -> None:
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type
        self._reader = reader

    async def read(self) -> Any:
        """Call the registered reader and await coroutines automatically."""
        result = self._reader()
        if inspect.isawaitable(result):
            return await result
        return result


class ToolCapturingFastMCP:
    """Test double that records registered tools and resources."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.tools: dict[str, Callable[..., Any]] = {}
        self.resources: dict[str, RegisteredResource] = {}
        self.prompts: dict[str, Callable[..., Any]] = {}

    def tool(self, *decorator_args: Any, **decorator_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        name = decorator_kwargs.get("name")
        if name is None and decorator_args:
            name = decorator_args[0]
        if name is None:
            msg = "Tool name is required for the test stub."
            raise ValueError(msg)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return decorator

    def prompt(self, *decorator_args: Any, **decorator_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Mimic FastMCP's prompt decorator for tests."""
        declared_name = decorator_kwargs.get("name")
        if decorator_args and callable(decorator_args[0]) and declared_name is None:
            func = decorator_args[0]
            name = getattr(func, "__name__", None) or "prompt"
            self.prompts[name] = func
            return func

        if declared_name is None and decorator_args and isinstance(decorator_args[0], str):
            declared_name = decorator_args[0]

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            name = declared_name or getattr(func, "__name__", None) or "prompt"
            self.prompts[name] = func
            return func

        return decorator

    async def get_tools(self) -> dict[str, Callable[..., Any]]:
        """Mirror FastMCP.get_tools for validation steps."""
        return dict(self.tools)

    def resource(self, uri: str, **kwargs: Any) -> Callable[[Callable[..., Any]], RegisteredResource]:
        name = kwargs.get("name", uri)
        description = kwargs.get("description", "")
        mime_type = kwargs.get("mime_type", "text/plain")

        def decorator(func: Callable[..., Any]) -> RegisteredResource:
            resource = RegisteredResource(
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
                reader=func,
            )
            self.resources[uri] = resource
            return resource

        return decorator

    def add_resource(self, resource: RegisteredResource) -> RegisteredResource:
        """Allow tests to insert pre-built resources."""
        self.resources[str(resource.uri)] = resource
        return resource


__all__ = ["RegisteredResource", "ToolCapturingFastMCP"]
