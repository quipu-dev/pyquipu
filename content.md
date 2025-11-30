好的，我们继续。为 `log` 和 `export` 命令添加 `--reachable-only` 参数，并再次遵循 DRY 原则，将核心逻辑提取到 `helpers.py` 中。

这个功能需要我们确定当前的工作区状态 (HEAD)，然后从历史图谱中找出所有与 HEAD 直接相关的祖先和后代节点。

## [WIP] feat(cli): 为 log 和 export 添加 --reachable-only 过滤

### 用户需求
为 `quipu log` 和 `quipu export` 命令添加一个新的布尔选项 `--reachable-only`。当启用此选项时，命令应只输出/导出那些与当前工作区状态 (HEAD) 在历史图谱上直接连通的节点（即祖先和后代）。

### 评论
这是一个高级功能，极大地提升了历史图谱的可读性。当项目历史变得复杂、分支繁多时，用户往往只关心当前工作路径的演进历史。这个功能可以有效地“剪枝”，隐藏掉不相关的实验性分支，让输出聚焦于主线故事。

### 目标
1.  在 `helpers.py` 中创建一个新的辅助函数 `filter_reachable_nodes`，封装计算和过滤可达节点的逻辑。
2.  在 `export.py` 中添加 `--reachable-only` 选项，并调用新的辅助函数。
3.  在 `query.py` 中为 `log` 命令添加 `--reachable-only` 选项，并调用新的辅助函数。
4.  为 `export` 和 `log` 命令添加新的测试用例，验证该功能的正确性。

### 基本原理
1.  **确定“当前”**: 首先，我们需要找到代表当前工作区状态的 `QuipuNode`。
2.  **计算可达集**: 利用 `HistoryReader` 提供的 `get_ancestor_output_trees` 和 `get_descendant_output_trees` 方法，我们可以高效地获取与当前节点相关的所有祖先和后代节点的 `output_tree` 哈希。将这两部分哈希与当前节点自身的哈希合并，就得到了完整的“可达哈希集合”。
3.  **过滤**: 遍历所有待处理的节点列表，只保留那些 `output_tree` 哈希存在于“可达哈希集合”中的节点。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #comp/engine #concept/history #scope/ux #ai/instruct #task/domain/cli #task/object/log-command #task/action/feature-enhancement #task/state/continue

---

### Script

#### Acts 1: 在 `helpers.py` 中实现可达性过滤

我们将创建 `filter_reachable_nodes` 函数。它需要 `engine` 实例来访问图谱和当前状态。

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/helpers.py
~~~~~
~~~~~python
def filter_nodes(
    nodes: List[QuipuNode], limit: Optional[int], since: Optional[str], until: Optional[str]
) -> List[QuipuNode]:
    """根据时间戳和数量过滤节点列表。"""
    filtered = nodes
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp >= since_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'since' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp <= until_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'until' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if limit is not None and limit > 0:
        filtered = filtered[:limit]
    return filtered
~~~~~
~~~~~python
def filter_nodes(
    nodes: List[QuipuNode], limit: Optional[int], since: Optional[str], until: Optional[str]
) -> List[QuipuNode]:
    """根据时间戳和数量过滤节点列表。"""
    filtered = nodes
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp >= since_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'since' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp <= until_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'until' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if limit is not None and limit > 0:
        filtered = filtered[:limit]
    return filtered


def filter_reachable_nodes(engine: Engine, nodes: List[QuipuNode]) -> List[QuipuNode]:
    """仅保留与当前工作区状态直接相关的节点（祖先和后代）。"""
    current_node = _find_current_node(engine, engine.history_graph)
    if not current_node:
        # 如果工作区是脏的，无法确定起点，返回所有节点
        return nodes

    current_hash = current_node.output_tree
    ancestors = engine.reader.get_ancestor_output_trees(current_hash)
    descendants = engine.reader.get_descendant_output_trees(current_hash)
    reachable_set = ancestors.union(descendants)
    reachable_set.add(current_hash)

    return [node for node in nodes if node.output_tree in reachable_set]
~~~~~

#### Acts 2: 为 `export` 命令集成可达性过滤

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/export.py
~~~~~
~~~~~python
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context, filter_nodes
~~~~~
~~~~~python
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context, filter_nodes, filter_reachable_nodes
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/export.py
~~~~~
~~~~~python
        hide_link_type: Annotated[
            Optional[List[str]],
            typer.Option(
                "--hide-link-type", help="禁用特定类型的导航链接 (可多次使用: summary, branch, parent, child)"
            ),
        ] = None,
    ):
        """将 Quipu 历史记录导出为一组人类可读的 Markdown 文件。"""
        hidden_types = set(hide_link_type) if hide_link_type else set()

        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                bus.info("export.info.emptyHistory")
                ctx.exit(0)

            all_nodes = sorted(engine.history_graph.values(), key=lambda n: n.timestamp, reverse=True)
            try:
                # filter_nodes returns preserving input order (reverse chrono),
                # but export expects chronological order for file generation/processing
                filtered = filter_nodes(all_nodes, limit, since, until)
                nodes_to_export = list(reversed(filtered))
            except typer.BadParameter as e:
                bus.error("export.error.badParam", error=str(e))
                ctx.exit(1)
~~~~~
~~~~~python
        hide_link_type: Annotated[
            Optional[List[str]],
            typer.Option(
                "--hide-link-type", help="禁用特定类型的导航链接 (可多次使用: summary, branch, parent, child)"
            ),
        ] = None,
        reachable_only: Annotated[bool, typer.Option("--reachable-only", help="仅导出与当前工作区状态直接相关的节点。")] = False,
    ):
        """将 Quipu 历史记录导出为一组人类可读的 Markdown 文件。"""
        hidden_types = set(hide_link_type) if hide_link_type else set()

        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                bus.info("export.info.emptyHistory")
                ctx.exit(0)

            nodes_to_process = sorted(engine.history_graph.values(), key=lambda n: n.timestamp, reverse=True)

            if reachable_only:
                nodes_to_process = filter_reachable_nodes(engine, nodes_to_process)

            try:
                # filter_nodes returns preserving input order (reverse chrono),
                # but export expects chronological order for file generation/processing
                filtered = filter_nodes(nodes_to_process, limit, since, until)
                nodes_to_export = list(reversed(filtered))
            except typer.BadParameter as e:
                bus.error("export.error.badParam", error=str(e))
                ctx.exit(1)
~~~~~

#### Acts 3: 为 `log` 命令集成可达性过滤

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/query.py
~~~~~
~~~~~python
from ..config import DEFAULT_WORK_DIR
from .helpers import engine_context, filter_nodes
~~~~~
~~~~~python
from ..config import DEFAULT_WORK_DIR
from .helpers import engine_context, filter_nodes, filter_reachable_nodes
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/query.py
~~~~~
~~~~~python
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制显示的节点数量。")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="起始时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="截止时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        """
        显示 Quipu 历史图谱日志。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            if not graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                raise typer.Exit(0)

            all_nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)
            try:
                nodes = filter_nodes(all_nodes, limit, since, until)
            except typer.BadParameter as e:
                bus.error("common.error.invalidConfig", error=str(e))
                ctx.exit(1)
~~~~~
~~~~~python
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制显示的节点数量。")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="起始时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="截止时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        reachable_only: Annotated[bool, typer.Option("--reachable-only", help="仅显示与当前工作区状态直接相关的节点。")] = False,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        """
        显示 Quipu 历史图谱日志。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            if not graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                raise typer.Exit(0)

            nodes_to_process = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)

            if reachable_only:
                nodes_to_process = filter_reachable_nodes(engine, nodes_to_process)

            try:
                nodes = filter_nodes(nodes_to_process, limit, since, until)
            except typer.BadParameter as e:
                bus.error("common.error.invalidConfig", error=str(e))
                ctx.exit(1)
~~~~~

#### Acts 4: 添加新的测试用例

为 `test_export_command.py` 和 `test_query_commands.py` 添加测试。

~~~~~act
patch_file tests/cli/test_export_command.py
~~~~~
~~~~~python
    target_file = next(f for name, f in files.items() if "Test_Target_Node" in name)
    content = target_file.read_text()
    assert "↑ [总结节点]" not in content and "→ [子节点]" not in content
    assert "↓ [上一分支点]" in content and "← [父节点]" in content
~~~~~
~~~~~python
    target_file = next(f for name, f in files.items() if "Test_Target_Node" in name)
    content = target_file.read_text()
    assert "↑ [总结节点]" not in content and "→ [子节点]" not in content
    assert "↓ [上一分支点]" in content and "← [父节点]" in content


def test_export_reachable_only(runner, populated_history, monkeypatch):
    """测试 --reachable-only 选项是否能过滤掉无关分支。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export_reachable"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    # The fixture leaves HEAD on branch B. We'll checkout a node on branch A.
    summary_node = next(n for n in engine.history_graph.values() if n.summary == "Summary Node")
    engine.visit(summary_node.output_tree)

    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--reachable-only"])
    assert result.exit_code == 0

    files = list(output_dir.glob("*.md"))
    # Branch A path: Root -> Linear 1 -> Branch Point -> Branch A -> Summary (5 nodes)
    # Branch B is now unreachable and should be excluded.
    assert len(files) == 5

    filenames = {f.name for f in files}
    assert not any("Branch_B_change" in name for name in filenames)
    assert any("Branch_A_change" in name for name in filenames)
~~~~~

~~~~~act
patch_file tests/cli/test_query_commands.py
~~~~~
~~~~~python
def test_log_filtering(runner, quipu_workspace, monkeypatch):
    """Test limit and time filtering logic for log command."""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    # Create 3 nodes
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
    (work_dir / "f3").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 3")

    # 1. Test Limit
    result = runner.invoke(app, ["log", "-n", "1", "-w", str(work_dir)])
    assert result.exit_code == 0
    # Should only print header + 1 node
    assert mock_bus.data.call_count == 1
    assert "Node 3" in mock_bus.data.call_args_list[0].args[0]  # Newest

    # 2. Test Filtering Result Empty
    mock_bus.reset_mock()
    # Using a future date
    result = runner.invoke(app, ["log", "--since", "2099-01-01 00:00", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_with("query.info.noResults")
~~~~~
~~~~~python
def test_log_filtering(runner, quipu_workspace, monkeypatch):
    """Test limit and time filtering logic for log command."""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    # Create 3 nodes
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
    (work_dir / "f3").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 3")

    # 1. Test Limit
    result = runner.invoke(app, ["log", "-n", "1", "-w", str(work_dir)])
    assert result.exit_code == 0
    # Should only print header + 1 node
    assert mock_bus.data.call_count == 1
    assert "Node 3" in mock_bus.data.call_args_list[0].args[0]  # Newest

    # 2. Test Filtering Result Empty
    mock_bus.reset_mock()
    # Using a future date
    result = runner.invoke(app, ["log", "--since", "2099-01-01 00:00", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_with("query.info.noResults")


def test_log_reachable_only(runner, quipu_workspace, monkeypatch):
    """Test --reachable-only filtering for the log command."""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    # History: root -> A -> B (HEAD)
    #               \\-> C (unreachable)
    (work_dir / "f_a").touch()
    h_a = engine.git_db.get_tree_hash()
    node_a = engine.capture_drift(h_a, "Node A")

    (work_dir / "f_b").touch()
    h_b = engine.git_db.get_tree_hash()
    engine.capture_drift(h_b, "Node B")

    engine.visit(node_a.output_tree)
    (work_dir / "f_c").touch()
    h_c = engine.git_db.get_tree_hash()
    engine.capture_drift(h_c, "Node C")

    # Checkout back to B to set it as current HEAD
    engine.visit(h_b)

    result = runner.invoke(app, ["log", "--reachable-only", "-w", str(work_dir)])
    assert result.exit_code == 0

    output = "".join(call.args[0] for call in mock_bus.data.call_args_list)
    assert "Node B" in output  # HEAD is reachable
    assert "Node A" in output  # Ancestor is reachable
    assert "Node C" not in output  # Unrelated branch is not reachable
~~~~~

### 下一步建议
我们已经成功为 `log` 和 `export` 添加了强大的过滤功能，并保持了代码的整洁。下一步可以考虑：
1.  **UI 集成**: 在 `quipu ui` 中添加一个快捷键（例如 `t` for toggle）来动态地显示/隐藏不可达的分支，这将极大地增强 TUI 的可用性。
2.  **性能**: 对于超大规模的历史库，计算可达性可能会有性能开销。可以评估在 `SQLite` 后端预计算或缓存可达性集合的可行性。
