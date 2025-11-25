import pytest
import subprocess
import json
from pathlib import Path
from datetime import datetime
from quipu.core.git_db import GitDB
from quipu.core.migration import HistoryMigrator
from quipu.core.file_system_storage import FileSystemHistoryWriter

@pytest.fixture
def legacy_env(tmp_path):
    """创建一个包含旧版历史记录的 Git 仓库环境"""
    repo = tmp_path / "legacy_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "migrator@quipu.dev"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Migrator Bot"], cwd=repo, check=True)
    
    # 模拟旧版写入器
    fs_writer = FileSystemHistoryWriter(repo / ".quipu" / "history")
    
    return repo, fs_writer

def test_migration_linear_history(legacy_env):
    """测试标准线性历史的迁移"""
    repo, fs_writer = legacy_env
    git_db = GitDB(repo)
    
    # 1. 创建旧版历史
    # Genesis -> A
    h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ha = "a" * 40
    node_a = fs_writer.create_node("plan", h0, ha, "Plan A")
    
    # A -> B
    hb = "b" * 40
    node_b = fs_writer.create_node("plan", ha, hb, "Plan B")
    
    # 2. 执行迁移
    migrator = HistoryMigrator(repo, git_db)
    count = migrator.migrate()
    
    assert count == 2
    
    # 3. 验证 Git 引用
    ref_head = git_db._run(["rev-parse", "refs/quipu/history"]).stdout.strip()
    assert len(ref_head) == 40
    
    # 4. 验证节点链 (B -> A)
    # 检查 Head (应该对应 Node B)
    log_entries = git_db.log_ref("refs/quipu/history")
    assert len(log_entries) == 2
    
    head_entry = log_entries[0] # Newest
    assert "Plan B" in head_entry["body"]
    
    parent_entry = log_entries[1]
    assert "Plan A" in parent_entry["body"]
    
    # 5. 验证 Metadata
    # 读取 Head Commit 的 Tree -> metadata.json
    tree_hash = head_entry["tree"]
    tree_content = git_db.cat_file(tree_hash, "tree").decode()
    meta_blob_hash = [l.split()[2] for l in tree_content.splitlines() if "metadata.json" in l][0]
    
    meta_bytes = git_db.cat_file(meta_blob_hash, "blob")
    meta = json.loads(meta_bytes)
    
    assert meta["meta_version"] == "1.0-migrated"
    assert meta["generator"]["id"] == "manual-migrated"
    assert "migration_info" in meta
    assert meta["type"] == "plan"
    assert meta["summary"] == "Plan B"

def test_migration_broken_chain(legacy_env):
    """测试断链节点的处理（应作为新根）"""
    repo, fs_writer = legacy_env
    git_db = GitDB(repo)
    
    h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ha = "a" * 40
    
    # 节点 A: 正常根
    fs_writer.create_node("plan", h0, ha, "Plan A")
    
    # 节点 C: 断链 (Input 是 Unknown)
    hun = "unknown" * 5 # invalid hash but serves as key
    hc = "c" * 40
    fs_writer.create_node("plan", hun, hc, "Plan C")
    
    migrator = HistoryMigrator(repo, git_db)
    count = migrator.migrate()
    
    assert count == 2
    
    # 验证 C 是一个孤立的根 (无 Parent)
    # 我们需要找到 C 对应的 Commit
    # 由于 update-ref 会指向最新的，如果时间戳 C > A，Head 是 C
    # 假设 fs_writer 是按顺序调用的，C 的时间戳确实较新
    
    head_commit = git_db._run(["rev-parse", "refs/quipu/history"]).stdout.strip()
    head_info = git_db.log_ref(head_commit)[0]
    
    assert "Plan C" in head_info["body"]
    # 检查 Parent 字段 (git log output: hash\nparent\n...)
    # log_ref 解析后的 parent 字段
    assert head_info["parent"] == "" # 无父节点

def test_migration_dry_run(legacy_env):
    repo, fs_writer = legacy_env
    git_db = GitDB(repo)
    
    fs_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "a"*40, "Plan A")
    
    migrator = HistoryMigrator(repo, git_db)
    count = migrator.migrate(dry_run=True)
    
    assert count == 1
    # 验证未创建引用
    assert not git_db.has_quipu_ref()