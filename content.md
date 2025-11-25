# feat(storage): implement qdps v1.0 phase 2 - git plumbing upgrade

## 目标
完成 QDPS v1.0 的第二阶段：Git 底层管道改造。
我们将赋予 `GitDB` 操作 Tree 和 Blob 的精细能力，并重写 Engine 的写入逻辑（`create_plan_node`, `capture_drift`），使其不再生成物理的 Markdown 文件，而是直接向 Git 对象库写入符合 QDPS 规范的“元数据/内容”双 Blob 结构。

同时，顺手修复因数据模型变更导致的 UI 测试失败，确保测试红绿条的参考价值。

## 基本原理
1.  **Git Plumbing**: 使用 `hash-object`, `mktree`, `commit-tree` 等底层命令替代高层的 `add/commit` 流程，实现对历史节点物理结构的精确控制。
2.  **原子写入**: 新的写入流程在内存中构建完整的 Commit 对象后，通过单次 `update-ref` 更新引用，消除了文件系统中间态，提升了性能和原子性。

## 标签
#feat #storage #qdps #phase-2 #git

---

## Script

### Act 1: 扩展 GitDB 底层能力

在 `packages/quipu-engine/src/quipu/core/git_db.py` 中增加对 Blob、Tree 和 Commit 的低级操作方法。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/git_db.py
~~~~~

~~~~~python
import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager
from quipu.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)

class GitDB:
    """
    Axon 的 Git 底层接口 (Plumbing Interface)。
    负责与 Git 对象数据库交互，维护 Shadow Index 和 Refs。
    """
    def __init__(self, root_dir: Path):
        if not shutil.which("git"):
            raise ExecutionError("未找到 'git' 命令。请安装 Git 并确保它在系统的 PATH 中。")

        self.root = root_dir.resolve()
        self.quipu_dir = self.root / ".quipu"
        self._ensure_git_repo()

    def _ensure_git_repo(self):
        """确保目标是一个 Git 仓库"""
        if not (self.root / ".git").is_dir():
            raise ExecutionError(f"工作目录 '{self.root}' 不是一个有效的 Git 仓库。请先运行 'git init'。")

    def _run(self, args: list[str], env: Optional[Dict] = None, input_str: Optional[str] = None, check: bool = True, log_error: bool = True) -> subprocess.CompletedProcess:
        """执行 git 命令的底层封装"""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
            
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.root,
                env=full_env,
                input=input_str,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            if log_error:
                logger.error(f"Git plumbing error: {e.stderr}")
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e

    # --- High Level Operations ---

    @contextmanager
    def shadow_index(self):
        """上下文管理器：创建一个隔离的 Shadow Index。"""
        index_path = self.quipu_dir / "tmp_index"
        self.quipu_dir.mkdir(exist_ok=True)
        env = {"GIT_INDEX_FILE": str(index_path)}
        try:
            yield env
        finally:
            if index_path.exists():
                try:
                    index_path.unlink()
                except OSError:
                    logger.warning(f"Failed to cleanup shadow index: {index_path}")

    def get_tree_hash(self) -> str:
        """计算当前工作区的 Tree Hash (Snapshot)。"""
        with self.shadow_index() as env:
            self._run(
                ["add", "-A", "--ignore-errors", ".", ":(exclude).quipu"],
                env=env
            )
            result = self._run(["write-tree"], env=env)
            return result.stdout.strip()

    def update_ref(self, ref_name: str, commit_hash: str):
        """更新引用 (如 refs/quipu/history)。"""
        self._run(["update-ref", ref_name, commit_hash])

    def get_head_commit(self) -> Optional[str]:
        """获取当前工作区 HEAD 的 Commit Hash"""
        try:
            result = self._run(["rev-parse", "HEAD"])
            return result.stdout.strip()
        except RuntimeError:
            return None

    def checkout_tree(self, tree_hash: str):
        """将工作区强制重置为目标 Tree 的状态。"""
        logger.info(f"Executing hard checkout to tree: {tree_hash[:7]}")
        self._run(["read-tree", tree_hash])
        self._run(["checkout-index", "-a", "-f"])
        self._run(["clean", "-dfx", "-e", ".quipu"])
        logger.info("✅ Workspace reset to target state.")

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()

    # --- Low Level Plumbing (QDPS v1.0) ---

    def hash_object(self, content: bytes, obj_type: str = "blob") -> str:
        """
        将内容写入 Git 对象库，返回 Hash。
        相当于: git hash-object -w --stdin -t <type>
        """
        # 注意：subprocess 传入 bytes 时，text 必须为 False 或不设置（默认）
        # 但我们之前的 _run 默认 text=True。为了支持二进制 blob，这里直接调用 subprocess
        try:
            result = subprocess.run(
                ["git", "hash-object", "-w", "--stdin", "-t", obj_type],
                cwd=self.root,
                input=content,
                capture_output=True,
                check=True
            )
            return result.stdout.decode().strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"hash-object failed: {e.stderr.decode()}")
            raise RuntimeError(f"Git hash-object failed") from e

    def mktree(self, entries: List[Tuple[str, str, str, str]]) -> str:
        """
        根据条目列表构建 Tree 对象。
        Entry 格式: (mode, type, hash, name)
        Example: ("100644", "blob", "a1b2...", "metadata.yml")
        """
        # 构建符合 git mktree 要求的输入格式: <mode> <type> <object> <file>
        # 注意: 字段间用空格分隔，但在 file 前是制表符 \t (虽然 git mktree 也接受空格，但标准是 \t)
        lines = []
        for mode, type_, hash_, name in entries:
            lines.append(f"{mode} {type_} {hash_}\t{name}")
        
        input_str = "\n".join(lines)
        
        result = self._run(["mktree"], input_str=input_str)
        return result.stdout.strip()

    def commit_tree(self, tree_hash: str, message: str, parents: List[str] = None) -> str:
        """
        创建 Commit 对象。
        """
        cmd = ["commit-tree", tree_hash, "-m", message]
        if parents:
            for p in parents:
                cmd.extend(["-p", p])
        
        result = self._run(cmd)
        return result.stdout.strip()
    
    def read_blob(self, blob_hash: str) -> bytes:
        """读取 Blob 内容 (二进制)"""
        try:
            result = subprocess.run(
                ["git", "cat-file", "-p", blob_hash],
                cwd=self.root,
                capture_output=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to read blob {blob_hash}") from e
~~~~~

### Act 2: 验证 GitDB 扩展功能

创建 `tests/test_git_db_plumbing.py`，确保新加入的底层方法工作正常。

~~~~~act
write_file tests/test_git_db_plumbing.py
~~~~~

~~~~~python
import pytest
from quipu.core.git_db import GitDB

class TestGitDBPlumbing:
    
    @pytest.fixture
    def db(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess
        subprocess.run(["git", "init"], cwd=repo, check=True)
        return GitDB(repo)

    def test_hash_object_blob(self, db):
        content = b"hello world"
        sha = db.hash_object(content)
        assert len(sha) == 40
        
        # Verify with cat-file
        read_back = db.read_blob(sha)
        assert read_back == content

    def test_mktree_and_commit(self, db):
        # 1. Create a blob
        blob_sha = db.hash_object(b"metadata content")
        
        # 2. Create a tree containing that blob
        entries = [
            ("100644", "blob", blob_sha, "metadata.yml")
        ]
        tree_sha = db.mktree(entries)
        assert len(tree_sha) == 40
        
        # 3. Create a commit
        commit_sha = db.commit_tree(tree_sha, "Test Commit")
        assert len(commit_sha) == 40
        
        # 4. Verify connectivity
        import subprocess
        log = subprocess.check_output(
            ["git", "log", "-1", "--format=%s", commit_sha], 
            cwd=db.root
        ).decode().strip()
        assert log == "Test Commit"

~~~~~

### Act 3: 重构 Engine 写入逻辑

修改 `packages/quipu-engine/src/quipu/core/state_machine.py`，注入 `MetadataFactory`，并使用双 Blob 结构重写写入方法。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~

~~~~~python
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

from .git_db import GitDB
from .history import load_history_graph
from .telemetry import MetadataFactory
from quipu.core.models import QuipuNode, QuipuMetadata

logger = logging.getLogger(__name__)

class Engine:
    """
    Axon 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.history_dir = self.quipu_dir / "history" # Deprecated but kept for read compat
        self.head_file = self.quipu_dir / "HEAD"
        
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        quipu_gitignore = self.quipu_dir / ".gitignore"
        if not quipu_gitignore.exists():
            try:
                quipu_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {quipu_gitignore}: {e}")
        
        self.git_db = GitDB(self.root_dir)
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None
        self.meta_factory = MetadataFactory()

    def _read_head(self) -> Optional[str]:
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return None

    def _write_head(self, tree_hash: str):
        try:
            self.head_file.write_text(tree_hash, encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新 HEAD 指针: {e}")

    def align(self) -> str:
        self.history_graph = load_history_graph(self.history_dir)
        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            return "CLEAN"
        
        if current_hash in self.history_graph:
            self.current_node = self.history_graph[current_hash]
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            self._write_head(current_hash)
            return "CLEAN"
        
        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
        if not self.history_graph:
            return "ORPHAN"
        return "DIRTY"

    def _persist_node(self, 
                      node_type: str, 
                      output_tree: str, 
                      content: str, 
                      message: str, 
                      input_tree: str = None) -> QuipuNode:
        """
        QDPS v1.0 核心写入逻辑：
        1. 生成 Metadata
        2. Hash Object (Meta + Content)
        3. MkTree
        4. Commit Tree
        5. Update Ref
        """
        # 1. Prepare Metadata
        meta_obj = self.meta_factory.create(node_type)
        meta_yaml = yaml.safe_dump(
            # 将 dataclass 转为 dict
            {k: v for k, v in meta_obj.__dict__.items()}, 
            sort_keys=False, 
            allow_unicode=True
        ).encode('utf-8')
        
        content_bytes = content.encode('utf-8')

        # 2. Write Blobs
        blob_meta = self.git_db.hash_object(meta_yaml)
        blob_content = self.git_db.hash_object(content_bytes)

        # 3. Build Tree
        entries = [
            ("100644", "blob", blob_meta, "metadata.yml"),
            ("100644", "blob", blob_content, "content.md")
        ]
        tree_hash = self.git_db.mktree(entries)

        # 4. Create Commit
        # 获取父 Commit (从 refs/quipu/history)
        parent_commit = None
        try:
            res = self.git_db._run(["rev-parse", "refs/quipu/history"], check=False)
            if res.returncode == 0:
                parent_commit = res.stdout.strip()
        except Exception: pass
        
        parents = [parent_commit] if parent_commit else []
        
        # 构造 Message，包含 Trailer
        full_message = f"{message}\n\nX-Quipu-Output-Tree: {output_tree}"
        
        commit_hash = self.git_db.commit_tree(tree_hash, full_message, parents)

        # 5. Update Ref
        self.git_db.update_ref("refs/quipu/history", commit_hash)
        
        # 6. Return Memory Node
        # 注意：这里我们构造一个 QuipuNode，但不再有物理 filename
        # 且 Hydration (Read) 逻辑尚未更新，所以 history_graph 可能在重启后读不到这个节点
        # 这是预期的，阶段 3 会修复读取。
        node = QuipuNode(
            output_tree=output_tree,
            metadata=meta_obj,
            content=content,
            # Legacy fields compat
            input_tree=input_tree if input_tree else "",
            timestamp=datetime.now(),
            node_type=node_type
        )
        
        self.history_graph[output_tree] = node
        self.current_node = node
        self._write_head(output_tree)
        
        return node

    def capture_drift(self, current_hash: str, message: Optional[str] = None) -> QuipuNode:
        with self.meta_factory.stopwatch():
            log_message = f"📸 正在捕获工作区漂移 (Message: {message})" if message else f"📸 正在捕获工作区漂移"
            logger.info(f"{log_message}，新状态 Hash: {current_hash[:7]}")

            genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            input_hash = genesis_hash
            
            head_hash = self._read_head()
            if head_hash and head_hash in self.history_graph:
                input_hash = head_hash
            elif self.history_graph:
                last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
                input_hash = last_node.output_tree
                logger.warning(f"⚠️  丢失 HEAD 指针，自动回退到最新历史节点: {input_hash[:7]}")

            diff_summary = self.git_db.get_diff_stat(input_hash, current_hash)
            
            user_message_section = f"### 💬 备注:\n{message}\n\n" if message else ""
            body = (
                f"# 📸 Snapshot Capture\n\n"
                f"{user_message_section}"
                f"检测到工作区发生变更。\n\n"
                f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
            )
            
            commit_msg = f"Capture: {message}" if message else f"Capture: {current_hash[:7]}"
            
        # 注意：persist_node 会使用 stopwatch 的结果，因为 stopwatch 已经退出
        return self._persist_node("capture", current_hash, body, commit_msg, input_hash)

    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> QuipuNode:
        with self.meta_factory.stopwatch():
            if input_tree == output_tree:
                logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
            else:
                logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
            
            commit_msg = f"Plan: {output_tree[:7]}"
            
        return self._persist_node("plan", output_tree, plan_content, commit_msg, input_tree)

    def checkout(self, target_hash: str):
        self.git_db.checkout_tree(target_hash)
        self._write_head(target_hash)
        if target_hash in self.history_graph:
            self.current_node = self.history_graph[target_hash]
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")
~~~~~

### Act 4: 验证写入逻辑 (Blackbox Verification)

创建 `tests/test_write_v2.py`，模拟 Engine 写入流程并验证 Git 内部结构。

~~~~~act
write_file tests/test_write_v2.py
~~~~~

~~~~~python
import pytest
import yaml
import subprocess
from quipu.core.state_machine import Engine

class TestWriteV2:
    @pytest.fixture
    def engine(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        # Config user
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu"], cwd=repo, check=True)
        return Engine(repo)

    def test_create_plan_node_structure(self, engine):
        """验证生成的 Git 对象结构是否符合 QDPS v1.0"""
        # 1. 模拟一个操作，生成 hash
        (engine.root_dir / "a.txt").write_text("v1")
        hash_v1 = engine.git_db.get_tree_hash()
        
        # 2. 创建 Plan Node
        engine.create_plan_node("genesis", hash_v1, "# My Plan\nHello")
        
        # 3. 验证 refs/quipu/history 存在
        history_sha = subprocess.check_output(
            ["git", "rev-parse", "refs/quipu/history"], 
            cwd=engine.root_dir
        ).decode().strip()
        assert len(history_sha) == 40
        
        # 4. 验证 Tree 结构
        # 获取 Commit 指向的 Tree
        commit_tree = subprocess.check_output(
            ["git", "show", "--format=%T", "-s", history_sha],
            cwd=engine.root_dir
        ).decode().strip()
        
        # 列出 Tree 内容
        ls_tree = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", commit_tree],
            cwd=engine.root_dir
        ).decode().strip().splitlines()
        
        assert "metadata.yml" in ls_tree
        assert "content.md" in ls_tree
        
        # 5. 验证 Metadata 内容
        # 读取 metadata.yml blob
        meta_content = subprocess.check_output(
            ["git", "show", f"{commit_tree}:metadata.yml"],
            cwd=engine.root_dir
        ).decode()
        
        meta = yaml.safe_load(meta_content)
        assert meta["meta_version"] == "1.0"
        assert meta["type"] == "plan"
        assert meta["env"]["python"] is not None

    def test_capture_drift_structure(self, engine):
        """验证 Capture 节点的结构"""
        # 1. 制造漂移
        (engine.root_dir / "drift.txt").write_text("oops")
        drift_hash = engine.git_db.get_tree_hash()
        
        # 2. 捕获
        engine.capture_drift(drift_hash, "Auto save")
        
        # 3. 获取最新 Commit 消息
        msg = subprocess.check_output(
            ["git", "log", "-1", "--format=%B", "refs/quipu/history"],
            cwd=engine.root_dir
        ).decode()
        
        assert "Capture: Auto save" in msg
        assert f"X-Quipu-Output-Tree: {drift_hash}" in msg
~~~~~

### Act 5: 修复 UI 测试 (Fix Broken Tests)

修改 `tests/test_ui_logic.py` 和 `tests/test_ui_reachability.py`，使用关键字参数初始化 `QuipuNode`，适配新加入的 `metadata` 字段位置变更。

~~~~~act
replace tests/test_ui_logic.py
~~~~~

~~~~~python
        # A <- B <- C
        node_a = QuipuNode("root", "a", datetime(2023,1,1), Path("f"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023,1,2), Path("f"), "plan")
        node_c = QuipuNode("b", "c", datetime(2023,1,3), Path("f"), "plan")
~~~~~

~~~~~python
        # A <- B <- C
        node_a = QuipuNode(output_tree="a", input_tree="root", timestamp=datetime(2023,1,1), filename=Path("f"), node_type="plan")
        node_b = QuipuNode(output_tree="b", input_tree="a", timestamp=datetime(2023,1,2), filename=Path("f"), node_type="plan")
        node_c = QuipuNode(output_tree="c", input_tree="b", timestamp=datetime(2023,1,3), filename=Path("f"), node_type="plan")
~~~~~

~~~~~act
replace tests/test_ui_logic.py
~~~~~

~~~~~python
        # A <- B
        # A <- C
        node_a = QuipuNode("root", "a", datetime(2023,1,1), Path("f"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023,1,2), Path("f"), "plan")
        node_c = QuipuNode("a", "c", datetime(2023,1,3), Path("f"), "plan") # Branch C is newer
~~~~~

~~~~~python
        # A <- B
        # A <- C
        node_a = QuipuNode(output_tree="a", input_tree="root", timestamp=datetime(2023,1,1), filename=Path("f"), node_type="plan")
        node_b = QuipuNode(output_tree="b", input_tree="a", timestamp=datetime(2023,1,2), filename=Path("f"), node_type="plan")
        node_c = QuipuNode(output_tree="c", input_tree="a", timestamp=datetime(2023,1,3), filename=Path("f"), node_type="plan") # Branch C is newer
~~~~~

~~~~~act
replace tests/test_ui_logic.py
~~~~~

~~~~~python
    def test_get_node_summary(self):
        node = QuipuNode("a", "b", datetime.now(), Path("f"), "plan", content="~~~act\nrun\n~~~")
        app = QuipuUiApp([], None)
        assert app._get_node_summary(node) == "run"
~~~~~

~~~~~python
    def test_get_node_summary(self):
        node = QuipuNode(output_tree="b", input_tree="a", timestamp=datetime.now(), filename=Path("f"), node_type="plan", content="~~~act\nrun\n~~~")
        app = QuipuUiApp([], None)
        assert app._get_node_summary(node) == "run"
~~~~~

~~~~~act
replace tests/test_ui_reachability.py
~~~~~

~~~~~python
        """
        root = QuipuNode("null", "root", datetime(2023,1,1), Path("f"), "plan")
        
        node_a = QuipuNode("root", "a", datetime(2023,1,2), Path("f"), "plan")
        node_a.parent = root
        root.children.append(node_a)
        
        node_b = QuipuNode("root", "b", datetime(2023,1,3), Path("f"), "plan")
        node_b.parent = root
        root.children.append(node_b)
        
        node_current = QuipuNode("a", "curr", datetime(2023,1,4), Path("f"), "plan")
~~~~~

~~~~~python
        """
        root = QuipuNode(output_tree="root", input_tree="null", timestamp=datetime(2023,1,1), filename=Path("f"), node_type="plan")
        
        node_a = QuipuNode(output_tree="a", input_tree="root", timestamp=datetime(2023,1,2), filename=Path("f"), node_type="plan")
        node_a.parent = root
        root.children.append(node_a)
        
        node_b = QuipuNode(output_tree="b", input_tree="root", timestamp=datetime(2023,1,3), filename=Path("f"), node_type="plan")
        node_b.parent = root
        root.children.append(node_b)
        
        node_current = QuipuNode(output_tree="curr", input_tree="a", timestamp=datetime(2023,1,4), filename=Path("f"), node_type="plan")
~~~~~

~~~~~act
replace tests/test_ui_reachability.py
~~~~~

~~~~~python
    def test_filter_unreachable(self):
        """测试 populate 时的过滤逻辑"""
        # Linear: A -> B
        node_a = QuipuNode("root", "a", datetime(2023,1,1), Path("f"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023,1,2), Path("f"), "plan")
        # Link them manually as load_history_graph would
        node_b.parent = node_a
        node_a.children.append(node_b)
        
        # Focus on A. 
        # Reachable: A (self), B (descendant). 
        # Wait, if focus is A, B is reachable via Redo. Correct.
        
        # Let's make an unreachable node C (sibling of A)
        node_c = QuipuNode("root", "c", datetime(2023,1,3), Path("f"), "plan")
        
        nodes = [node_a, node_b, node_c]
~~~~~

~~~~~python
    def test_filter_unreachable(self):
        """测试 populate 时的过滤逻辑"""
        # Linear: A -> B
        node_a = QuipuNode(output_tree="a", input_tree="root", timestamp=datetime(2023,1,1), filename=Path("f"), node_type="plan")
        node_b = QuipuNode(output_tree="b", input_tree="a", timestamp=datetime(2023,1,2), filename=Path("f"), node_type="plan")
        # Link them manually as load_history_graph would
        node_b.parent = node_a
        node_a.children.append(node_b)
        
        # Focus on A. 
        # Reachable: A (self), B (descendant). 
        # Wait, if focus is A, B is reachable via Redo. Correct.
        
        # Let's make an unreachable node C (sibling of A)
        node_c = QuipuNode(output_tree="c", input_tree="root", timestamp=datetime(2023,1,3), filename=Path("f"), node_type="plan")
        
        nodes = [node_a, node_b, node_c]
~~~~~