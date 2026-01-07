from unittest.mock import MagicMock

import pytest
from pyquipu.cli.main import app
from pyquipu.engine.state_machine import Engine


@pytest.fixture
def history_with_redundant_refs(engine_instance: Engine):
    """
    创建一个包含线性和分支历史的仓库，这将生成冗余的 head 引用。
    History: root -> n1 -> n2 (branch point) -> n3a (leaf)
                                            \\-> n3b (leaf)
    Expected redundant refs: root, n1, n2
    Expected preserved refs: n3a, n3b
    """
    engine = engine_instance
    ws = engine.root_dir

    # root
    (ws / "file.txt").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.capture_drift(h0, "root")

    # n1
    (ws / "file.txt").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.capture_drift(h1, "n1")

    # n2 (branch point)
    (ws / "file.txt").write_text("v2")
    h2 = engine.git_db.get_tree_hash()
    n2 = engine.capture_drift(h2, "n2")

    # n3a (leaf A)
    engine.visit(n2.output_tree)
    (ws / "a.txt").touch()
    h3a = engine.git_db.get_tree_hash()
    engine.capture_drift(h3a, "n3a")

    # n3b (leaf B)
    engine.visit(n2.output_tree)
    (ws / "b.txt").touch()
    h3b = engine.git_db.get_tree_hash()
    engine.capture_drift(h3b, "n3b")

    return engine


def test_cache_sync(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    result = runner.invoke(app, ["cache", "sync", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("cache.sync.info.hydrating")
    mock_bus.success.assert_called_once_with("cache.sync.success")


def test_cache_rebuild_no_db(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    result = runner.invoke(app, ["cache", "rebuild", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.warning.assert_called_once_with("cache.rebuild.info.dbNotFound")
    mock_bus.info.assert_called_once_with("cache.sync.info.hydrating")
    mock_bus.success.assert_called_once_with("cache.sync.success")


def test_cache_prune_refs_with_redundancy(runner, history_with_redundant_refs, monkeypatch):
    """
    测试 prune-refs 命令是否能正确识别并删除冗余引用。
    """
    engine = history_with_redundant_refs
    work_dir = engine.root_dir
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    refs_dir = work_dir / ".git" / "refs" / "quipu" / "local" / "heads"
    assert len(list(refs_dir.iterdir())) == 5, "Pre-condition: 5 refs should exist before pruning"

    result = runner.invoke(app, ["cache", "prune-refs", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.info.assert_any_call("cache.prune.info.scanning")
    mock_bus.info.assert_any_call("cache.prune.info.found", count=3, total=5)
    mock_bus.success.assert_called_with("cache.prune.success", count=3)
    assert len(list(refs_dir.iterdir())) == 2, "Post-condition: 2 refs should remain after pruning"


def test_cache_prune_refs_no_redundancy(runner, history_with_redundant_refs, monkeypatch):
    """
    测试在没有冗余引用的情况下运行 prune-refs。
    """
    engine = history_with_redundant_refs
    work_dir = engine.root_dir
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    # 第一次运行以清理
    runner.invoke(app, ["cache", "prune-refs", "-w", str(work_dir)])
    mock_bus.reset_mock()  # 重置 mock 以进行第二次断言

    # 第二次运行，此时应没有冗余
    result = runner.invoke(app, ["cache", "prune-refs", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("cache.prune.info.scanning")
    mock_bus.success.assert_called_once_with("cache.prune.info.noRedundant")


def test_cache_prune_refs_empty_repo(runner, quipu_workspace, monkeypatch):
    """
    测试在空仓库（无任何 quipu 引用）上运行 prune-refs。
    """
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    result = runner.invoke(app, ["cache", "prune-refs", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("cache.prune.info.scanning")
    mock_bus.success.assert_called_once_with("cache.prune.info.noRedundant")
