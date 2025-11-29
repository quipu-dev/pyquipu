好的，我们开始执行试点重构。

此计划将专注于 `workspace` 相关命令 (`save` 和 `discard`)，将其所有面向用户的输出迁移到 `MessageBus` 系统。同时，我们会更新其测试用例，使其不再依赖脆弱的字符串匹配，而是通过模拟 (Mocking) `MessageBus` 来验证业务逻辑的正确意图，从而建立一套更健壮、可维护的测试实践。

## [WIP] refactor(cli): 将 workspace 命令输出迁移到 MessageBus

### 用户需求
1.  重构 `packages/quipu-cli/src/quipu/cli/commands/workspace.py` 文件，将其中所有的 `typer.secho` 调用替换为对 `quipu.common.messaging.bus` 的调用。
2.  将所有硬编码的消息文本提取到 `locales/zh/cli.json` 文件中，并使用消息 ID 进行调用。
3.  重构 `tests/cli/test_workspace_commands.py` 文件，使用 `monkeypatch` 和 `unittest.mock` 来模拟 `MessageBus`，并更新测试断言以验证对 `bus` 的方法调用，而不是检查 `result.stderr` 中的具体字符串。

### 评论
这是将 `MessageBus` 理念落地到实际代码的第一步。通过对 `workspace` 这个逻辑相对独立的组件进行试点重构，我们可以验证整个工作流的有效性，并为后续大规模重构其他命令建立一个清晰的模式。这个改动将显著提升我们测试用例的健壮性。

### 目标
1.  `workspace.py` 中不再有任何 `typer.secho` 调用。
2.  `locales/zh/cli.json` 包含所有 `workspace` 命令所需的消息模板。
3.  `test_workspace_commands.py` 中的测试用例与 UI 表示层（颜色、图标、具体文本）完全解耦。

### 基本原理
我们将遵循“依赖倒置”原则，在测试环境中用一个模拟对象 (Mock) 替换掉真实的 `MessageBus` 实例。这样，当 CLI 命令运行时，它会调用我们的模拟对象上的方法。测试代码随后可以检查这个模拟对象被调用的方式（例如，`success` 方法是否被以 `"workspace.save.success"` 为参数调用了一次），从而验证了业务逻辑的正确性，而无需关心这个消息最终被渲染成了什么样子。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #comp/common #comp/tests #concept/ui #scope/core #scope/dx #ai/instruct #task/domain/ui #task/object/message-bus #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 重构 `workspace.py` 以使用 `MessageBus`

我们将引入 `bus` 实例，并逐一替换掉 `typer.secho` 调用。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/workspace.py
~~~~~
~~~~~python
from pathlib import Path
from typing import Annotated, Optional

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
~~~~~
~~~~~python
from pathlib import Path
from typing import Annotated, Optional

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from quipu.common.messaging import bus
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/workspace.py
~~~~~
~~~~~python
            if is_node_clean or is_genesis_clean:
                typer.secho("✅ 工作区状态未发生变化，无需创建快照。", fg=typer.colors.GREEN, err=True)
                ctx.exit(0)

            try:
                node = engine.capture_drift(current_tree_hash, message=message)
                msg_suffix = f" ({message})" if message else ""
                typer.secho(f"📸 快照已保存: {node.short_hash}{msg_suffix}", fg=typer.colors.GREEN, err=True)
            except Exception as e:
                logger.error("创建快照失败", exc_info=True)
                typer.secho(f"❌ 创建快照失败: {e}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
~~~~~
~~~~~python
            if is_node_clean or is_genesis_clean:
                bus.success("workspace.save.noChanges")
                ctx.exit(0)

            try:
                node = engine.capture_drift(current_tree_hash, message=message)
                msg_suffix = f" ({message})" if message else ""
                bus.success("workspace.save.success", short_hash=node.short_hash, msg_suffix=msg_suffix)
            except Exception as e:
                bus.error("workspace.save.error", error=str(e))
                ctx.exit(1)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/workspace.py
~~~~~
~~~~~python
            graph = engine.history_graph
            if not graph:
                typer.secho("❌ 错误: 找不到任何历史记录，无法确定要恢复到哪个状态。", fg=typer.colors.RED, err=True)
                ctx.exit(1)

            target_tree_hash = engine._read_head()
~~~~~
~~~~~python
            graph = engine.history_graph
            if not graph:
                bus.error("workspace.discard.error.noHistory")
                ctx.exit(1)

            target_tree_hash = engine._read_head()
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/workspace.py
~~~~~
~~~~~python
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                typer.secho(
                    f"⚠️  HEAD 指针丢失或无效，将恢复到最新历史节点: {latest_node.short_hash}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_tree_hash:
                typer.secho(
                    f"✅ 工作区已经是干净状态 ({latest_node.short_hash})，无需操作。", fg=typer.colors.GREEN, err=True
                )
                ctx.exit(0)

            diff_stat = engine.git_db.get_diff_stat(target_tree_hash, current_hash)
            typer.secho("\n以下是即将被丢弃的变更:", fg=typer.colors.YELLOW, err=True)
            typer.secho("-" * 20, err=True)
            typer.echo(diff_stat, err=True)
            typer.secho("-" * 20, err=True)

            if not force:
                prompt = f"🚨 即将丢弃上述所有变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？"
                if not prompt_for_confirmation(prompt, default=False):
                    typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
                    raise typer.Abort()

            try:
                engine.visit(target_tree_hash)
                typer.secho(f"✅ 工作区已成功恢复到节点 {latest_node.short_hash}。", fg=typer.colors.GREEN, err=True)
            except Exception as e:
                logger.error(f"恢复工作区状态失败", exc_info=True)
                typer.secho(f"❌ 恢复状态失败: {e}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
~~~~~
~~~~~python
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                bus.warning("workspace.discard.warning.headMissing", short_hash=latest_node.short_hash)

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_tree_hash:
                bus.success("workspace.discard.noChanges", short_hash=latest_node.short_hash)
                ctx.exit(0)

            diff_stat = engine.git_db.get_diff_stat(target_tree_hash, current_hash)
            bus.info("workspace.discard.ui.diffHeader")
            typer.secho("-" * 20, err=True)
            typer.echo(diff_stat, err=True)
            typer.secho("-" * 20, err=True)

            if not force:
                prompt = f"🚨 即将丢弃上述所有变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？"
                if not prompt_for_confirmation(prompt, default=False):
                    bus.warning("common.prompt.cancel")
                    raise typer.Abort()

            try:
                engine.visit(target_tree_hash)
                bus.success("workspace.discard.success", short_hash=latest_node.short_hash)
            except Exception as e:
                bus.error("workspace.discard.error.generic", error=str(e))
                ctx.exit(1)
~~~~~

#### Acts 2: 扩充 `locales/zh/cli.json`

我们将新的消息 ID 和模板添加到 `cli.json` 文件中。

~~~~~act
patch_file
locales/zh/cli.json
~~~~~
~~~~~json
{
  "common.error.generic": "❌ 系统错误: {error}",
  "common.prompt.cancel": "\n🚫 操作已取消。",
  "workspace.save.success": "📸 快照已保存: {short_hash}{msg_suffix}",
  "workspace.save.noChanges": "✅ 工作区状态未发生变化，无需创建快照。",
  "workspace.save.error": "❌ 创建快照失败: {error}"
}
~~~~~
~~~~~json
{
  "common.error.generic": "❌ 系统错误: {error}",
  "common.prompt.cancel": "\n🚫 操作已取消。",
  "workspace.save.success": "📸 快照已保存: {short_hash}{msg_suffix}",
  "workspace.save.noChanges": "✅ 工作区状态未发生变化，无需创建快照。",
  "workspace.save.error": "❌ 创建快照失败: {error}",
  "workspace.discard.success": "✅ 工作区已成功恢复到节点 {short_hash}。",
  "workspace.discard.noChanges": "✅ 工作区已经是干净状态 ({short_hash})，无需操作。",
  "workspace.discard.error.noHistory": "❌ 错误: 找不到任何历史记录，无法确定要恢复到哪个状态。",
  "workspace.discard.error.generic": "❌ 恢复状态失败: {error}",
  "workspace.discard.warning.headMissing": "⚠️  HEAD 指针丢失或无效，将恢复到最新历史节点: {short_hash}",
  "workspace.discard.ui.diffHeader": "\n以下是即将被丢弃的变更:"
}
~~~~~

#### Acts 3: 重构 `test_workspace_commands.py`

最后，我们重写测试文件，用 `mock` 调用断言取代字符串匹配。

~~~~~act
write_file
tests/cli/test_workspace_commands.py
~~~~~
~~~~~python
from unittest.mock import MagicMock
from unittest import mock
from quipu.cli.main import app


def test_save_clean_workspace(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Initial")

    result = runner.invoke(app, ["save", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("workspace.save.noChanges")


def test_save_with_changes(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with(
        "workspace.save.success", short_hash=mock.ANY, msg_suffix=" (My Snapshot)"
    )


def test_discard_changes(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    initial_node = engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["discard", "-f", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("workspace.discard.success", short_hash=initial_node.short_hash)
    assert (work_dir / "file.txt").read_text() == "v1"


def test_discard_interactive_abort(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["discard", "-w", str(work_dir)], input="n")

    assert result.exit_code == 1
    mock_bus.warning.assert_called_once_with("common.prompt.cancel")
    assert (work_dir / "file.txt").read_text() == "v2"
~~~~~

### 下一步建议
试点重构已完成。我们成功地将一个 CLI 命令模块及其测试迁移到了新的 `MessageBus` 架构上。

下一步，我们可以将这个模式推广到其他命令模块。建议按照以下顺序进行，从简单到复杂：
1.  **`query` 和 `show`**: 这两个是只读命令，重构起来最简单。
2.  **`cache`**: 涉及文件系统操作，但逻辑不复杂。
3.  **`navigation`**: 逻辑比 `workspace` 更复杂，涉及更多用户交互和状态变更。
4.  **`axon`, `run`**: 涉及运行时和引擎的协调，是核心命令。
5.  **`remote`, `export`, `ui`**: 相对独立的复杂命令。

如果你同意，我们可以从 `query` 和 `show` 命令开始下一步的重构。
