好的，我将执行重构计划的第一阶段：解耦 `MessageBus` 与 `Renderer`。

这个重构是后续所有工作的基础。它将 `quipu-common` 包中的 UI 渲染逻辑 (`TyperRenderer`) 剥离，并迁移到 `quipu-cli` 包中，从而使 `quipu-common` 成为一个与 UI 无关的纯逻辑库。`quipu-cli` 作为应用程序层，将在启动时负责注入具体的渲染器实现。

## [WIP] refactor: 解耦 MessageBus 与 Renderer

### 用户需求
根据 `MessageBug重构.md` 计划，执行第一阶段的架构重构。核心目标是将 `quipu-common` 包中的 `MessageBus` 与 `Typer` 的具体实现解耦。`TyperRenderer` 应该被移动到 `quipu-cli` 中，而 `MessageBus` 则通过依赖注入的方式在运行时接收一个 `Renderer` 实例。

### 评论
这是一个关键的架构改进，它遵循了依赖倒置原则。通过这次重构，`quipu-common` 将不再依赖任何 UI 框架，提升了其通用性和可复用性。同时，这也使得 `MessageBus` 的测试变得更加简单，因为我们可以轻易地注入一个模拟的 `Renderer`。

### 目标
1.  在 `quipu-cli` 包中创建一个新的 `rendering.py` 模块，用于存放 `TyperRenderer`。
2.  修改 `quipu-common` 中的 `MessageBus`，使其不再包含任何 `Typer` 相关的代码，并通过一个 `set_renderer` 方法接收渲染器实例。
3.  移除 `quipu-common` 对 `typer` 的依赖。
4.  在 `quipu-cli` 的主入口 (`main.py`) 配置全局的 `bus` 实例，为其注入 `TyperRenderer`。

### 基本原理
我们将 `TyperRenderer` (一个实现细节) 从 `quipu-common` (一个通用库) 移动到 `quipu-cli` (一个具体的应用程序)。`quipu-common` 中的全局 `bus` 实例将在创建时不包含渲染器。`quipu-cli` 应用在启动时，会创建 `TyperRenderer` 的实例，并通过 `bus.set_renderer()` 方法将其“注入”到 `bus` 中。这样，程序的其余部分就可以像以前一样使用 `bus`，而无需关心其内部是如何配置的。

### 标签
#intent/refine #flow/ready #priority/critical #comp/cli #comp/common #concept/ui #scope/core #ai/instruct #task/domain/cli #task/object/message-bus #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 在 `quipu-cli` 中创建新的渲染模块

我们将 `Renderer` 协议和 `TyperRenderer` 的实现代码移动到一个位于 `quipu-cli` 包内的新文件中。

```````act
write_file
packages/quipu-cli/src/quipu/cli/rendering.py
```````
```````python
from typing import Protocol
import typer


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
```````

#### Acts 2: 重构 `quipu-common` 的 `MessageBus`

现在，我们修改 `quipu.common.messaging.bus`，移除所有与 `Typer` 相关的代码，并调整 `MessageBus` 的初始化和渲染逻辑。

```````act
patch_file
packages/quipu-common/src/quipu/common/messaging/bus.py
```````
```````python
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
```````
```````python
import json
import logging
from pathlib import Path
from typing import Dict, Any, Protocol, Optional

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


class MessageBus:
    """The central service for all user-facing CLI output."""

    def __init__(self, store: MessageStore):
        self._store = store
        self._renderer: Optional[Renderer] = None

    def set_renderer(self, renderer: Renderer):
        """Injects a concrete renderer implementation."""
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
        """Retrieves and formats a message string without rendering it."""
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
```````

#### Acts 3: 移除 `quipu-common` 的 `typer` 依赖

由于 `TyperRenderer` 已被移除，我们现在可以安全地从 `quipu-common` 的 `pyproject.toml` 中删除 `typer` 依赖。

```````act
patch_file
packages/quipu-common/pyproject.toml
```````
```````toml
[project]
name = "quipu-common"
version = "0.1.0"
authors = [
  { name="doucx", email="doucxldh@gmail.com" },
]
description = "Common utilities and helpers for the Quipu ecosystem."
requires-python = ">=3.8"
license = { text = "Apache-2.0" }
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
]
dependencies = [
    "typer>=0.9.0"
]

[tool.setuptools.packages.find]
```````
```````toml
[project]
name = "quipu-common"
version = "0.1.0"
authors = [
  { name="doucx", email="doucxldh@gmail.com" },
]
description = "Common utilities and helpers for the Quipu ecosystem."
requires-python = ">=3.8"
license = { text = "Apache-2.0" }
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
]
dependencies = []

[tool.setuptools.packages.find]
```````

#### Acts 4: 在 `quipu-cli` 入口注入渲染器

最后，我们在 `quipu-cli` 的主入口文件 `main.py` 中，将 `TyperRenderer` 注入到全局 `bus` 实例中。

```````act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
```````
```````python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show, export

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)

# --- App Definition ---
app = typer.Typer(
```````
```````python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show, export
from .rendering import TyperRenderer
from quipu.common.messaging import bus

# --- Global Setup ---
# Inject the CLI-specific renderer into the common message bus instance.
# This must be done once at the application's entry point.
bus.set_renderer(TyperRenderer())

# Initialize logger, but handler configuration (stderr or file)
# is determined by specific commands at runtime.
logging.getLogger(__name__)


# --- App Definition ---
app = typer.Typer(
```````

### 下一步建议
我们已经成功完成了架构重构的第一阶段。`MessageBus` 现在与 `Typer` 完全解耦，为后续的迁移工作奠定了坚实的基础。

下一步，我们将开始 **Phase 2: 迁移 `quipu-runtime`**。这将涉及分析 `acts` 和 `executor` 中的 `logging` 调用，为它们创建消息 ID，并用 `bus` 调用替换它们。这将是 `MessageBus` 价值的第一次大规模体现。
