import zipfile
from unittest.mock import ANY, MagicMock

import pytest
from pyquipu.cli.main import app
from pyquipu.engine.state_machine import Engine

from tests.helpers import EMPTY_TREE_HASH


@pytest.fixture
def populated_history(engine_instance: Engine):
    """
    创建一个包含分支、总结节点的通用历史记录用于测试。
    History:
    - n0 (root) -> n1 -> n2 (branch point) -> n3a (branch A) -> n4 (summary)
                                          \\-> n3b (branch B)
    """
    engine = engine_instance
    ws = engine.root_dir
    (ws / "file.txt").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, h0, "plan 0", summary_override="Root Node")
    (ws / "file.txt").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h0, h1, "plan 1", summary_override="Linear Node 1")
    (ws / "file.txt").write_text("v2")
    h2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2, "plan 2", summary_override="Branch Point")
    engine.visit(h2)
    (ws / "branch_a.txt").touch()
    h3a = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3a, "plan 3a", summary_override="Branch A change")
    engine.visit(h3a)
    engine.create_plan_node(h3a, h3a, "plan 4", summary_override="Summary Node")
    engine.visit(h2)
    (ws / "branch_b.txt").touch()
    h3b = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3b, "plan 3b", summary_override="Branch B change")
    return engine


@pytest.fixture
def history_for_all_links(engine_instance: Engine):
    """
    创建一个复杂的历史记录，确保特定节点拥有所有类型的导航链接。
    Node n3 will have: a parent (n2b), a child (n4), an ancestor branch point (n1),
    and an ancestor summary node (n_summary).
    """
    engine = engine_instance
    ws = engine.root_dir
    engine.create_plan_node(EMPTY_TREE_HASH, EMPTY_TREE_HASH, "plan sum", summary_override="Ancestor_Summary")
    (ws / "f").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, h0, "plan 0", summary_override="Root")
    (ws / "f").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h0, h1, "plan 1", summary_override="Branch_Point")
    engine.visit(h1)
    (ws / "a").touch()
    h2a = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2a, "plan 2a", summary_override="Branch_A")
    engine.visit(h1)
    (ws / "b").touch()
    h2b = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2b, "plan 2b", summary_override="Parent_Node")
    engine.visit(h2b)
    (ws / "c").touch()
    h3 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2b, h3, "plan 3", summary_override="Test_Target_Node")
    engine.visit(h3)
    (ws / "d").touch()
    h4 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h3, h4, "plan 4", summary_override="Child_Node")
    return engine


def test_export_basic(runner, populated_history, monkeypatch):
    """测试基本的导出功能。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir)])

    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("export.success.dir")

    assert output_dir.exists()
    files = list(output_dir.glob("*.md"))
    assert len(files) == 6
    target_file = next((f for f in files if "Branch_A_change" in f.name), None)
    assert target_file is not None
    content = target_file.read_text()
    assert content.startswith("---") and "> [!nav] 节点导航" in content


def test_export_filtering(runner, populated_history, monkeypatch):
    """测试过滤选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export_filter"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "-n", "2"])

    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("export.success.dir")
    assert len(list(output_dir.glob("*.md"))) == 2


def test_export_edge_cases(runner, quipu_workspace, monkeypatch):
    """测试边界情况。"""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    # Empty history
    result = runner.invoke(app, ["export", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_with("export.info.emptyHistory")

    # No matching nodes
    (work_dir / "f").touch()
    engine.capture_drift(engine.git_db.get_tree_hash())

    # Reset mock for second call
    mock_bus.reset_mock()

    result = runner.invoke(app, ["export", "-w", str(work_dir), "--since", "2099-01-01 00:00"])
    assert result.exit_code == 0
    mock_bus.info.assert_called_with("export.info.noMatchingNodes")


def test_export_no_frontmatter(runner, populated_history, monkeypatch):
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export_no_fm"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-frontmatter", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert not a_file.read_text().startswith("---")


def test_export_no_nav(runner, populated_history, monkeypatch):
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export_no_nav"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-nav", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert "> [!nav] 节点导航" not in a_file.read_text()


def test_export_zip(runner, populated_history, monkeypatch):
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export_zip"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--zip"])

    assert result.exit_code == 0
    mock_bus.info.assert_any_call("export.info.zipping")
    mock_bus.success.assert_called_with("export.success.zip", path=ANY)

    zip_path = output_dir.with_suffix(".zip")
    assert not output_dir.exists() and zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert len(zf.namelist()) == 6


@pytest.mark.parametrize(
    "link_type_to_hide, text_not_expected, text_still_expected",
    [
        ("summary", "↑ [总结节点]", "↓ [上一分支点]"),
        ("branch", "↓ [上一分支点]", "← [父节点]"),
        ("parent", "← [父节点]", "→ [子节点]"),
        ("child", "→ [子节点]", "↑ [总结节点]"),
    ],
)
def test_export_hide_link_type(
    runner, history_for_all_links, link_type_to_hide, text_not_expected, text_still_expected, monkeypatch
):
    """验证 --hide-link-type 选项能成功禁用特定类型的导航链接。"""
    engine = history_for_all_links
    output_dir = engine.root_dir / ".quipu" / "test_export_hide_links"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    result = runner.invoke(
        app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--hide-link-type", link_type_to_hide]
    )
    assert result.exit_code == 0
    files = {f.name: f for f in output_dir.glob("*.md")}
    target_file = next(f for name, f in files.items() if "Test_Target_Node" in name)
    content = target_file.read_text()
    assert text_not_expected not in content
    assert text_still_expected in content


def test_export_hide_multiple_link_types(runner, history_for_all_links, monkeypatch):
    """验证可以同时禁用多种链接类型。"""
    engine = history_for_all_links
    output_dir = engine.root_dir / ".quipu" / "test_export_hide_multi"
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.export.bus", mock_bus)

    result = runner.invoke(
        app,
        [
            "export",
            "-w",
            str(engine.root_dir),
            "-o",
            str(output_dir),
            "--hide-link-type",
            "summary",
            "--hide-link-type",
            "child",
        ],
    )
    assert result.exit_code == 0
    files = {f.name: f for f in output_dir.glob("*.md")}
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
