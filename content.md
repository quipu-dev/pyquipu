好的，我们开始实施。

此任务的目标是创建一个新的 `quipu export` 命令，它能够将 Quipu 历史记录导出为一组结构化的 Markdown 文件，并提供丰富的过滤和格式化选项。

我将分步进行，首先搭建命令框架，然后填充核心逻辑，最后完善导航和打包等高级功能。

## [WIP] feat: 创建 `quipu export` 命令框架并注册

### 用户需求
实现 `quipu export` 命令的 V3 版本需求。第一步是创建该命令的骨架，定义所有必要的参数和选项，并将其注册到主 CLI 应用中，确保命令可以被调用。

### 评论
这是实现新功能的第一步，通过先建立一个可运行但无功能的命令框架，我们可以确保 CLI 的结构正确，为后续填充具体业务逻辑打下坚实的基础。

### 目标
1.  在 `packages/quipu-cli/src/quipu/cli/commands/` 目录下创建一个新的 `export.py` 文件。
2.  在 `export.py` 中定义一个 `export_command` 函数，并使用 `@app.command()` 装饰器。
3.  为该函数添加所有在 V3 需求文档中定义的 `typer` 选项：`--output-dir`, `--limit`, `--since`, `--until`, `--zip`, `--no-nav`, `--no-frontmatter`。
4.  在 `packages/quipu-cli/src/quipu/cli/main.py` 中导入并注册这个新的 `export` 命令。

### 基本原理
通过 Typer 框架，我们可以声明式地定义 CLI 命令及其参数。首先创建命令文件并完成注册，可以确保命令的入口点和参数解析是正确的。这是一种增量开发的有效方式，先搭建结构，再填充细节。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #concept/ui #scope/api #ai/instruct #task/domain/cli #task/object/export-command #task/action/implementation #task/state/begin

---

### Script

#### Acts 1: 创建 `export.py` 文件并定义命令骨架

我们将创建 `export.py` 文件，并使用 `typer` 定义 `export` 命令及其所有选项。

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/commands/export.py
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Annotated, Optional

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command(name="export")
    def export_command(
        ctx: typer.Context,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        output_dir: Annotated[
            Path,
            typer.Option(
                "--output-dir",
                "-o",
                help="导出文件的存放目录。",
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
            ),
        ] = Path("./.quipu/export"),
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制导出的最新节点数量。")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="仅导出指定时间戳 (YYYY-MM-DD HH:MM) 之后的节点。")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="仅导出指定时间戳 (YYYY-MM-DD HH:MM) 之前的节点。")] = None,
        zip_output: Annotated[bool, typer.Option("--zip", help="将导出目录压缩成一个 .zip 文件。")] = False,
        no_nav: Annotated[bool, typer.Option("--no-nav", help="禁止在文件末尾生成导航栏。")] = False,
        no_frontmatter: Annotated[bool, typer.Option("--no-frontmatter", help="禁止在文件开头生成 YAML Frontmatter。")] = False,
    ):
        """
        将 Quipu 历史记录导出为一组人类可读的 Markdown 文件。
        """
        typer.secho("🚀 Export command is running (implementation pending)...", fg=typer.colors.BLUE)
        typer.echo(f"Work Directory: {work_dir}")
        typer.echo(f"Output Directory: {output_dir}")
        if limit:
            typer.echo(f"Limit: {limit} nodes")
        if since:
            typer.echo(f"Since: {since}")
        if until:
            typer.echo(f"Until: {until}")
        if zip_output:
            typer.echo("Zip Output: Enabled")
        if no_nav:
            typer.echo("Navigation Bar: Disabled")
        if no_frontmatter:
            typer.echo("Frontmatter: Disabled")

        # Core logic to be implemented here
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                typer.secho("📜 历史记录为空，无需导出。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)
            
            # Placeholder for future implementation
            typer.secho(f"\n✅ Found {len(engine.history_graph)} nodes. Export logic will be implemented next.", fg=typer.colors.GREEN)

~~~~~

#### Acts 2: 在主 CLI 应用中注册 `export` 命令

现在，我们将新创建的命令模块导入到 `main.py` 并进行注册，使其成为 `quipu` CLI 的一部分。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~
~~~~~python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show, export

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
run.register(app)
ui.register(app)
show.register(app)


# --- Entry Point ---
if __name__ == "__main__":
~~~~~
~~~~~python
run.register(app)
ui.register(app)
show.register(app)
export.register(app)


# --- Entry Point ---
if __name__ == "__main__":
~~~~~

### 下一步建议
框架已经搭建完成。下一步，我将开始实现 `export.py` 中的核心业务逻辑，包括：
1.  **数据过滤**: 根据时间戳和数量筛选节点。
2.  **文件生成**: 实现文件名规范和文件内容的生成逻辑 (不含导航栏)。
3.  **核心导出循环**: 将筛选出的节点数据写入到目标目录的文件中。

如果你同意，我将开始实施这些核心功能。
