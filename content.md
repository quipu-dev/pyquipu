好的，我们基于当前的代码库开始执行。

我将生成一个计划来实现 `--json` 输出功能，并采用我们讨论过的、基于 `dataclasses` 的动态序列化方案来避免硬编码，确保代码的健壮性和可维护性。

## [WIP] feat: 为 log 和 find 命令添加 --json 输出格式

### 用户需求
为 `quipu log` 和 `quipu find` 命令增加一个 `--json` 标志，当该标志被激活时，命令应以机器可读的 JSON 格式向 `stdout` 输出结果，以便于脚本集成和自动化处理。

### 评论
这是一个重要的功能增强。提供 JSON 输出将 Quipu 从一个纯粹的人机交互工具，转变为一个可以轻松融入更广泛自动化工作流的系统组件，极大地提升了其作为平台工具的价值和开发者的体验 (DX)。

### 目标
1.  为 `query.py` 中的 `log` 和 `find_command` 函数添加 `--json` 命令行选项。
2.  实现一个动态的、非硬编码的辅助函数，用于将 `QuipuNode` 对象列表序列化为 JSON 字符串。
3.  当 `--json` 选项被使用时，程序将调用此辅助函数，将结果打印到 `stdout` 并立即退出，不输出任何其他人类可读的元信息。
4.  当不使用 `--json` 选项时，命令的行为保持不变。

### 基本原理
我们将遵循你提出的健壮性设计原则。通过在 `query.py` 中创建一个新的辅助函数 `_nodes_to_json_str`，我们将利用 Python 的 `dataclasses.fields` 功能来动态地将 `QuipuNode` 实例转换为字典。这种方法遵循“单一事实来源”原则，即数据结构只在 `quipu.core.models.QuipuNode` 中定义一次，序列化逻辑会自动适应其变化，从而避免了硬编码带来的脆弱性和维护负担。

在命令处理逻辑中，我们会优先检查 `--json` 标志。如果为真，则进入专门的 JSON 输出路径；否则，执行现有的人类可读输出逻辑。

### 标签
#intent/build #flow/ready #priority/medium #comp/cli #concept/ui #scope/api #scope/dx #ai/brainstorm #task/domain/cli #task/object/json-output #task/action/implementation #task/state/begin #task/status/active

---

### Script

#### Acts 1: 重构 `query.py` 以支持 JSON 输出

我们将使用 `write_file` 一次性更新整个 `query.py` 文件。这比使用多个 `patch_file` 更安全、更清晰，因为它完整地展示了最终的模块结构，包括新的导入、新的辅助函数以及对现有函数的修改。

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/commands/query.py
~~~~~
~~~~~python
import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, List

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from quipu.core.models import QuipuNode


def _nodes_to_json_str(nodes: List[QuipuNode]) -> str:
    """
    Dynamically serializes a list of QuipuNode objects to a JSON string,
    avoiding hardcoded fields for better maintainability.
    """
    EXCLUDED_FIELDS = {"parent", "children", "content", "filename"}
    node_list = []
    for node in nodes:
        node_dict = {}
        for field in dataclasses.fields(node):
            if field.name in EXCLUDED_FIELDS:
                continue
            value = getattr(node, field.name)
            if isinstance(value, datetime):
                node_dict[field.name] = value.isoformat()
            else:
                node_dict[field.name] = value
        
        # Explicitly add properties
        node_dict["short_hash"] = node.short_hash
        node_list.append(node_dict)
        
    return json.dumps(node_list, indent=2)


def register(app: typer.Typer):
    @app.command()
    def log(
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        """
        显示 Quipu 历史图谱日志。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            if not graph:
                if not json_output:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit(0)
            
            nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)

            if json_output:
                typer.echo(_nodes_to_json_str(nodes))
                raise typer.Exit(0)

            typer.secho("--- Quipu History Log ---", bold=True, err=True)
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
                tag = f"[{node.node_type.upper()}]"
                summary = node.summary
                typer.secho(f"{ts} {tag:<9} {node.short_hash}", fg=color, nl=False)
                typer.echo(f" - {summary}")

    @app.command(name="find")
    def find_command(
        ctx: typer.Context,
        summary_regex: Annotated[
            Optional[str], typer.Option("--summary", "-s", help="用于匹配节点摘要的正则表达式 (不区分大小写)。")
        ] = None,
        node_type: Annotated[Optional[str], typer.Option("--type", "-t", help="节点类型 ('plan' 或 'capture')。")] = None,
        limit: Annotated[int, typer.Option("--limit", "-n", help="返回的最大结果数量。")] = 10,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        """
        根据条件查找历史节点。
        """
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if not json_output:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if not json_output:
                    typer.secho("🤷 未找到符合条件的历史节点。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            if json_output:
                typer.echo(_nodes_to_json_str(nodes))
                ctx.exit(0)

            typer.secho("--- 查找结果 ---", bold=True, err=True)
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
                tag = f"[{node.node_type.upper()}]"
                typer.secho(f"{ts} {tag:<9} {node.output_tree}", fg=color, nl=False)
                typer.echo(f" - {node.summary}")
~~~~~

### 下一步建议
我们已经成功地实现了 `--json` 功能。现在，最关键的步骤是为这个新功能添加测试，以确保其正确性和未来的稳定性。

我建议更新 `tests/cli/test_query_commands.py`，添加新的测试用例来验证：
1.  当使用 `--json` 标志时，`result.stdout` 包含有效的 JSON 字符串。
2.  解析后的 JSON 数据结构和内容符合预期。
3.  当使用 `--json` 标志时，`result.stderr` 为空。
4.  当不使用 `--json` 标志时，命令的输出与之前保持一致。

如果你同意，我将立即着手生成更新测试文件的计划。
