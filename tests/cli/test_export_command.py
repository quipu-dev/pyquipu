import pytest
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

from quipu.cli.main import app
from quipu.engine.state_machine import Engine
from tests.helpers import EMPTY_TREE_HASH


@pytest.fixture
def populated_history(engine_instance: Engine):
    """
    创建一个包含分支、总结节点的复杂历史记录用于测试。
    History:
    - n0 (root)
      - n1
        - n2 (branch point)
          - n3a (branch A)
            - n4 (summary node)
          - n3b (branch B)
    """
    engine = engine_instance
    ws = engine.root_dir

    # Node 0
    (ws / "file.txt").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, h0, "plan 0", summary_override="Root Node")
    
    # Node 1
    (ws / "file.txt").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h0, h1, "plan 1", summary_override="Linear Node 1")

    # Node 2 (Branch Point)
    (ws / "file.txt").write_text("v2")
    h2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2, "plan 2", summary_override="Branch Point")

    # Node 3a (Branch A)
    engine.visit(h2) # Checkout branch point
    (ws / "branch_a.txt").touch()
    h3a = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3a, "plan 3a", summary_override="Branch A change")

    # Node 4 (Summary Node on Branch A)
    engine.visit(h3a)
    # No file change, create an idempotent node
    engine.create_plan_node(h3a, h3a, "plan 4", summary_override="Summary Node")

    # Node 3b (Branch B)
    engine.visit(h2) # Checkout branch point again
    (ws / "branch_b.txt").touch()
    h3b = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3b, "plan 3b", summary_override="Branch B change")

    return engine


def test_export_basic(runner, populated_history):
    """测试基本的导出功能。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    
    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir)])
    
    assert result.exit_code == 0
    assert "导出成功" in result.stderr
    assert output_dir.exists()
    
    files = list(output_dir.glob("*.md"))
    assert len(files) == 6  # n0, n1, n2, n3a, n4, n3b

    # 检查一个文件的内容
    branch_a_file = next((f for f in files if "Branch_A_change" in f.name), None)
    assert branch_a_file is not None
    content = branch_a_file.read_text()
    assert content.startswith("---")  # Has frontmatter
    assert "# content.md" in content
    assert "> [!nav] 节点导航" in content # Has navbar


def test_export_filtering(runner, populated_history):
    """测试过滤选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"

    # Test --limit
    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "-n", "2"])
    assert result.exit_code == 0
    assert len(list(output_dir.glob("*.md"))) == 2


def test_export_no_frontmatter(runner, populated_history):
    """测试 --no-frontmatter 选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-frontmatter", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert not a_file.read_text().startswith("---")


def test_export_no_nav(runner, populated_history):
    """测试 --no-nav 选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-nav", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert "> [!nav] 节点导航" not in a_file.read_text()


def test_export_navbar_logic(runner, populated_history):
    """验证导航栏链接的正确性。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir)])

    files = list(output_dir.glob("*.md"))
    
    # Test Branch Point links (Node 2)
    branch_point_file = next(f for f in files if "Branch_Point" in f.name)
    content = branch_point_file.read_text()
    assert content.count("→ [子节点]") == 2
    assert "← [父节点]" in content

    # Test Summary and Branch Point ancestor links (Node 4)
    summary_node_file = next(f for f in files if "Summary_Node" in f.name)
    content = summary_node_file.read_text()
    # n4 is a summary node, but its ancestors are not. So it should not have a summary link.
    assert "↑ [总结节点]" not in content
    assert "↓ [上一分支点]" in content
    assert "Branch_Point" in content # Check it links to the correct file


def test_export_zip(runner, populated_history):
    """测试 --zip 功能。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    
    result = runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--zip"])
    
    assert result.exit_code == 0
    assert "已保存为压缩包" in result.stderr
    
    zip_path = output_dir.with_suffix(".zip")
    assert not output_dir.exists()
    assert zip_path.exists()
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        assert len(zf.namelist()) == 6


def test_export_edge_cases(runner, quipu_workspace):
    """测试边界情况。"""
    work_dir, _, engine = quipu_workspace # Empty history
    
    # Test empty history
    result = runner.invoke(app, ["export", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "历史记录为空" in result.stderr

    # Create one node, then test no-match filter
    (work_dir / "f").touch()
    # Use the properly initialized engine from the fixture
    engine.capture_drift(engine.git_db.get_tree_hash())
    
    result = runner.invoke(app, ["export", "-w", str(work_dir), "--since", "2099-01-01 00:00"])
    assert result.exit_code == 0
    assert "未找到符合条件的节点" in result.stderr