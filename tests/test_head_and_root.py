import pytest
import os
from pathlib import Path
from quipu.core.state_machine import Engine
from quipu.cli.controller import find_project_root
from quipu.core.file_system_storage import FileSystemHistoryReader, FileSystemHistoryWriter

class TestHeadTracking:
    @pytest.fixture
    def engine_with_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        # Config git user
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Axon Test"], cwd=repo, check=True)
        
        history_dir = repo / ".quipu" / "history"
        reader = FileSystemHistoryReader(history_dir)
        writer = FileSystemHistoryWriter(history_dir)
        return Engine(repo, reader=reader, writer=writer)

    def test_head_persistence(self, engine_with_repo):
        """测试 HEAD 指针的创建和更新"""
        engine = engine_with_repo
        
        # 1. 初始状态，无 HEAD
        assert not engine.head_file.exists()
        assert engine._read_head() is None
        
        # 2. 创建一个 Plan 节点
        # 这会自动更新 HEAD
        (engine.root_dir / "a.txt").touch()
        tree1 = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", tree1, "plan content")
        
        assert engine.head_file.exists()
        assert engine._read_head() == tree1
        
        # 3. Align 应该保持 HEAD
        engine.align()
        assert engine._read_head() == tree1
        
    def test_drift_uses_head(self, engine_with_repo):
        """测试漂移捕获时使用 HEAD 作为父节点"""
        engine = engine_with_repo
        
        # 1. 建立 State A 并确立 HEAD
        (engine.root_dir / "f.txt").write_text("v1")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "setup")
        assert engine._read_head() == hash_a
        
        # 2. 制造漂移 (State B)
        (engine.root_dir / "f.txt").write_text("v2")
        hash_b = engine.git_db.get_tree_hash()
        
        # 3. 捕获漂移
        # 此时 engine 应该读取 HEAD (hash_a) 作为 input_tree
        capture_node = engine.capture_drift(hash_b)
        
        assert capture_node.input_tree == hash_a
        assert capture_node.output_tree == hash_b
        
        # 4. 验证 capture 后 HEAD 更新
        assert engine._read_head() == hash_b

    def test_checkout_updates_head(self, engine_with_repo):
        """验证 engine.checkout 正确更新 HEAD"""
        engine = engine_with_repo
        
        # 1. Create State A (Plan)
        (engine.root_dir / "f.txt").write_text("v1")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "State A")
        
        # 2. Create State B (Plan)
        (engine.root_dir / "f.txt").write_text("v2")
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")
        
        assert engine._read_head() == hash_b
        
        # 3. Checkout to State A
        engine.checkout(hash_a)
        
        # 4. Assert Physical State
        assert (engine.root_dir / "f.txt").read_text() == "v1"
        
        # 5. Assert Logical State (HEAD)
        assert engine._read_head() == hash_a

class TestRootDiscovery:
    def test_find_project_root(self, tmp_path):
        # /project/.git
        # /project/src/subdir
        project = tmp_path / "project"
        project.mkdir()
        (project / ".git").mkdir()
        
        subdir = project / "src" / "subdir"
        subdir.mkdir(parents=True)
        
        # Case 1: From subdir
        assert find_project_root(subdir) == project.resolve()
        
        # Case 2: From root
        assert find_project_root(project) == project.resolve()
        
        # Case 3: Outside
        outside = tmp_path / "outside"
        outside.mkdir()
        assert find_project_root(outside) is None