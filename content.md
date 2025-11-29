## [WIP] refactor: 将 quipu-runtime 迁移到 MessageBus

### 错误分析
当前 `quipu-runtime` 模块（包含 Executor, PluginLoader 和所有 Acts）使用 `logging` 和 `print` 直接进行输出。这导致了：
1.  输出格式不统一（混合了日志格式和原始打印）。
2.  无法支持国际化。
3.  测试依赖于脆弱的字符串匹配 (`caplog`, `capsys`)。
4.  此外，`quipu-runtime` 缺少对 `quipu-common` 的显式依赖声明，这在引入 `MessageBus` 时会导致运行时错误。

### 用户需求
1.  在 `quipu-runtime` 的 `pyproject.toml` 中添加 `quipu-common` 依赖。
2.  在 `locales/zh/cli.json` 中定义所有 Runtime 相关的消息模板。
3.  将 `quipu-runtime` 源码中所有面向用户的 `logging` 和 `print` 调用替换为 `bus` 方法调用。
4.  更新相关测试，使用 `mock_bus` 验证行为。

### 评论
这是一次大规模的横向重构，涉及 `runtime` 包的几乎所有文件。虽然改动面广，但逻辑单一且重复。通过这次重构，我们将彻底完成 MessageBus 在核心执行层的覆盖。

### 目标
1.  修正 `quipu-runtime` 依赖。
2.  统一 Runtime 输出规范。
3.  提升 Runtime 测试的健壮性。

### 基本原理
通过依赖注入单例 `bus`，我们将“输出什么”（语义 ID）和“怎么输出”（TUI/Text/Log）分离。在测试中，利用 `monkeypatch` 拦截 `bus`，使测试不再受 UI 文案变更的影响。

### 标签
#intent/refine #flow/ready #priority/high #comp/runtime #comp/tests #concept/ui #scope/dx #ai/instruct #task/domain/ui #task/object/message-bus #task/action/migration #task/state/continue

---

### Script

#### Acts 1: 添加依赖

首先，确保 `quipu-runtime` 可以合法引用 `quipu-common`。

~~~~~act
patch_file
packages/quipu-runtime/pyproject.toml
~~~~~
~~~~~toml
dependencies = [
    "quipu-interfaces",
    "typer>=0.9.0"
]

[tool.uv.sources]
quipu-interfaces = { workspace = true }
~~~~~
~~~~~toml
dependencies = [
    "quipu-interfaces",
    "quipu-common",
    "typer>=0.9.0"
]

[tool.uv.sources]
quipu-interfaces = { workspace = true }
quipu-common = { workspace = true }
~~~~~

#### Acts 2: 定义消息模板

在资源文件中添加 Runtime 相关的消息 ID。

~~~~~act
patch_file
locales/zh/cli.json
~~~~~
~~~~~json
  "navigation.checkout.prompt.confirm": "🚨 即将重置工作区到状态 {short_hash} ({timestamp})。\n此操作会覆盖未提交的更改。是否继续？",
  "workspace.discard.prompt.confirm": "🚨 即将丢弃上述所有变更，并恢复到状态 {short_hash}。\n此操作不可逆。是否继续？"
}
~~~~~
~~~~~json
  "navigation.checkout.prompt.confirm": "🚨 即将重置工作区到状态 {short_hash} ({timestamp})。\n此操作会覆盖未提交的更改。是否继续？",
  "workspace.discard.prompt.confirm": "🚨 即将丢弃上述所有变更，并恢复到状态 {short_hash}。\n此操作不可逆。是否继续？"

  "runtime.executor.info.starting": "🚀 正在开始执行 {count} 个操作...",
  "runtime.executor.info.executing": "⚙️  正在执行 [{current}/{total}]: {act_name} (模式: {mode}, 参数: {arg_count})",
  "runtime.executor.info.noChange": "🤷 内容无变化，操作已跳过。",
  "runtime.executor.warning.createRootDirFailed": "⚠️  无法创建根目录 {path}: {error}",
  "runtime.executor.warning.noConfirmHandler": "⚠️  无确认处理器，已跳过需要用户确认的操作。",
  "runtime.executor.warning.skipEmpty": "⚠️  跳过空指令 [{current}/{total}]",
  "runtime.executor.warning.skipUnknown": "⚠️  跳过未知操作 [{current}/{total}]: {act_name}",
  "runtime.executor.warning.ignoreInlineArgs": "⚠️  [{act_name}] 模式为 block_only，已忽略行内参数: {args}",

  "runtime.plugin.info.loading": "🔍 正在从 '{plugin_dir}' 加载插件...",
  "runtime.plugin.warning.notDirectory": "⚠️  路径 '{path}' 不是目录，跳过插件加载。",
  "runtime.plugin.error.specFailed": "❌ 无法为 {file_path} 创建模块规范",
  "runtime.plugin.error.loadFailed": "❌ 加载插件 {plugin_name} 失败: {error}",

  "acts.basic.success.fileWritten": "✅ [写入] 文件已写入: {path}",
  "acts.basic.success.filePatched": "✅ [更新] 文件内容已更新: {path}",
  "acts.basic.success.fileAppended": "✅ [追加] 内容已追加到: {path}",

  "acts.check.success.filesExist": "✅ [检查] 所有指定文件均存在。",
  "acts.check.success.cwdMatched": "✅ [检查] 工作区目录匹配: {path}",

  "acts.git.success.initialized": "✅ [Git] 已初始化仓库: {path}",
  "acts.git.success.added": "✅ [Git] 已添加文件: {targets}",
  "acts.git.success.committed": "✅ [Git] 提交成功: {message}",
  "acts.git.warning.repoExists": "⚠️  Git 仓库已存在，跳过初始化。",
  "acts.git.warning.commitSkipped": "⚠️  [Git] 没有暂存的更改，跳过提交。",

  "acts.memory.success.thoughtLogged": "🧠 [记忆] 思维已记录到 .quipu/memory.md",

  "acts.read.info.searching": "🔍 [搜索] 模式: '{pattern}' 于 {path}",
  "acts.read.info.useRipgrep": "⚡ 使用 'rg' (ripgrep) 进行高性能搜索。",
  "acts.read.info.noMatchRipgrep": "🤷 (rg) 未找到匹配项。",
  "acts.read.info.usePythonSearch": "🐢 使用原生 Python 搜索 (回退模式)。",
  "acts.read.info.noMatchPython": "🤷 (Python) 未找到匹配项。",
  "acts.read.info.readingFile": "📖 [读取] 正在读取 {filename}...",
  "acts.read.info.listingTree": "📂 [列表] 目录树: {path}",
  "acts.read.info.listingDir": "📂 [列表] 目录内容: {path}",
  "acts.read.warning.ripgrepFailed": "⚠️  ripgrep 执行出错，回退到 Python 搜索: {error}",
  "acts.read.error.readFailed": "❌ [读取] 无法读取二进制或非 UTF-8 文件: {filename}",

  "acts.refactor.success.moved": "✅ [移动] 已移动/重命名: {source} -> {destination}",
  "acts.refactor.success.deleted": "🗑️  [删除] 已删除: {path}",
  "acts.refactor.warning.deleteSkipped": "⚠️  文件不存在，跳过删除: {path}",

  "acts.shell.info.executing": "🚀 [Shell] 正在执行: {command}",
  "acts.shell.warning.stderrOutput": "⚠️  [Stderr]:\n{output}"
}
~~~~~

#### Acts 3: 迁移 `quipu-runtime` 核心组件

修改 `Executor` 和 `PluginLoader`。

~~~~~act
write_file
packages/quipu-runtime/src/quipu/runtime/plugin_loader.py
~~~~~
~~~~~python
import importlib.util
import logging
import sys
from pathlib import Path
from quipu.common.messaging import bus
from .executor import Executor

logger = logging.getLogger(__name__)


def load_plugins(executor: Executor, plugin_dir: Path):
    """
    动态扫描、导入并注册所有插件模块。

    改进版：不再依赖 sys.path 和包名，而是直接通过文件路径加载模块。
    这允许加载任意位置的插件，哪怕文件夹名称相同（如都叫 'acts'）。
    """
    if not plugin_dir.exists():
        return

    bus.info("runtime.plugin.info.loading", plugin_dir=plugin_dir)

    # 确保是一个目录
    if not plugin_dir.is_dir():
        bus.warning("runtime.plugin.warning.notDirectory", path=plugin_dir)
        return

    # 扫描目录下所有 .py 文件
    for file_path in plugin_dir.glob("*.py"):
        # 跳过私有模块和 __init__.py (除非你需要在 init 里做特殊注册，通常插件是独立的)
        if file_path.name.startswith("_"):
            continue

        # 构造唯一的模块名称，防止冲突
        # 格式: quipu_plugin.{parent_dir_hash}.{filename}
        # 这里简单使用全路径哈希或替换字符来保证唯一性
        safe_name = f"quipu_plugin_{file_path.stem}_{abs(hash(str(file_path)))}"

        try:
            # 使用 importlib.util 从文件路径直接加载
            spec = importlib.util.spec_from_file_location(safe_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                # 必须在执行前加入 sys.modules，防止模块内部互相引用出错
                sys.modules[safe_name] = module
                spec.loader.exec_module(module)

                # 查找约定的 'register' 函数
                if hasattr(module, "register"):
                    register_func = getattr(module, "register")
                    register_func(executor)
                    logger.debug(f"✅ 成功加载插件: {file_path.name}")
                else:
                    # 静默跳过没有 register 的辅助文件
                    pass
            else:
                bus.error("runtime.plugin.error.specFailed", file_path=file_path)

        except Exception as e:
            bus.error("runtime.plugin.error.loadFailed", plugin_name=file_path.name, error=e)
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/runtime/executor.py
~~~~~
~~~~~python
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
import shlex

from quipu.common.messaging import bus
from quipu.interfaces.types import Statement, ActFunction, ActContext
from quipu.interfaces.exceptions import ExecutionError, OperationCancelledError

logger = logging.getLogger(__name__)


# 定义确认处理器的签名: (diff_lines: List[str], prompt_message: str) -> bool
ConfirmationHandler = Callable[[List[str], str], bool]


class Executor:
    """
    执行器：负责管理可用的 Act 并执行解析后的语句。
    维护文件操作的安全边界。
    """

    def __init__(
        self,
        root_dir: Path,
        yolo: bool = False,
        confirmation_handler: Optional[ConfirmationHandler] = None,
    ):
        self.root_dir = root_dir.resolve()
        self.yolo = yolo
        self.confirmation_handler = confirmation_handler
        # Map: name -> (func, arg_mode, summarizer)
        self._acts: Dict[str, tuple[ActFunction, str, Any]] = {}

        if not self.root_dir.exists():
            try:
                self.root_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                bus.warning("runtime.executor.warning.createRootDirFailed", path=self.root_dir, error=e)

    def register(self, name: str, func: ActFunction, arg_mode: str = "hybrid", summarizer: Any = None):
        """
        注册一个新的操作
        :param arg_mode: 参数解析模式
                         - "hybrid": (默认) 合并行内参数和块内容 (inline + blocks)
                         - "exclusive": 互斥模式。优先使用行内参数；若无行内参数，则使用块内容。绝不混合。
                         - "block_only": 仅使用块内容，强制忽略行内参数。
        :param summarizer: 可选的 Summarizer 函数 (args, context_blocks) -> str
        """
        valid_modes = {"hybrid", "exclusive", "block_only"}
        if arg_mode not in valid_modes:
            raise ValueError(f"Invalid arg_mode: {arg_mode}. Must be one of {valid_modes}")

        self._acts[name] = (func, arg_mode, summarizer)
        logger.debug(f"注册 Act: {name} (Mode: {arg_mode})")

    def get_registered_acts(self) -> Dict[str, str]:
        """获取所有已注册的 Act 及其文档字符串"""
        return {name: data[0].__doc__ for name, data in self._acts.items()}

    def summarize_statement(self, stmt: Statement) -> str | None:
        """
        尝试为给定的语句生成摘要。
        如果找不到 Act 或 Act 没有 summarizer，返回 None。
        """
        raw_act_line = stmt["act"]
        try:
            tokens = shlex.split(raw_act_line)
        except ValueError:
            return None

        if not tokens:
            return None

        act_name = tokens[0]
        inline_args = tokens[1:]
        contexts = stmt["contexts"]

        if act_name not in self._acts:
            return None

        _, _, summarizer = self._acts[act_name]

        if not summarizer:
            return None

        try:
            return summarizer(inline_args, contexts)
        except Exception as e:
            # Summarizer 失败不应影响主流程，仅记录日志
            logger.warning(f"Summarizer for '{act_name}' failed: {e}")
            return None

    def resolve_path(self, rel_path: str) -> Path:
        """
        将相对路径转换为基于 root_dir 的绝对路径。
        包含基本的路径逃逸检查。
        """
        clean_rel = rel_path.strip()
        abs_path = (self.root_dir / clean_rel).resolve()

        if not str(abs_path).startswith(str(self.root_dir)):
            raise ExecutionError(f"安全警告：路径 '{clean_rel}' 试图访问工作区外部: {abs_path}")

        return abs_path

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str):
        """
        生成 diff 并请求用户确认。
        如果 self.yolo 为 True, 则直接返回。
        如果用户取消或环境不支持，此方法将抛出 OperationCancelledError。
        """
        if self.yolo:
            return

        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        if not diff:
            bus.info("runtime.executor.info.noChange")
            return

        if not self.confirmation_handler:
            bus.warning("runtime.executor.warning.noConfirmHandler")
            raise OperationCancelledError("No confirmation handler is configured.")

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"
        # 此调用现在要么成功返回，要么抛出 OperationCancelledError
        self.confirmation_handler(diff, prompt)

    def execute(self, statements: List[Statement]):
        """执行一系列语句"""
        bus.info("runtime.executor.info.starting", count=len(statements))

        # 创建一个可重用的上下文对象
        ctx = ActContext(self)

        for i, stmt in enumerate(statements):
            raw_act_line = stmt["act"]
            block_contexts = stmt["contexts"]

            try:
                tokens = shlex.split(raw_act_line)
            except ValueError as e:
                raise ExecutionError(f"Error parsing Act command line: {raw_act_line} ({e})")

            if not tokens:
                bus.warning("runtime.executor.warning.skipEmpty", current=i + 1, total=len(statements))
                continue

            act_name = tokens[0]
            inline_args = tokens[1:]

            if act_name not in self._acts:
                bus.warning(
                    "runtime.executor.warning.skipUnknown",
                    current=i + 1,
                    total=len(statements),
                    act_name=act_name,
                )
                continue

            func, arg_mode, _ = self._acts[act_name]

            final_args = []
            if arg_mode == "hybrid":
                final_args = inline_args + block_contexts
            elif arg_mode == "exclusive":
                if inline_args:
                    final_args = inline_args
                    if block_contexts:
                        logger.debug(
                            f"ℹ️  [{act_name} - Exclusive] Inline args detected, ignoring {len(block_contexts)} subsequent Block(s)."
                        )
                else:
                    final_args = block_contexts
            elif arg_mode == "block_only":
                if inline_args:
                    bus.warning("runtime.executor.warning.ignoreInlineArgs", act_name=act_name, args=inline_args)
                final_args = block_contexts

            try:
                bus.info(
                    "runtime.executor.info.executing",
                    current=i + 1,
                    total=len(statements),
                    act_name=act_name,
                    mode=arg_mode,
                    arg_count=len(final_args),
                )
                # 传递上下文对象，而不是 executor 实例
                func(ctx, final_args)
            except OperationCancelledError:
                # 显式地重新抛出，以确保它能被上层捕获
                raise
            except Exception as e:
                # 记录详细日志供调试，同时抛出标准错误供上层展示
                logger.error(f"Execution failed for '{act_name}': {e}")
                raise ExecutionError(f"An error occurred while executing '{act_name}': {e}") from e
~~~~~

#### Acts 4: 迁移所有 Acts

将 `acts/*.py` 中的 `logging` 和 `print` 替换为 `bus`。

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/basic.py
~~~~~
~~~~~python
import os
from pathlib import Path
from typing import List
import logging
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册基础文件系统操作"""
    executor.register("write_file", _write_file, arg_mode="hybrid", summarizer=_summarize_write)
    executor.register("patch_file", _patch_file, arg_mode="hybrid", summarizer=_summarize_patch_file)
    executor.register("append_file", _append_file, arg_mode="hybrid", summarizer=_summarize_append)
    executor.register("end", _end, arg_mode="hybrid")
    executor.register("echo", _echo, arg_mode="hybrid")


def _summarize_write(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Write: {path}"


def _summarize_patch_file(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"patch_file in: {path}"


def _summarize_append(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Append to: {path}"


def _end(ctx: ActContext, args: List[str]):
    """
    Act: end
    Args: [ignored_contexts...]
    说明: 这是一个空操作。
    它的作用是显式结束上一个指令的参数收集。
    解析器会将后续的 block 视为 end 的参数，而 end 函数会忽略它们。
    """
    pass


def _echo(ctx: ActContext, args: List[str]):
    """
    Act: echo
    Args: [content]
    """
    if len(args) < 1:
        ctx.fail("echo 需要至少一个参数: [content]")

    bus.data(args[0])


def _write_file(ctx: ActContext, args: List[str]):
    """
    Act: write_file
    Args: [path, content]
    """
    if len(args) < 2:
        ctx.fail("write_file 需要至少两个参数: [path, content]")

    raw_path = args[0]
    content = args[1]

    target_path = ctx.resolve_path(raw_path)

    old_content = ""
    if target_path.exists():
        try:
            old_content = target_path.read_text(encoding="utf-8")
        except Exception:
            old_content = "[Binary or Unreadable]"

    ctx.request_confirmation(target_path, old_content, content)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
    except PermissionError:
        ctx.fail(f"写入文件失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"写入文件时发生未知错误: {e}")

    bus.success("acts.basic.success.fileWritten", path=target_path.relative_to(ctx.root_dir))


def _patch_file(ctx: ActContext, args: List[str]):
    """
    Act: patch_file
    Args: [path, old_string, new_string]
    """
    if len(args) < 3:
        ctx.fail("patch_file 需要至少三个参数: [path, old_string, new_string]")

    raw_path, old_str, new_str = args[0], args[1], args[2]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(f"文件未找到: {raw_path}")

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as e:
        ctx.fail(f"读取文件 {raw_path} 失败: {e}")

    if old_str not in content:
        ctx.fail(f"在文件 {raw_path} 中未找到指定的旧文本。\n请确保 Markdown 块中的空格和换行完全匹配。")

    new_content = content.replace(old_str, new_str, 1)

    ctx.request_confirmation(target_path, content, new_content)

    try:
        target_path.write_text(new_content, encoding="utf-8")
    except PermissionError:
        ctx.fail(f"替换文件内容失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"更新文件时发生未知错误: {e}")

    bus.success("acts.basic.success.filePatched", path=target_path.relative_to(ctx.root_dir))


def _append_file(ctx: ActContext, args: List[str]):
    """
    Act: append_file
    Args: [path, content]
    """
    if len(args) < 2:
        ctx.fail("append_file 需要至少两个参数: [path, content]")

    raw_path, content_to_append = args[0], args[1]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(f"文件不存在，无法追加: {raw_path}")

    old_content = ""
    try:
        old_content = target_path.read_text(encoding="utf-8")
    except Exception:
        old_content = "[Binary or Unreadable]"

    new_content = old_content + content_to_append

    ctx.request_confirmation(target_path, old_content, new_content)

    try:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(content_to_append)
    except PermissionError:
        ctx.fail(f"追加文件内容失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"追加文件时发生未知错误: {e}")

    bus.success("acts.basic.success.fileAppended", path=target_path.relative_to(ctx.root_dir))
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/check.py
~~~~~
~~~~~python
import os
from pathlib import Path
from typing import List
import logging
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册检查类操作"""
    executor.register("check_files_exist", _check_files_exist, arg_mode="exclusive")
    executor.register("check_cwd_match", _check_cwd_match, arg_mode="exclusive")


def _check_files_exist(ctx: ActContext, args: List[str]):
    """
    Act: check_files_exist
    Args: [file_list_string]
    说明: 检查当前工作区内是否存在指定的文件。文件名通过换行符分隔。
    """
    if len(args) < 1:
        ctx.fail("check_files_exist 需要至少一个参数: [file_list_string]")

    raw_files = args[0].strip().split("\n")
    missing_files = []

    for raw_path in raw_files:
        clean_path = raw_path.strip()
        if not clean_path:
            continue

        target_path = ctx.resolve_path(clean_path)
        if not target_path.exists():
            missing_files.append(clean_path)

    if missing_files:
        msg = f"❌ [Check] 以下文件在工作区中未找到:\n" + "\n".join(f"  - {f}" for f in missing_files)
        ctx.fail(msg)

    bus.success("acts.check.success.filesExist")


def _check_cwd_match(ctx: ActContext, args: List[str]):
    """
    Act: check_cwd_match
    Args: [expected_absolute_path]
    说明: 检查当前运行的工作区根目录是否与预期的绝对路径匹配。
    """
    if len(args) < 1:
        ctx.fail("check_cwd_match 需要至少一个参数: [expected_absolute_path]")

    expected_path_str = args[0].strip()
    current_root = ctx.root_dir.resolve()
    expected_path = Path(os.path.expanduser(expected_path_str)).resolve()

    if current_root != expected_path:
        ctx.fail(f"❌ [Check] 工作区目录不匹配!\n  预期: {expected_path}\n  实际: {current_root}")

    bus.success("acts.check.success.cwdMatched", path=current_root)
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/git.py
~~~~~
~~~~~python
import subprocess
import logging
import os
from typing import List
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册 Git 相关操作"""
    executor.register("git_init", _git_init, arg_mode="exclusive")
    executor.register("git_add", _git_add, arg_mode="exclusive")
    executor.register("git_commit", _git_commit, arg_mode="block_only", summarizer=_summarize_commit)
    executor.register("git_status", _git_status, arg_mode="exclusive")


def _summarize_commit(args: List[str], contexts: List[str]) -> str:
    msg = contexts[0] if contexts else "No message"
    # Keep it short
    summary = (msg[:50] + "...") if len(msg) > 50 else msg
    return f"Git Commit: {summary}"


def _run_git_cmd(ctx: ActContext, cmd_args: List[str]) -> str:
    """在工作区根目录执行 git 命令的辅助函数。"""
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        result = subprocess.run(
            ["git"] + cmd_args, cwd=ctx.root_dir, capture_output=True, text=True, check=True, env=env
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        # 使用 ctx.fail 来抛出标准化的异常
        ctx.fail(f"Git 命令执行失败: git {' '.join(cmd_args)}\n错误信息: {error_msg}")
    except FileNotFoundError:
        ctx.fail("未找到 git 命令，请确保系统已安装 Git。")
    # 确保函数总有返回值，即使 ctx.fail 会抛异常
    return ""


def _git_init(ctx: ActContext, args: List[str]):
    """
    Act: git_init
    Args: []
    """
    if (ctx.root_dir / ".git").exists():
        bus.warning("acts.git.warning.repoExists")
        return
    _run_git_cmd(ctx, ["init"])
    bus.success("acts.git.success.initialized", path=ctx.root_dir)


def _git_add(ctx: ActContext, args: List[str]):
    """
    Act: git_add
    Args: [files]
    """
    targets = []
    if not args:
        targets = ["."]
    else:
        for arg in args:
            targets.extend(arg.split())
    if not targets:
        targets = ["."]
    _run_git_cmd(ctx, ["add"] + targets)
    bus.success("acts.git.success.added", targets=targets)


def _git_commit(ctx: ActContext, args: List[str]):
    """
    Act: git_commit
    Args: [message]
    """
    if len(args) < 1:
        ctx.fail("git_commit 需要至少一个参数: [message]")

    message = args[0]

    status = _run_git_cmd(ctx, ["status", "--porcelain"])
    if not status:
        bus.warning("acts.git.warning.commitSkipped")
        return

    ctx.request_confirmation(ctx.root_dir / ".git", "Staged Changes", f"Commit Message: {message}")

    _run_git_cmd(ctx, ["commit", "-m", message])
    bus.success("acts.git.success.committed", message=message)


def _git_status(ctx: ActContext, args: List[str]):
    """
    Act: git_status
    Args: []
    """
    status = _run_git_cmd(ctx, ["status"])
    bus.data(status)
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/memory.py
~~~~~
~~~~~python
import logging
from typing import List
from datetime import datetime
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册记忆与日志操作"""
    executor.register("log_thought", _log_thought, arg_mode="block_only")


def _log_thought(ctx: ActContext, args: List[str]):
    """
    Act: log_thought
    Args: [content]
    说明: 将思维过程追加到 .quipu/memory.md 文件中，用于长期记忆。
    """
    if len(args) < 1:
        ctx.fail("log_thought 需要内容参数")

    content = args[0]

    memory_dir = ctx.root_dir / ".quipu"
    memory_dir.mkdir(exist_ok=True)

    memory_file = memory_dir / "memory.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## [{timestamp}]\n{content}\n"

    try:
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        ctx.fail(f"无法写入记忆文件: {e}")

    bus.success("acts.memory.success.thoughtLogged")
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/read.py
~~~~~
~~~~~python
import os
import shutil
import subprocess
import re
import argparse
from pathlib import Path
from typing import List
import logging
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor
from quipu.interfaces.exceptions import ExecutionError

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册读取与检索操作"""
    executor.register("read_file", _read_file, arg_mode="hybrid")
    executor.register("list_files", _list_files, arg_mode="exclusive")
    executor.register("search_files", _search_files, arg_mode="exclusive")


class SafeArgumentParser(argparse.ArgumentParser):
    """覆盖 ArgumentParser 以抛出 ExecutionError。"""

    def error(self, message):
        raise ExecutionError(f"参数解析错误: {message}")

    def exit(self, status=0, message=None):
        if message:
            raise ExecutionError(message)


def _search_files(ctx: ActContext, args: List[str]):
    """
    Act: search_files
    Args: pattern [--path PATH]
    """
    parser = SafeArgumentParser(prog="search_files", add_help=False)
    parser.add_argument("pattern", help="搜索内容的正则表达式")
    parser.add_argument("--path", "-p", default=".", help="搜索的根目录")

    try:
        parsed_args = parser.parse_args(args)
    except ExecutionError as e:
        ctx.fail(str(e))
    except Exception as e:
        ctx.fail(f"参数解析异常: {e}")

    search_path = ctx.resolve_path(parsed_args.path)
    if not search_path.exists():
        ctx.fail(f"搜索路径不存在: {search_path}")

    bus.info("acts.read.info.searching", pattern=parsed_args.pattern, path=search_path)

    if shutil.which("rg"):
        bus.info("acts.read.info.useRipgrep")
        try:
            cmd = ["rg", "-n", "--no-heading", "--color=never", parsed_args.pattern, str(search_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.root_dir)
            if result.stdout:
                bus.data(result.stdout.strip())
            else:
                bus.info("acts.read.info.noMatchRipgrep")
            return
        except Exception as e:
            bus.warning("acts.read.warning.ripgrepFailed", error=str(e))

    bus.info("acts.read.info.usePythonSearch")
    _python_search(ctx, search_path, parsed_args.pattern)


def _python_search(ctx: ActContext, start_path: Path, pattern_str: str):
    try:
        regex = re.compile(pattern_str)
    except re.error as e:
        ctx.fail(f"无效的正则表达式: {pattern_str} ({e})")

    matches = []
    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"}]
        for file in files:
            file_path = Path(root) / file
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            clean_line = line.strip()
                            # 关键修复：路径始终相对于项目根目录，以保证输出一致性
                            relative_path = file_path.relative_to(ctx.root_dir)
                            matches.append(f"{relative_path}:{i}:{clean_line[:200]}")
            except (UnicodeDecodeError, PermissionError):
                continue

    if matches:
        bus.data("\n".join(matches))
    else:
        bus.info("acts.read.info.noMatchPython")


def _read_file(ctx: ActContext, args: List[str]):
    """
    Act: read_file
    Args: [path]
    """
    if not args:
        ctx.fail("read_file 需要一个参数: [path]")

    target_path = ctx.resolve_path(args[0])
    if not target_path.exists():
        ctx.fail(f"文件不存在: {args[0]}")
    if target_path.is_dir():
        ctx.fail(f"这是一个目录，请使用 list_files: {args[0]}")

    try:
        content = target_path.read_text(encoding="utf-8")
        bus.info("acts.read.info.readingFile", filename=target_path.name)
        bus.data(content)
    except UnicodeDecodeError:
        bus.error("acts.read.error.readFailed", filename=args[0])
    except Exception as e:
        ctx.fail(f"读取文件失败: {e}")


def _list_files(ctx: ActContext, args: List[str]):
    """
    Act: list_files
    Args: [path] [--tree]
    """
    parser = SafeArgumentParser(prog="list_files", add_help=False)
    parser.add_argument("path", nargs="?", default=".", help="目标目录")
    parser.add_argument("--tree", "-t", action="store_true", help="以树状结构递归显示")

    try:
        parsed_args = parser.parse_args(args)
    except Exception as e:
        ctx.fail(f"参数解析异常: {e}")

    target_dir = ctx.resolve_path(parsed_args.path)
    if not target_dir.is_dir():
        ctx.fail(f"目录不存在或不是目录: {target_dir}")

    output = []
    if parsed_args.tree:
        bus.info("acts.read.info.listingTree", path=target_dir)
        # Simplified tree implementation
        for path_object in sorted(target_dir.rglob("*")):
            if ".git" in path_object.parts or ".quipu" in path_object.parts:
                continue
            depth = len(path_object.relative_to(target_dir).parts) - 1
            indent = "    " * depth
            output.append(f"{indent}└── {path_object.name}{'/' if path_object.is_dir() else ''}")
    else:
        bus.info("acts.read.info.listingDir", path=target_dir)
        items = sorted(list(target_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        for item in items:
            if item.name.startswith("."):
                continue
            output.append(f"📁 {item.name}/" if item.is_dir() else f"📄 {item.name}")

    if not output:
        output.append("(Empty directory)")
    bus.data("\n".join(output))
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/refactor.py
~~~~~
~~~~~python
import shutil
from typing import List
import logging
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册重构类操作"""
    executor.register("move_file", _move_file, arg_mode="hybrid")
    executor.register("delete_file", _delete_file, arg_mode="exclusive")


def _move_file(ctx: ActContext, args: List[str]):
    """
    Act: move_file
    Args: [src_path, dest_path]
    """
    if len(args) < 2:
        ctx.fail("move_file 需要两个参数: [src, dest]")

    src_raw, dest_raw = args[0], args[1]
    src_path = ctx.resolve_path(src_raw)
    dest_path = ctx.resolve_path(dest_raw)

    if not src_path.exists():
        ctx.fail(f"源文件不存在: {src_raw}")

    msg = f"Move: {src_raw} -> {dest_raw}"
    ctx.request_confirmation(src_path, f"Source Exists", msg)

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest_path))
    except PermissionError:
        ctx.fail(f"移动/重命名失败: 权限不足。源: '{src_raw}', 目标: '{dest_raw}'")
    except Exception as e:
        ctx.fail(f"移动/重命名时发生未知错误: {e}")
    bus.success("acts.refactor.success.moved", source=src_raw, destination=dest_raw)


def _delete_file(ctx: ActContext, args: List[str]):
    """
    Act: delete_file
    Args: [path]
    """
    if len(args) < 1:
        ctx.fail("delete_file 需要一个参数: [path]")

    raw_path = args[0]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        bus.warning("acts.refactor.warning.deleteSkipped", path=raw_path)
        return

    file_type = "目录 (递归删除!)" if target_path.is_dir() else "文件"
    warning = f"🚨 正在删除{file_type}: {target_path}"

    ctx.request_confirmation(target_path, "EXISTING CONTENT", warning)

    try:
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()
    except PermissionError:
        ctx.fail(f"删除失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"删除时发生未知错误: {e}")

    bus.success("acts.refactor.success.deleted", path=raw_path)
~~~~~

~~~~~act
write_file
packages/quipu-runtime/src/quipu/acts/shell.py
~~~~~
~~~~~python
import subprocess
import logging
from typing import List
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册 Shell 相关操作"""
    executor.register("run_command", _run_command, arg_mode="exclusive")


def _run_command(ctx: ActContext, args: List[str]):
    """
    Act: run_command
    Args: [command_string]
    """
    if len(args) < 1:
        ctx.fail("run_command 需要至少一个参数: [command_string]")

    command = " ".join(args)

    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {ctx.root_dir})"
    ctx.request_confirmation(ctx.root_dir, "System State", warning_msg)

    bus.info("acts.shell.info.executing", command=command)

    try:
        result = subprocess.run(command, cwd=ctx.root_dir, shell=True, capture_output=True, text=True)

        if result.stdout:
            # 结果数据打印到 stdout
            bus.data(result.stdout.strip())
        if result.stderr:
            # 错误/状态信息打印到 stderr
            bus.warning("acts.shell.warning.stderrOutput", output=result.stderr.strip())

        if result.returncode != 0:
            ctx.fail(f"命令执行失败 (Code {result.returncode})")

    except Exception as e:
        ctx.fail(f"Shell 执行异常: {e}")
~~~~~

#### Acts 5: 更新 Runtime 测试

首先通过 `conftest.py` 提供一个默认的 mock bus，这大大简化了测试迁移。

~~~~~act
patch_file
tests/runtime/conftest.py
~~~~~
~~~~~python
import pytest
from pathlib import Path
from quipu.runtime.executor import Executor
from quipu.acts.basic import register as register_basic_acts


@pytest.fixture
def executor(tmp_path: Path) -> Executor:
~~~~~
~~~~~python
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from quipu.runtime.executor import Executor
from quipu.acts.basic import register as register_basic_acts


@pytest.fixture(autouse=True)
def mock_runtime_bus(monkeypatch):
    """
    自动 patch quipu.common.messaging.bus，避免在测试中调用真实的消息总线。
    这确保了 runtime 测试与 CLI 的输出层解耦。
    """
    m_bus = MagicMock()
    # patch quipu.common.messaging.bus，因为 runtime 模块是从那里导入的 bus 对象
    monkeypatch.setattr("quipu.common.messaging.bus", m_bus)
    return m_bus


@pytest.fixture
def executor(tmp_path: Path) -> Executor:
~~~~~

现在更新具体的测试文件，替换掉 `capsys` 和 `caplog` 的断言。

~~~~~act
write_file
tests/runtime/acts/test_check.py
~~~~~
~~~~~python
import pytest
from pathlib import Path
from quipu.runtime.executor import Executor
from quipu.interfaces.exceptions import ExecutionError
from quipu.acts.check import register as register_check_acts
from quipu.interfaces.types import ActContext


class TestCheckActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        """自动为每个测试注册 check acts"""
        register_check_acts(executor)

    def test_check_files_exist_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        (isolated_vault / "config.json").touch()
        (isolated_vault / "src").mkdir()
        (isolated_vault / "src/main.py").touch()

        file_list = "config.json\nsrc/main.py"
        func, _, _ = executor._acts["check_files_exist"]
        ctx = ActContext(executor)
        func(ctx, [file_list])

        mock_runtime_bus.success.assert_called_with("acts.check.success.filesExist")

    def test_check_files_exist_fail(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "exists.txt").touch()
        file_list = "exists.txt\nmissing.txt"

        with pytest.raises(ExecutionError) as excinfo:
            func, _, _ = executor._acts["check_files_exist"]
            ctx = ActContext(executor)
            func(ctx, [file_list])

        msg = str(excinfo.value)
        assert "missing.txt" in msg
        assert "exists.txt" not in msg

    def test_check_cwd_match_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        real_path = str(isolated_vault.resolve())
        func, _, _ = executor._acts["check_cwd_match"]
        ctx = ActContext(executor)
        func(ctx, [real_path])

        mock_runtime_bus.success.assert_called_with("acts.check.success.cwdMatched", path=isolated_vault.resolve())

    def test_check_cwd_match_fail(self, executor: Executor):
        wrong_path = "/this/path/does/not/exist"

        with pytest.raises(ExecutionError) as excinfo:
            func, _, _ = executor._acts["check_cwd_match"]
            ctx = ActContext(executor)
            func(ctx, [wrong_path])

        assert "工作区目录不匹配" in str(excinfo.value)
~~~~~

~~~~~act
write_file
tests/runtime/acts/test_git.py
~~~~~
~~~~~python
import pytest
import subprocess
import shutil
from pathlib import Path
from quipu.runtime.executor import Executor
from quipu.acts.git import register as register_git_acts


@pytest.mark.skipif(not shutil.which("git"), reason="Git 命令未找到，跳过 Git 测试")
class TestGitActs:
    @pytest.fixture(autouse=True)
    def setup_git_env(self, executor: Executor, isolated_vault: Path):
        """为测试环境自动注册 Git Acts 并进行 git init"""
        register_git_acts(executor)

        # 执行初始化
        func, _, _ = executor._acts["git_init"]
        func(executor, [])

        # 配置测试用的 user，防止 CI/Test 环境报错
        subprocess.run(["git", "config", "user.email", "quipu@test.com"], cwd=isolated_vault, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Bot"], cwd=isolated_vault, check=True)

    def test_git_workflow(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        # 1. 创建文件
        target_file = isolated_vault / "README.md"
        target_file.write_text("# Test Repo", encoding="utf-8")

        # 2. Git Add
        git_add, _, _ = executor._acts["git_add"]
        git_add(executor, ["README.md"])
        mock_runtime_bus.success.assert_called_with("acts.git.success.added", targets=["README.md"])

        # 验证状态 (porcelain 输出 ?? 代表未追踪，A 代表已添加)
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=isolated_vault, text=True)
        assert "A  README.md" in status

        # 3. Git Commit
        git_commit, _, _ = executor._acts["git_commit"]
        git_commit(executor, ["Initial commit"])
        mock_runtime_bus.success.assert_called_with("acts.git.success.committed", message="Initial commit")

        # 验证提交日志
        log = subprocess.check_output(["git", "log", "--oneline"], cwd=isolated_vault, text=True)
        assert "Initial commit" in log

    def test_git_init_idempotent(self, executor: Executor, mock_runtime_bus):
        # setup_git_env 已经 init 过了，再次 init 应该提示跳过
        func, _, _ = executor._acts["git_init"]
        func(executor, [])
        mock_runtime_bus.warning.assert_called_with("acts.git.warning.repoExists")

    def test_git_status_output_stream(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        """
        验证 git_status 使用 bus.data 输出数据，而 executor 使用 bus.info 输出进度。
        """
        # 1. 制造一些状态变更
        (isolated_vault / "untracked.txt").write_text("new file")

        # 2. 我们通过 executor.execute 来模拟完整的执行流程
        stmts = [{"act": "git_status", "contexts": []}]
        executor.execute(stmts)

        # 3. 验证 bus 调用
        # 验证执行器日志
        mock_runtime_bus.info.assert_any_call(
            "runtime.executor.info.executing", current=1, total=1, act_name="git_status", mode="exclusive", arg_count=0
        )

        # 验证数据输出
        # args[0] 应该是 status 字符串，包含 untracked.txt
        assert mock_runtime_bus.data.called
        data_arg = mock_runtime_bus.data.call_args[0][0]
        assert "Untracked files" in data_arg
        assert "untracked.txt" in data_arg
~~~~~

~~~~~act
write_file
tests/runtime/acts/test_read.py
~~~~~
~~~~~python
import pytest
import shutil
import logging
from pathlib import Path
from quipu.runtime.executor import Executor, ExecutionError
from quipu.acts.read import register as register_read_acts
from quipu.interfaces.types import ActContext


class TestReadActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_read_acts(executor)

    def test_search_python_fallback(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        target_file = isolated_vault / "config.py"
        target_file.write_text('SECRET_KEY = "123456"', encoding="utf-8")
        (isolated_vault / "readme.md").write_text("Nothing here", encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["SECRET_KEY"])

        mock_runtime_bus.info.assert_any_call("acts.read.info.usePythonSearch")
        
        # 验证数据输出
        assert mock_runtime_bus.data.called
        data_out = mock_runtime_bus.data.call_args[0][0]
        assert "config.py" in data_out
        assert 'SECRET_KEY = "123456"' in data_out

    @pytest.mark.skipif(not shutil.which("rg"), reason="Ripgrep (rg) 未安装，跳过集成测试")
    def test_search_with_ripgrep(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        (isolated_vault / "main.rs").write_text('fn main() { println!("Hello Quipu"); }', encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["println!"])

        mock_runtime_bus.info.assert_any_call("acts.read.info.useRipgrep")
        
        assert mock_runtime_bus.data.called
        data_out = mock_runtime_bus.data.call_args[0][0]
        assert "main.rs" in data_out
        assert 'println!("Hello Quipu")' in data_out

    def test_search_scoped_path(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "target.txt").write_text("target_function", encoding="utf-8")
        src_dir = isolated_vault / "src"
        src_dir.mkdir()
        (src_dir / "inner.txt").write_text("target_function", encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["target_function", "--path", "src"])

        assert mock_runtime_bus.data.called
        stdout = mock_runtime_bus.data.call_args[0][0]

        # After the fix, the path should be relative to the root
        assert str(Path("src") / "inner.txt") in stdout
        assert str(isolated_vault / "target.txt") not in stdout
        assert "target.txt:1:target_function" not in stdout

    def test_search_no_match(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "file.txt").write_text("some content", encoding="utf-8")
        
        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["non_existent_pattern"])
        
        mock_runtime_bus.info.assert_called_with("acts.read.info.noMatchPython")

    def test_search_binary_file_resilience(self, executor: Executor, isolated_vault: Path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        binary_file = isolated_vault / "data.bin"
        binary_file.write_bytes(b"\x80\x81\xff")
        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        try:
            search_func(ctx, ["pattern"])
        except Exception as e:
            pytest.fail(f"搜索过程因二进制文件崩溃: {e}")

    def test_search_args_error(self, executor: Executor):
        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError) as exc:
            search_func(ctx, ["pattern", "--unknown-flag"])
        assert "参数解析错误" in str(exc.value)
~~~~~

~~~~~act
write_file
tests/runtime/test_plugin_loader.py
~~~~~
~~~~~python
import pytest
import sys
from pathlib import Path
from quipu.runtime.executor import Executor
from quipu.runtime.plugin_loader import load_plugins
from quipu.cli.utils import find_git_repository_root


class TestPluginLoading:
    @pytest.fixture
    def custom_plugin_dir(self, tmp_path):
        """创建一个模拟的外部插件目录"""
        plugin_dir = tmp_path / ".quipu" / "acts"
        plugin_dir.mkdir(parents=True)
        return plugin_dir

    def test_load_external_plugin(self, executor: Executor, custom_plugin_dir, mock_runtime_bus):
        """测试从任意路径加载插件文件"""
        # 1. 创建一个动态插件文件
        plugin_file = custom_plugin_dir / "hello_world.py"
        plugin_content = """
def register(executor):
    executor.register("hello_world", lambda exc, args: print("Hello!"))
"""
        plugin_file.write_text(plugin_content, encoding="utf-8")

        # 2. 执行加载
        load_plugins(executor, custom_plugin_dir)

        # 3. 验证是否注册成功
        assert "hello_world" in executor._acts
        
        # 验证消息
        mock_runtime_bus.info.assert_called_with("runtime.plugin.info.loading", plugin_dir=custom_plugin_dir)

        # 验证模块是否被正确隔离加载
        loaded_modules = [m for m in sys.modules.keys() if "quipu_plugin_hello_world" in m]
        assert len(loaded_modules) > 0

    def test_ignore_invalid_files(self, executor: Executor, custom_plugin_dir):
        """测试忽略非 Python 文件和无 register 函数的文件"""
        # 非 py 文件
        (custom_plugin_dir / "readme.md").write_text("# Readme")

        # 无 register 的 py 文件
        (custom_plugin_dir / "helper.py").write_text("def foo(): pass")

        load_plugins(executor, custom_plugin_dir)

        # 应该没有报错，且 acts 列表没有增加
        assert "foo" not in executor._acts

    def test_find_git_repository_root(self, tmp_path):
        """测试 Git 项目根目录检测逻辑"""
        root = tmp_path / "my_project"
        root.mkdir()
        (root / ".git").mkdir()

        subdir = root / "src" / "subdir"
        subdir.mkdir(parents=True)

        found = find_git_repository_root(subdir)
        assert found == root.resolve()

        found_root = find_git_repository_root(root)
        assert found_root == root.resolve()

        orphan = tmp_path / "orphan"
        orphan.mkdir()
        assert find_git_repository_root(orphan) is None
~~~~~

~~~~~act
write_file
tests/runtime/test_plugin_resilience.py
~~~~~
~~~~~python
import pytest
import logging
from pathlib import Path
from unittest.mock import ANY

from quipu.runtime.executor import Executor
from quipu.runtime.plugin_loader import load_plugins


class TestPluginResilience:
    @pytest.fixture
    def executor(self, tmp_path) -> Executor:
        return Executor(root_dir=tmp_path, yolo=True)

    @pytest.fixture
    def plugin_dir(self, tmp_path) -> Path:
        p_dir = tmp_path / "plugins"
        p_dir.mkdir()
        return p_dir

    def test_load_plugin_with_syntax_error(self, executor: Executor, plugin_dir: Path, mock_runtime_bus):
        """验证加载有语法错误的插件不会使程序崩溃。"""
        from quipu.acts.basic import register as register_basic_acts

        # 1. 创建一个有语法错误的插件
        bad_plugin_file = plugin_dir / "bad_syntax.py"
        bad_plugin_file.write_text("def register(executor):\n  print('unbalanced parentheses'", encoding="utf-8")

        # 2. 注册核心 Acts
        register_basic_acts(executor)
        num_acts_before = len(executor.get_registered_acts())

        # 3. 加载插件
        load_plugins(executor, plugin_dir)

        # 4. 验证
        mock_runtime_bus.error.assert_called_with(
            "runtime.plugin.error.loadFailed", plugin_name="bad_syntax.py", error=ANY
        )
        
        num_acts_after = len(executor.get_registered_acts())
        assert num_acts_after == num_acts_before, "不应注册任何新 Act"
        assert "write_file" in executor.get_registered_acts(), "核心 Act 应该仍然存在"

    def test_load_plugin_with_registration_error(self, executor: Executor, plugin_dir: Path, mock_runtime_bus):
        """验证插件在 register() 函数中抛出异常不会使程序崩溃。"""
        # 1. 创建一个在注册时会失败的插件
        bad_plugin_file = plugin_dir / "fail_on_register.py"
        plugin_content = """
def register(executor):
    raise ValueError("Something went wrong during registration")
"""
        bad_plugin_file.write_text(plugin_content, encoding="utf-8")

        # 2. 加载插件
        load_plugins(executor, plugin_dir)

        # 3. 验证
        mock_runtime_bus.error.assert_called_with(
            "runtime.plugin.error.loadFailed", plugin_name="fail_on_register.py", error=ANY
        )
        assert len(executor.get_registered_acts()) == 0
~~~~~

### 下一步建议
Runtime 模块的迁移和测试更新已完成。现在应该运行测试套件以验证这一系列更改的正确性。如果测试通过，我们可以继续进行 Phase 3：`quipu-engine` 的迁移，或者开始整理和优化现有的消息 ID。
