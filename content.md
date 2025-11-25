# fix-core 引入 HEAD 指针与优化根目录检索

## 目标
1.  **建立 HEAD 指针机制**: 在 `.axon/HEAD` 中持久化存储当前所处的逻辑节点 Hash。这确保了当发生漂移 (Drift) 时，系统知道是从“哪里”漂移出来的，从而能够正确地链接父子节点 (`input_tree` -> `output_tree`)。
2.  **增强根目录发现**: 确保 CLI 命令无论在项目的哪个子目录下执行，都能自动向上递归查找到项目根目录，从而正确加载 `GitDB` 和配置。

## 基本原理
*   **HEAD 的必要性**: 在 Git 中，HEAD 指向当前分支。在 Quipu 中，我们需要一个类似的机制来指向“上一个已知的同步状态”。没有它，任何从 Dirty 状态生成的 Capture 节点都会丢失其父节点信息，退化为创世节点 (Genesis Node) 的子节点。
*   **Root Discovery**: `GitDB` 需要在 Git 根目录下运行。目前的实现过于依赖 `CWD` (当前工作目录)。我们需要将 `controller.py` 中的 `_find_project_root` 逻辑提升为公共组件，并在所有 CLI 入口处强制应用。

## 标签
 #fix #core #engine #cli

---

## Script

### Act 1: 提升 `find_project_root` 为公共工具

我们将 `core/controller.py` 中的私有函数 `_find_project_root` 提升为公共函数，以便 `main.py` 可以调用它来解决路径问题。

~~~~~act
replace core/controller.py
~~~~~

~~~~~python
logger = logging.getLogger(__name__)

def _find_project_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
~~~~~

~~~~~python
logger = logging.getLogger(__name__)

def find_project_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
~~~~~

~~~~~act
replace core/controller.py
~~~~~

~~~~~python
    # 3. Project Root (Highest priority)
    project_root = _find_project_root(work_dir)
    if project_root:
        proj_acts = project_root / ".axon" / "acts"
~~~~~

~~~~~python
    # 3. Project Root (Highest priority)
    project_root = find_project_root(work_dir)
    if project_root:
        proj_acts = project_root / ".axon" / "acts"
~~~~~

~~~~~act
replace core/controller.py
~~~~~

~~~~~python
    try:
        # --- Phase 0: Root Canonicalization (根目录规范化) ---
        # 无论用户从哪个子目录启动，都必须找到并使用唯一的项目根。
        # 这是确保 Engine 和 Executor 上下文一致性的关键。
        project_root = _find_project_root(work_dir)
        if not project_root:
            # 如果不在 Git 仓库内，则使用原始 work_dir，但 Engine 初始化会失败。
~~~~~

~~~~~python
    try:
        # --- Phase 0: Root Canonicalization (根目录规范化) ---
        # 无论用户从哪个子目录启动，都必须找到并使用唯一的项目根。
        # 这是确保 Engine 和 Executor 上下文一致性的关键。
        project_root = find_project_root(work_dir)
        if not project_root:
            # 如果不在 Git 仓库内，则使用原始 work_dir，但 Engine 初始化会失败。
~~~~~

### Act 2: 在 Engine 中实现 HEAD 逻辑

我们需要修改 `core/engine.py`，增加对 `.axon/HEAD` 的读写支持，并在 `align` 和 `capture_drift` 中集成此逻辑。

~~~~~act
write_file core/engine.py
~~~~~

~~~~~python
import logging
from pathlib import Path
from typing import Dict, Optional
import yaml
from datetime import datetime

from .git_db import GitDB
from .history import load_history_graph
from .models import AxonNode

logger = logging.getLogger(__name__)

class Engine:
    """
    Axon 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.axon_dir = self.root_dir / ".axon"
        self.history_dir = self.axon_dir / "history"
        self.head_file = self.axon_dir / "HEAD"
        
        # 确保目录结构存在
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # 核心：确保 .axon 目录被 Git 忽略
        axon_gitignore = self.axon_dir / ".gitignore"
        if not axon_gitignore.exists():
            try:
                axon_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {axon_gitignore}: {e}")
        
        self.git_db = GitDB(self.root_dir)
        self.history_graph: Dict[str, AxonNode] = {}
        self.current_node: Optional[AxonNode] = None

    def _read_head(self) -> Optional[str]:
        """读取 .axon/HEAD 文件中的 Hash"""
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return None

    def _write_head(self, tree_hash: str):
        """更新 .axon/HEAD"""
        try:
            self.head_file.write_text(tree_hash, encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新 HEAD 指针: {e}")

    def align(self) -> str:
        """
        核心对齐方法：确定 "我现在在哪"。
        返回状态: "CLEAN", "DIRTY", "ORPHAN"
        """
        # 1. 加载或重新加载历史
        self.history_graph = load_history_graph(self.history_dir)
        
        # 2. 获取当前物理状态
        current_hash = self.git_db.get_tree_hash()

        # 3. 特殊情况：处理创世状态 (空仓库)
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            # 创世状态不写入 HEAD，或者写入空？暂不写入。
            return "CLEAN"
        
        # 4. 在逻辑图谱中定位
        if current_hash in self.history_graph:
            self.current_node = self.history_graph[current_hash]
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            # 对齐成功，更新 HEAD
            self._write_head(current_hash)
            return "CLEAN"
        
        # 未找到匹配节点，进入漂移检测
        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
        
        if not self.history_graph:
            return "ORPHAN" # 历史为空，但工作区非空
        
        return "DIRTY"

    def capture_drift(self, current_hash: str, message: Optional[str] = None) -> AxonNode:
        """
        捕获当前工作区的漂移，生成一个新的 CaptureNode。
        """
        log_message = f"📸 正在捕获工作区漂移 (Message: {message})" if message else f"📸 正在捕获工作区漂移"
        logger.info(f"{log_message}，新状态 Hash: {current_hash[:7]}")

        # 1. 确定父节点 (input_tree)
        # 优先使用 HEAD 指针，其次尝试从历史中推断，最后回退到创世 Hash
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        input_hash = genesis_hash
        
        head_hash = self._read_head()
        if head_hash and head_hash in self.history_graph:
            input_hash = head_hash
        elif self.history_graph:
            # Fallback: 使用时间戳最新的节点（风险：可能导致跳线，但在无 HEAD 时是唯一选择）
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            logger.warning(f"⚠️  丢失 HEAD 指针，自动回退到最新历史节点: {input_hash[:7]}")
        
        # 获取父 Commit 用于 Git 锚定
        last_commit_hash = None
        # 这里逻辑简化：不再依赖 rev-parse refs/axon/history，而是尝试通过 input_hash 找关系
        # 但为了保持兼容，我们还是尝试获取
        res = self.git_db._run(["rev-parse", "refs/axon/history"], check=False)
        if res.returncode == 0:
            last_commit_hash = res.stdout.strip()

        # 2. 生成差异摘要
        diff_summary = self.git_db.get_diff_stat(input_hash, current_hash)
        
        # 3. 构建节点内容和元数据
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_hash}_{current_hash}_{ts_str}.md"
        
        meta = {"type": "capture", "input_tree": input_hash, "output_tree": current_hash}
        
        user_message_section = f"### 💬 备注:\n{message}\n\n" if message else ""
        body = (
            f"# 📸 Snapshot Capture\n\n"
            f"{user_message_section}"
            f"检测到工作区发生变更。\n\n"
            f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
        )
        
        # 4. 写入文件
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"
        filename.write_text(frontmatter + body, "utf-8")
        
        # 5. 创建锚点 Commit
        commit_msg = f"Axon Save: {message}" if message else f"Axon Capture: {current_hash[:7]}"
        parents = [last_commit_hash] if last_commit_hash else []
        new_commit_hash = self.git_db.create_anchor_commit(current_hash, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/axon/history", new_commit_hash)

        # 6. 更新内存状态
        new_node = AxonNode(
            input_tree=input_hash,
            output_tree=current_hash,
            timestamp=timestamp,
            filename=filename,
            node_type="capture",
            content=body
        )
        
        self.history_graph[current_hash] = new_node
        self.current_node = new_node
        
        # 7. 关键：更新 HEAD 指向新的捕获节点
        self._write_head(current_hash)
        
        logger.info(f"✅ 捕获完成，新节点已创建: {filename.name}")
        return new_node

    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> AxonNode:
        """
        将一次成功的 Plan 执行固化为历史节点。
        """
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
        
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_tree}_{output_tree}_{ts_str}.md"
        
        meta = {
            "type": "plan",
            "input_tree": input_tree,
            "output_tree": output_tree
        }
        
        body = f"{plan_content.strip()}\n"
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"
        
        filename.write_text(frontmatter + body, "utf-8")
        
        # Git 锚定逻辑保持不变...
        parent_commit = None
        try:
            res = self.git_db._run(["rev-parse", "refs/axon/history"], check=False)
            if res.returncode == 0:
                parent_commit = res.stdout.strip()
        except Exception: pass
            
        commit_msg = f"Axon Plan: {output_tree[:7]}"
        parents = [parent_commit] if parent_commit else []
        
        new_commit_hash = self.git_db.create_anchor_commit(output_tree, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/axon/history", new_commit_hash)
        
        new_node = AxonNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=timestamp,
            filename=filename,
            node_type="plan",
            content=body
        )
        
        self.history_graph[output_tree] = new_node
        self.current_node = new_node
        
        # 关键：更新 HEAD
        self._write_head(output_tree)
        
        logger.info(f"✅ Plan 已归档: {filename.name}")
        return new_node
~~~~~

### Act 3: 修复 CLI 中的根目录发现

修改 `main.py`，在执行任何操作前，先通过 `find_project_root` 解析出正确的根目录，解决子目录执行报错的问题。

~~~~~act
replace main.py
~~~~~

~~~~~python
from logger_config import setup_logging
from core.controller import run_axon
from config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from core.plugin_loader import load_plugins
~~~~~

~~~~~python
from logger_config import setup_logging
from core.controller import run_axon, find_project_root
from config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from core.plugin_loader import load_plugins
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
# --- 导航命令辅助函数 ---
def _find_current_node(engine: Engine, graph: Dict[str, AxonNode]) -> Optional[AxonNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
~~~~~

~~~~~python
def _resolve_root(work_dir: Path) -> Path:
    """辅助函数：解析项目根目录，如果未找到则回退到 work_dir"""
    root = find_project_root(work_dir)
    return root if root else work_dir

# --- 导航命令辅助函数 ---
def _find_current_node(engine: Engine, graph: Dict[str, AxonNode]) -> Optional[AxonNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    from core.history import load_all_history_nodes, load_history_graph
    
    engine = Engine(work_dir)
    all_nodes = load_all_history_nodes(engine.history_dir)
~~~~~

~~~~~python
    from core.history import load_all_history_nodes, load_history_graph
    
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    all_nodes = load_all_history_nodes(engine.history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    捕获当前工作区的状态，创建一个“微提交”快照。
    """
    setup_logging()
    engine = Engine(work_dir)
    status = engine.align()
    if status == "CLEAN":
~~~~~

~~~~~python
    """
    捕获当前工作区的状态，创建一个“微提交”快照。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    status = engine.align()
    if status == "CLEAN":
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    与远程仓库同步 Axon 历史图谱。
    """
    setup_logging()
    work_dir = work_dir.resolve()
    config = ConfigManager(work_dir)
    if remote is None:
~~~~~

~~~~~python
    """
    与远程仓库同步 Axon 历史图谱。
    """
    setup_logging()
    work_dir = _resolve_root(work_dir) # Sync needs root
    config = ConfigManager(work_dir)
    if remote is None:
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    丢弃工作区所有未记录的变更，恢复到上一个干净状态。
    """
    setup_logging()
    engine = Engine(work_dir)
    history_dir = work_dir.resolve() / ".axon" / "history"
    graph = load_history_graph(history_dir)
~~~~~

~~~~~python
    """
    丢弃工作区所有未记录的变更，恢复到上一个干净状态。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    history_dir = engine.history_dir
    graph = load_history_graph(history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    将工作区恢复到指定的历史节点状态。
    """
    setup_logging()
    history_dir = work_dir.resolve() / ".axon" / "history"
    graph = load_history_graph(history_dir)
    matches = [node for sha, node in graph.items() if sha.startswith(hash_prefix)]
    if not matches:
        typer.secho(f"❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    if len(matches) > 1:
        typer.secho(f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    target_node = matches[0]
    target_tree_hash = target_node.output_tree
    engine = Engine(work_dir)
    status = engine.align()
~~~~~

~~~~~python
    """
    将工作区恢复到指定的历史节点状态。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    history_dir = engine.history_dir
    
    graph = load_history_graph(history_dir)
    matches = [node for sha, node in graph.items() if sha.startswith(hash_prefix)]
    if not matches:
        typer.secho(f"❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    if len(matches) > 1:
        typer.secho(f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    target_node = matches[0]
    target_tree_hash = target_node.output_tree
    
    status = engine.align()
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    向上移动到当前状态的父节点 (类似 Ctrl+Z)。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~python
    """
    向上移动到当前状态的父节点 (类似 Ctrl+Z)。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    向下移动到子节点 (类似 Ctrl+Y)。默认选择最新的子节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~python
    """
    向下移动到子节点 (类似 Ctrl+Y)。默认选择最新的子节点。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    在同一父节点的兄弟分支间，切换到上一个 (更旧的) 节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~python
    """
    在同一父节点的兄弟分支间，切换到上一个 (更旧的) 节点。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    在同一父节点的兄弟分支间，切换到下一个 (更新的) 节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~python
    """
    在同一父节点的兄弟分支间，切换到下一个 (更新的) 节点。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    engine = Engine(real_root)
    graph = load_history_graph(engine.history_dir)
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    """
    显示 Axon 历史图谱日志。
    """
    setup_logging()
    history_dir = work_dir.resolve() / ".axon" / "history"
    if not history_dir.exists():
~~~~~

~~~~~python
    """
    显示 Axon 历史图谱日志。
    """
    setup_logging()
    real_root = _resolve_root(work_dir)
    history_dir = real_root / ".axon" / "history"
    if not history_dir.exists():
~~~~~

### Act 4: 补充测试用例

创建一个新的测试文件 `tests/test_head_and_root.py` 来验证这两个修复。

~~~~~act
write_file tests/test_head_and_root.py
~~~~~

~~~~~python
import pytest
import os
from pathlib import Path
from core.engine import Engine
from core.controller import find_project_root

class TestHeadTracking:
    @pytest.fixture
    def engine_with_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        # Config git user
        subprocess.run(["git", "config", "user.email", "test@axon.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Axon Test"], cwd=repo, check=True)
        return Engine(repo)

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
~~~~~