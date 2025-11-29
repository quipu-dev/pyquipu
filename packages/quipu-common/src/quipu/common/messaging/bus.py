import json
import logging
from pathlib import Path
from typing import Dict, Any, Protocol

import typer

from .messages import find_locales_dir

logger = logging.getLogger(__name__)


class MessageStore:
    """Loads and provides access to message templates from a JSON file."""

    def __init__(self, locale: str = "zh"):
        self._messages: Dict[str, str] = {}
        self.locale = locale
        self._load_messages()

    def _load_messages(self):
        locales_dir = find_locales_dir()
        if not locales_dir:
            logger.error("Message resource directory 'locales' not found. UI messages will be unavailable.")
            return

        message_file = locales_dir / self.locale / "cli.json"
        if not message_file.exists():
            logger.error(f"Message file for locale '{self.locale}' not found at {message_file}")
            return

        try:
            with open(message_file, "r", encoding="utf-8") as f:
                self._messages = json.load(f)
            logger.debug(f"Successfully loaded {len(self._messages)} messages for locale '{self.locale}'.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load or parse message file {message_file}: {e}")

    def get(self, msg_id: str, default: str = "") -> str:
        """Retrieves a message template by its ID."""
        return self._messages.get(msg_id, default or f"<{msg_id}>")


class Renderer(Protocol):
    """Protocol defining the interface for a message renderer."""

    def success(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def data(self, data_string: str) -> None: ...


class TyperRenderer:
    """A renderer that uses Typer for colored and styled CLI output."""

    def success(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.GREEN, err=True)

    def info(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.BLUE, err=True)

    def warning(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.YELLOW, err=True)

    def error(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.RED, err=True)

    def data(self, data_string: str) -> None:
        typer.echo(data_string, err=False)  # Explicitly to stdout


class MessageBus:
    """The central service for all user-facing CLI output."""

    def __init__(self, store: MessageStore, renderer: Renderer):
        self._store = store
        self._renderer = renderer

    def _render(self, level: str, msg_id: str, **kwargs: Any) -> None:
        template = self._store.get(msg_id)
        try:
            message = template.format(**kwargs)
        except KeyError as e:
            message = f"<Formatting error for '{msg_id}': missing key {e}>"
            logger.warning(message)

        render_method = getattr(self._renderer, level)
        render_method(message)

    def success(self, msg_id: str, **kwargs: Any) -> None:
        self._render("success", msg_id, **kwargs)

    def info(self, msg_id: str, **kwargs: Any) -> None:
        self._render("info", msg_id, **kwargs)

    def warning(self, msg_id: str, **kwargs: Any) -> None:
        self._render("warning", msg_id, **kwargs)

    def error(self, msg_id: str, **kwargs: Any) -> None:
        self._render("error", msg_id, **kwargs)

    def get(self, msg_id: str, **kwargs: Any) -> str:
        """Retrieves and formats a message string without rendering it."""
        template = self._store.get(msg_id)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Formatting error for '{msg_id}': missing key {e}")
            return template

    def data(self, data_string: str) -> None:
        self._renderer.data(data_string)


# --- Default Instance ---
# A default instance that can be easily imported and used.
# This avoids the need for complex dependency injection in the early stages.
_default_store = MessageStore(locale="zh")
_default_renderer = TyperRenderer()
bus = MessageBus(store=_default_store, renderer=_default_renderer)
