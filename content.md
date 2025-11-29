好的，我们继续推进 `MessageBus` 的集成工作。

根据我们制定的路线图，下一步是重构 `query` 和 `show` 这两个只读命令。这是一个理想的步骤，因为它们逻辑清晰，不涉及文件系统写入，能让我们在低风险的环境下扩大新架构的覆盖范围。

## [WIP] refactor(cli): 迁移 query 和 show 命令至 MessageBus

### 用户需求
1.  重构 `packages/quipu-cli/src/quipu/cli/commands/query.py` 和 `show.py`，将所有面向用户的 `typer` 输出调用替换为对 `MessageBus` 的调用。
2.  将相应的硬编码消息文本迁移到 `locales/zh/cli.json`。
3.  更新 `tests/cli/test_query_commands.py`，使用 `MessageBus` 模拟来验证命令的输出意图，而不是匹配输出字符串。

### 评论
这次重构延续了我们在 `workspace` 命令上建立的成功模式。通过处理 `query` 和 `show` 命令，我们不仅能进一步净化 CLI 代码库，还能特别处理“数据输出 (`stdout`)”与“元信息输出 (`stderr`)”的分离问题，确保 `bus.data()` 的正确使用，这对于工具的管道协作能力至关重要。

### 目标
1.  `query.py` 和 `show.py` 中所有简单的、面向用户的 `typer.secho` 和 `typer.echo` 调用被 `bus` 调用取代。
2.  `locales/zh/cli.json` 包含 `query` 和 `show` 命令所需的所有新消息模板。
3.  `test_query_commands.py` 中的断言逻辑完全迁移到对模拟 `bus` 实例的方法调用验证上，实现与 UI 的彻底解耦。

### 基本原理
我们将继续应用“依赖倒置”和“模拟测试”的策略。对于 `query` 和 `show` 命令，一个关键点是将它们的输出分为两类：
1.  **元信息**: 如标题（`--- Quipu History Log ---`）、状态（`历史记录为空`）等，将通过 `bus.info`, `bus.error` 等方法输出到 `stderr`。
2.  **数据**: 如 `log` 命令的节点列表、`show` 命令的文件内容、JSON 输出等，将通过 `bus.data()` 方法输出到 `stdout`。

通过在测试中模拟 `bus` 对象，我们可以精确地断言哪个方法被调用，以及传递了什么数据，从而确保了命令在逻辑层面的正确性。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #comp/tests #concept/ui #scope/dx #ai/instruct #task/domain/ui #task/object/message-bus #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 重构 `query.py`

我们将 `bus` 引入 `query.py` 并替换所有 `typer` 调用。核心数据输出将改用 `bus.data()`。

~~~~~act
patch_file
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
from quipu.interfaces.models import QuipuNode
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
from quipu.common.messaging import bus
from quipu.interfaces.models import QuipuNode
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/query.py
~~~~~
~~~~~python
            if not graph:
                if json_output:
                    typer.echo("[]")
                else:
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
~~~~~
~~~~~python
            if not graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                raise typer.Exit(0)

            nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)

            if json_output:
                bus.data(_nodes_to_json_str(nodes))
                raise typer.Exit(0)

            bus.info("query.log.ui.header")
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                tag = f"[{node.node_type.upper()}]"
                summary = node.summary
                # Note: Coloring is a presentation detail handled by renderer, or omitted for data.
                # Here we pass the uncolored data string to the bus.
                data_line = f"{ts} {tag:<9} {node.short_hash} - {summary}"
                bus.data(data_line)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/query.py
~~~~~
~~~~~python
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if json_output:
                    typer.echo("[]")
                else:
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
~~~~~python
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.noResults")
                ctx.exit(0)

            if json_output:
                bus.data(_nodes_to_json_str(nodes))
                ctx.exit(0)

            bus.info("query.find.ui.header")
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                tag = f"[{node.node_type.upper()}]"
                data_line = f"{ts} {tag:<9} {node.output_tree} - {node.summary}"
                bus.data(data_line)
~~~~~

#### Acts 2: 重构 `show.py`

与 `query.py` 类似，我们将 `bus` 引入 `show.py` 并替换 `typer` 调用。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/show.py
~~~~~
~~~~~python
from rich.console import Console
from rich.syntax import Syntax

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR

logger = logging.getLogger(__name__)


def _find_target_node(graph: Dict, hash_prefix: str):
    """辅助函数，用于在图中查找唯一的节点。"""
    matches = [
        node
        for node in graph.values()
        if node.commit_hash.startswith(hash_prefix) or node.output_tree.startswith(hash_prefix)
    ]
    if not matches:
        typer.secho(f"❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.secho(
            f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    return matches[0]
~~~~~
~~~~~python
from rich.console import Console
from rich.syntax import Syntax

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from quipu.common.messaging import bus

logger = logging.getLogger(__name__)


def _find_target_node(graph: Dict, hash_prefix: str):
    """辅助函数，用于在图中查找唯一的节点。"""
    matches = [
        node
        for node in graph.values()
        if node.commit_hash.startswith(hash_prefix) or node.output_tree.startswith(hash_prefix)
    ]
    if not matches:
        bus.error("show.error.notFound", hash_prefix=hash_prefix)
        raise typer.Exit(1)
    if len(matches) > 1:
        bus.error("show.error.notUnique", hash_prefix=hash_prefix, count=len(matches))
        raise typer.Exit(1)
    return matches[0]
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/show.py
~~~~~
~~~~~python
            blobs = engine.reader.get_node_blobs(target_node.commit_hash)

            if not blobs:
                if json_output:
                    typer.echo("{}")
                else:
                    typer.secho("🤷 此节点内部无文件内容。", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit()

            # --- Phase 1: Build output dictionary ---
            output_data = {}
            files_to_process = extract if extract else sorted(blobs.keys())

            for filename in files_to_process:
                if filename not in blobs:
                    typer.secho(f"❌ 错误: 在节点内未找到文件 '{filename}'。", fg=typer.colors.RED, err=True)
                    typer.secho(f"可用文件: {', '.join(blobs.keys())}", fg=typer.colors.YELLOW, err=True)
                    raise typer.Exit(1)

                content_bytes = blobs[filename]
~~~~~
~~~~~python
            blobs = engine.reader.get_node_blobs(target_node.commit_hash)

            if not blobs:
                if json_output:
                    bus.data("{}")
                else:
                    bus.info("show.info.noContent")
                raise typer.Exit()

            # --- Phase 1: Build output dictionary ---
            output_data = {}
            files_to_process = extract if extract else sorted(blobs.keys())

            for filename in files_to_process:
                if filename not in blobs:
                    bus.error("show.error.fileNotInNode", filename=filename)
                    bus.info("show.info.availableFiles", file_list=", ".join(blobs.keys()))
                    raise typer.Exit(1)

                content_bytes = blobs[filename]
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/show.py
~~~~~
~~~~~python
            # --- Phase 2: Render output ---
            if json_output:
                typer.echo(json.dumps(output_data, indent=2, ensure_ascii=False))
            else:
                console = Console()
~~~~~
~~~~~python
            # --- Phase 2: Render output ---
            if json_output:
                bus.data(json.dumps(output_data, indent=2, ensure_ascii=False))
            else:
                console = Console()
~~~~~

#### Acts 3: 扩充 `locales/zh/cli.json`

我们将所有新的消息 ID 和模板添加到 `cli.json` 文件中。

~~~~~act
patch_file
locales/zh/cli.json
~~~~~
~~~~~json
}
~~~~~
~~~~~json
,
  "query.info.emptyHistory": "📜 历史记录为空。",
  "query.info.noResults": "🤷 未找到符合条件的历史节点。",
  "query.log.ui.header": "--- Quipu History Log ---",
  "query.find.ui.header": "--- 查找结果 ---",
  "show.error.notFound": "❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。",
  "show.error.notUnique": "❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {count} 个节点。",
  "show.info.noContent": "🤷 此节点内部无文件内容。",
  "show.error.fileNotInNode": "❌ 错误: 在节点内未找到文件 '{filename}'。",
  "show.info.availableFiles": "可用文件: {file_list}"
}
~~~~~

#### Acts 4: 重构 `test_query_commands.py`

最后，我们重写测试文件，以使用 `mock` 调用断言。

~~~~~act
write_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
import json
from unittest.mock import MagicMock, call
from quipu.cli.main import app


def test_log_empty(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.info.emptyHistory")


def test_log_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    node1 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    node2 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.log.ui.header")
    assert "Node 1" in mock_bus.data.call_args_list[0].args[0]
    assert "Node 2" in mock_bus.data.call_args_list[1].args[0]


def test_find_command(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    hash_v1 = engine.git_db.get_tree_hash()
    engine.capture_drift(hash_v1, message="Fix bug")
    (work_dir / "f2").touch()
    hash_v2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(
        input_tree=hash_v1, output_tree=hash_v2, plan_content="content", summary_override="Implement feature"
    )

    result = runner.invoke(app, ["find", "-s", "Fix", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.find.ui.header")
    mock_bus.data.assert_called_once()
    assert "Fix bug" in mock_bus.data.call_args.args[0]


def test_log_json_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")

    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once()
    
    # Verify the data passed to bus.data is valid JSON with expected content
    json_data = json.loads(mock_bus.data.call_args.args[0])
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert "Node 1" in json_data[0]["summary"]


def test_find_json_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Feature A")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Bugfix B")

    result = runner.invoke(app, ["find", "--summary", "Bugfix", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once()

    json_data = json.loads(mock_bus.data.call_args.args[0])
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert "Bugfix B" in json_data[0]["summary"]


def test_log_json_empty(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)
    
    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once_with("[]")
~~~~~

### 下一步建议
我们已经成功地将 `query` 和 `show` 命令迁移到了 `MessageBus` 架构。

下一个合适的重构目标是 `cache` 命令。它的逻辑比 `query` 复杂，因为它会修改文件系统（删除和创建数据库文件），但比 `navigation` 或 `run` 命令要简单。这将是检验 `MessageBus` 在处理带有副作用的命令时表现的一个很好的案例。

如果你同意，我将开始准备重构 `cache` 命令的计划。
