import json
import logging
from typing import Any, Dict, Optional, Protocol

from .messages import find_locales_dir

logger = logging.getLogger(__name__)


class MessageStore:
    def __init__(self, locale: str = "zh"):
        self._messages: Dict[str, str] = {}
        self.locale = locale
        self._load_messages()

    def _load_messages(self):
        locales_dir = find_locales_dir()
        if not locales_dir:
            logger.error("Message resource directory 'locales' not found. UI messages will be unavailable.")
            return

        locale_path = locales_dir / self.locale
        if not locale_path.is_dir():
            logger.error(f"Locale directory for '{self.locale}' not found at {locale_path}")
            return

        for message_file in locale_path.glob("*.json"):
            try:
                with open(message_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._messages.update(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse message file {message_file}: {e}")

        if self._messages:
            logger.debug(f"Successfully loaded {len(self._messages)} messages for locale '{self.locale}'.")

    def get(self, msg_id: str, default: str = "") -> str:
        return self._messages.get(msg_id, default or f"<{msg_id}>")


class Renderer(Protocol):
    def success(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def data(self, data_string: str) -> None: ...


class MessageBus:
    def __init__(self, store: MessageStore):
        self._store = store
        self._renderer: Optional[Renderer] = None

    def set_renderer(self, renderer: Renderer):
        self._renderer = renderer

    def _render(self, level: str, msg_id: str, **kwargs: Any) -> None:
        if not self._renderer:
            logger.warning(f"MessageBus renderer not configured. Dropping message: '{msg_id}'")
            return

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
        template = self._store.get(msg_id)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Formatting error for '{msg_id}': missing key {e}")
            return template

    def data(self, data_string: str) -> None:
        if not self._renderer:
            logger.warning("MessageBus renderer not configured. Dropping data output.")
            return
        self._renderer.data(data_string)


# --- Default Instance ---
# A default instance that can be easily imported and used.
# The renderer will be injected at runtime by the application layer (e.g., CLI).
_default_store = MessageStore(locale="zh")
bus = MessageBus(store=_default_store)
