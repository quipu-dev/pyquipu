好的，我们开始实现 `quipu axon` 子命令。

根据设计文档，`quipu axon` 将作为一个无状态的、轻量级的 Markdown 任务执行器。它将复用 `quipu-runtime` 的解析和执行能力，但完全不依赖 `quipu-engine`，不产生任何历史记录。这对于 CI/CD、项目脚手架等场景非常有价值。

我们将按照以下步骤实现：
1.  在 `quipu.cli.utils` 模块中添加一个通用的结果处理器 `handle_result`。
2.  在 `quipu.cli.factory` 模块中创建一个专门用于 `axon` 的、无状态的执行器 (`Executor`) 工厂函数 `create_stateless_executor`。
3.  创建 `quipu.cli.commands.axon` 模块来承载子命令的逻辑。
4.  在主入口 `quipu.cli.main` 中注册这个新的 `axon` 子命令。

这是一个符合“小心翼翼地避免耦合”设计哲学的实现方案。

## [WIP] feat: 实现无状态的 `quipu axon` 子命令

### 用户需求
根据设计文档，需要创建一个 `quipu axon` 子命令，它作为一个独立的、无状态的 Markdown 任务执行器，与 `quipu-engine` 完全解耦。

### 评论
这是一个非常重要的功能，它将 `quipu-runtime` 的通用价值释放出来，使其可以用于 CI/CD、项目脚手架等不关心历史状态的场景，极大地扩展了 Quipu 生态的应用范围。

### 目标
1.  创建一个新的 `quipu axon <plan.md>` 命令。
2.  实现一个仅初始化 `quipu-runtime` 相关组件 (`PluginLoader`, `Executor`) 的工厂函数。
3.  确保 `axon` 命令的执行过程不触及、不加载 `quipu-engine` 或任何历史状态。
4.  在主应用中注册 `axon` 作为一个独立的子命令组。

### 基本原理
通过在 `quipu-cli` 中添加一个新的 `typer.Typer` 应用作为子命令来实现。该子命令的逻辑将调用一个专用的工厂函数，该函数只构造一个无状态的 `Executor`，然后用它来解析和执行用户提供的 Markdown 文件内容。这样就在入口层将有状态 (`quipu run`) 和无状态 (`quipu axon run`) 的逻辑清晰地分离开来。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #comp/runtime #concept/executor #scope/api #ai/instruct #task/domain/cli #task/object/subcommand-axon #task/action/implementation #task/state/begin

---

### Script

#### Acts 1: 增强 `utils` 和 `factory`

我们首先在 `utils.py` 中添加一个辅助函数来处理命令执行结果，然后在 `factory.py` 中添加无状态执行器的工厂函数。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/utils.py
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_git_repository_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
        current = start_path.resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return parent
    except Exception:
        pass
    return None
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Optional

import typer
from quipu.core.result import QuipuResult

logger = logging.getLogger(__name__)


def find_git_repository_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
        current = start_path.resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return parent
    except Exception:
        pass
    return None


def handle_result(result: QuipuResult):
    """Prints a result message to the console and exits."""
    if result.message:
        color = typer.colors.GREEN if result.success else typer.colors.RED
        typer.secho(f"{result.message}", fg=color, err=True)
    if result.data:
        typer.echo(result.data)
    raise typer.Exit(result.exit_code)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/factory.py
~~~~~
~~~~~python
    # 将所有资源注入 Engine
    engine = Engine(project_root, db=git_db, reader=reader, writer=writer, db_manager=db_manager)
    if not lazy:
        engine.align()

    return engine
~~~~~
~~~~~python
    # 将所有资源注入 Engine
    engine = Engine(project_root, db=git_db, reader=reader, writer=writer, db_manager=db_manager)
    if not lazy:
        engine.align()

    return engine


def create_stateless_executor() -> "Executor":
    """
    Creates a stateless Executor instance.

    This executor is configured with core acts and plugins, but it does NOT
    connect to the state engine. It's ideal for `axon` commands.
    """
    # 迟延导入以避免循环依赖
    import sys
    from typing import List
    import typer
    from quipu.core.executor import Executor
    from quipu.acts import register_core_acts
    from .plugin_manager import PluginManager

    def typer_confirmation_handler(diff_lines: List[str], prompt: str) -> bool:
        """A confirmation handler that uses Typer for UI."""
        typer.echo("\n🔍 变更预览:")
        for line in diff_lines:
            if line.startswith("+"):
                typer.secho(line.strip("\n"), fg=typer.colors.GREEN)
            elif line.startswith("-"):
                typer.secho(line.strip("\n"), fg=typer.colors.RED)
            elif line.startswith("^"):
                typer.secho(line.strip("\n"), fg=typer.colors.BLUE)
            else:
                typer.echo(line.strip("\n"))
        typer.echo("")

        if not sys.stdin.isatty():
            logger.warning("非交互式环境，自动跳过确认。")
            return False

        return typer.confirm(prompt, default=True)

    # For a stateless executor, the root_dir is just the current directory.
    executor = Executor(
        root_dir=Path("."),
        yolo=False,
        confirmation_handler=typer_confirmation_handler,
    )

    # Load core acts
    register_core_acts(executor)

    # Load external plugins relative to the current working directory
    plugin_manager = PluginManager()
    plugin_manager.load_from_sources(executor, Path("."))

    return executor
~~~~~

#### Acts 2: 创建 `axon` 命令模块

现在创建 `axon.py` 文件，它将包含 `axon run` 命令的全部逻辑。

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/commands/axon.py
~~~~~
~~~~~python
import logging
from pathlib import Path
import typer
from typing_extensions import Annotated

from quipu.core.result import QuipuResult
from ..factory import create_stateless_executor
from ..utils import handle_result

logger = logging.getLogger(__name__)

axon_app = typer.Typer(
    help="""
    A stateless Markdown task runner.

    This command executes a '.md' file containing Quipu 'act' blocks
    without creating any history or interacting with the state engine.
    It's ideal for CI/CD, automation scripts, and project scaffolding.
    """,
    no_args_is_help=True,
)


@axon_app.command(name="run", help="Execute a stateless plan file.")
def run_plan(
    plan_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to the stateless plan file (.md) to execute.",
        ),
    ]
):
    """
    Parses and executes a given Markdown file.
    """
    logger.info(f"⚡️  Axon: Executing stateless plan from '{plan_file.name}'...")
    try:
        content = plan_file.read_text(encoding="utf-8")
        if not content.strip():
            handle_result(QuipuResult(success=False, exit_code=1, message="Plan file is empty."))
            return

        executor = create_stateless_executor()
        result = executor.execute_content(content)
        handle_result(result)

    except Exception as e:
        logger.error(f"❌ An unexpected error occurred during Axon execution: {e}", exc_info=True)
        handle_result(QuipuResult(success=False, exit_code=1, message=str(e), error=e))
~~~~~

#### Acts 3: 修正 `axon` 命令中的方法调用

`Executor` 没有 `execute_content` 方法，正确的方法是先解析再执行。我将修正 `axon.py` 中的这个错误。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/axon.py
~~~~~
~~~~~python
        executor = create_stateless_executor()
        result = executor.execute_content(content)
        handle_result(result)

    except Exception as e:
~~~~~
~~~~~python
        # Stateless execution is a two-step process: parse then execute.
        from quipu.core.parser import detect_best_parser, get_parser
        from quipu.core.exceptions import ExecutionError as CoreExecutionError

        try:
            parser_name = detect_best_parser(content)
            parser = get_parser(parser_name)
            statements = parser.parse(content)

            if not statements:
                handle_result(
                    QuipuResult(
                        success=True, exit_code=0, message="No executable 'act' blocks found in the plan file."
                    )
                )
                return

            executor = create_stateless_executor()
            executor.execute(statements)
            handle_result(QuipuResult(success=True, exit_code=0, message="✅ Axon plan executed successfully."))

        except CoreExecutionError as e:
            handle_result(QuipuResult(success=False, exit_code=1, message=str(e), error=e))
        except Exception as e:
            logger.error(f"❌ An unexpected error occurred during Axon execution: {e}", exc_info=True)
            handle_result(QuipuResult(success=False, exit_code=1, message=str(e), error=e))
~~~~~

#### Acts 4: 注册 `axon` 子命令

最后，我们在 `main.py` 中注册 `axon_app`，使其成为 `quipu` 的一个子命令。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
import logging
import typer
from .commands import cache, navigation, query, remote, run, ui, workspace

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~
~~~~~python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
# --- Command Registration ---
# 注册子命令应用
app.add_typer(cache.cache_app)

# 注册顶级命令
workspace.register(app)
~~~~~
~~~~~python
# --- Command Registration ---
# 注册子命令应用
app.add_typer(axon.axon_app, name="axon")
app.add_typer(cache.cache_app)

# 注册顶级命令
workspace.register(app)
~~~~~

### 下一步建议
现在 `quipu axon` 命令的基础框架已经搭建完成。下一步，我们应该为其编写专门的集成测试，以确保其无状态执行的纯粹性，并验证它能正确加载插件和处理各种 Markdown 输入。
