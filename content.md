# refactor: 为测试实现内存存储后端

## 用户需求
你提出，为了提升测试的速度和隔离性，需要创建一个内存中的存储实现，用于替代在测试中与真实文件系统和 Git 交互的 `GitDB` 和 `GitObjectHistory...` 类。

## 评论
这是一个非常关键的架构改进。它将 `Engine` 的核心逻辑与存储后端彻底解耦，使得我们可以对 `Engine` 进行快速、可靠的单元测试，而无需处理文件 I/O 和 `git` 子进程带来的开销和不确定性。

## 目标
1.  创建一个 `InMemoryDB` 类，它将模拟 `GitDB` 的接口，但在内存中操作一个虚拟文件系统。
2.  创建 `InMemoryHistoryManager` 类，它将同时实现 `HistoryReader` 和 `HistoryWriter` 接口，在内存中管理 `QuipuNode` 对象图。
3.  将这些新的测试工具放在一个新的 `tests/helpers.py` 文件中，供测试套件共享。
4.  重构 `Engine` 和 `factory` 以支持依赖注入，使其能够接受一个数据库实例 (`GitDB` 或 `InMemoryDB`)。
5.  创建一个新的测试文件 `tests/test_engine_memory.py` 来验证这个新的内存后端是否能正确工作。

## 基本原理
这个重构的核心是**依赖注入**。

1.  **模拟 `GitDB`**: 我们将创建一个 `InMemoryDB` 类，它包含一个 `VirtualFileSystem` (一个简单的字典) 来模拟工作区。`get_tree_hash` 方法将通过对虚拟文件系统的内容进行确定性哈希来模拟 `git write-tree`，确保状态的可复现性。`checkout_tree` 则是在不同的文件系统快照之间切换。
2.  **模拟 `HistoryStorage`**: `InMemoryHistoryManager` 将直接在内存中的一个字典里创建、链接和查询 `QuipuNode` 对象，完全绕过 Git 的 commit 和 ref 系统。
3.  **注入**: `Engine` 的构造函数将被修改，不再自行创建 `GitDB`，而是接受一个外部传入的 `db` 对象。`create_engine` 工厂将负责创建生产环境下的 `GitDB` 并将其注入。在测试中，我们将创建 `InMemoryDB` 并注入。

这种方式让我们可以在不改变 `Engine` 核心业务逻辑的情况下，为其替换一个“测试用”的、完全在内存中运行的底层。

## 标签
#intent/refine #intent/tooling #flow/ready #priority/high 
#comp/engine #comp/interfaces #comp/tests 
#concept/state #concept/history 
#scope/dx #scope/core 
#ai/delegate 

---

## Script

### Acts 1: 创建测试辅助工具

首先，我们在 `tests` 目录下创建一个新的 `helpers.py` 文件，用于存放所有测试用的模拟类。

`````act
write_file tests/helpers.py
`````
`````python
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

# --- Constants ---
EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class VirtualFileSystem:
    """一个简单的内存虚拟文件系统。"""

    def __init__(self):
        self._files: Dict[str, str] = {}

    def write(self, path: str, content: str):
        self._files[path] = content

    def read(self, path: str) -> Optional[str]:
        return self._files.get(path)

    def delete(self, path: str):
        if path in self._files:
            del self._files[path]

    def exists(self, path: str) -> bool:
        return path in self._files

    def copy(self) -> "VirtualFileSystem":
        new_vfs = VirtualFileSystem()
        new_vfs._files = self._files.copy()
        return new_vfs

    @property
    def files(self) -> Dict[str, str]:
        return self._files


class InMemoryDB:
    """一个模拟 GitDB 接口的内存数据库，用于快速测试。"""

    def __init__(self):
        self.vfs = VirtualFileSystem()
        self.snapshots: Dict[str, VirtualFileSystem] = {EMPTY_TREE_HASH: VirtualFileSystem()}
        self.nodes: Dict[str, QuipuNode] = {}  # output_tree -> Node

    def get_tree_hash(self) -> str:
        """对当前 VFS 内容进行确定性哈希。"""
        if not self.vfs.files:
            return EMPTY_TREE_HASH

        # 排序以保证哈希的确定性
        sorted_files = sorted(self.vfs.files.items())
        hasher = hashlib.sha1()
        for path, content in sorted_files:
            hasher.update(path.encode("utf-8"))
            hasher.update(content.encode("utf-8"))

        tree_hash = hasher.hexdigest()
        # 存储快照
        if tree_hash not in self.snapshots:
            self.snapshots[tree_hash] = self.vfs.copy()
        return tree_hash

    def checkout_tree(self, tree_hash: str):
        if tree_hash not in self.snapshots:
            raise FileNotFoundError(f"In-memory snapshot not found for hash: {tree_hash}")
        self.vfs = self.snapshots[tree_hash].copy()

    def get_diff_name_status(self, old_tree: str, new_tree: str) -> List[Tuple[str, str]]:
        old_vfs = self.snapshots.get(old_tree, VirtualFileSystem()).files
        new_vfs = self.snapshots.get(new_tree, VirtualFileSystem()).files

        old_files = set(old_vfs.keys())
        new_files = set(new_vfs.keys())

        added = new_files - old_files
        deleted = old_files - new_files
        common = old_files & new_files

        changes = []
        for f in added:
            changes.append(("A", f))
        for f in deleted:
            changes.append(("D", f))
        for f in common:
            if old_vfs[f] != new_vfs[f]:
                changes.append(("M", f))

        return sorted(changes)

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        changes = self.get_diff_name_status(old_tree, new_tree)
        return "\n".join(f"{status}\t{path}" for status, path in changes)

    # --- Mocked/Stubbed methods from GitDB interface ---
    def hash_object(self, content_bytes: bytes, object_type: str = "blob") -> str:
        return hashlib.sha1(content_bytes).hexdigest()

    def cat_file(self, object_hash: str, object_type: str = "blob") -> bytes:
        # In memory, content is directly on the node, this isn't strictly needed
        return b""


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
    """同时实现 Reader 和 Writer 接口的内存历史管理器。"""

    def __init__(self, db: InMemoryDB):
        self.db = db  # The db holds the single source of truth for nodes

    def load_all_nodes(self) -> List[QuipuNode]:
        return list(self.db.nodes.values())

    def get_node_content(self, node: QuipuNode) -> str:
        return node.content

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        node = QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.now(),
            filename=Path(f"memory://{output_tree}"),
            node_type=node_type,
            content=content,
            summary=kwargs.get("summary_override", f"Summary for {output_tree[:7]}"),
        )

        # Link parent
        if input_tree in self.db.nodes:
            parent_node = self.db.nodes[input_tree]
            node.parent = parent_node
            parent_node.children.append(node)

        self.db.nodes[output_tree] = node
        return node
`````

### Acts 2: 重构 Engine 以支持依赖注入

现在修改 `Engine` 的构造函数，使其接受一个 `db` 对象，而不是自己创建 `GitDB`。

`````act
replace packages/quipu-engine/src/quipu/core/state_machine.py
`````
`````python
    def __init__(self, root_dir: Path, reader: HistoryReader, writer: HistoryWriter):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.quipu_dir.mkdir(exist_ok=True)  # 确保 .quipu 目录存在
        self.history_dir = self.quipu_dir / "history"
        self.head_file = self.quipu_dir / "HEAD"

        self.nav_log_file = self.quipu_dir / "nav_log"
        self.nav_ptr_file = self.quipu_dir / "nav_ptr"

        quipu_gitignore = self.quipu_dir / ".gitignore"
        if not quipu_gitignore.exists():
            try:
                quipu_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {quipu_gitignore}: {e}")

        self.git_db = GitDB(self.root_dir)
        self.reader = reader
        self.writer = writer
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None

        self._sync_persistent_ignores()
`````
`````python
    def __init__(self, root_dir: Path, db: Any, reader: HistoryReader, writer: HistoryWriter):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.quipu_dir.mkdir(exist_ok=True)  # 确保 .quipu 目录存在
        self.history_dir = self.quipu_dir / "history"
        self.head_file = self.quipu_dir / "HEAD"

        self.nav_log_file = self.quipu_dir / "nav_log"
        self.nav_ptr_file = self.quipu_dir / "nav_ptr"

        quipu_gitignore = self.quipu_dir / ".gitignore"
        if not quipu_gitignore.exists():
            try:
                quipu_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {quipu_gitignore}: {e}")

        self.git_db = db  # <-- 依赖注入
        self.reader = reader
        self.writer = writer
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None

        # Only sync ignores if it's a real git repo
        if isinstance(db, GitDB):
            self._sync_persistent_ignores()
`````

### Acts 3: 调整 Engine 工厂以注入 `GitDB`

`create_engine` 工厂现在需要将它创建的 `GitDB` 实例传递给 `Engine` 的构造函数。

`````act
replace packages/quipu-cli/src/quipu/cli/factory.py
`````
`````python
    # 5. 注入依赖并实例化 Engine
    engine = Engine(project_root, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱

    return engine
`````
`````python
    # 5. 注入依赖并实例化 Engine
    engine = Engine(project_root, db=git_db, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱

    return engine
`````

### Acts 4: 添加使用内存后端的测试

最后，我们创建一个新的测试文件来验证我们的内存后端是否按预期工作。

`````act
write_file tests/test_engine_memory.py
`````
`````python
import pytest
from pathlib import Path

from quipu.core.state_machine import Engine
from .helpers import InMemoryDB, InMemoryHistoryManager, EMPTY_TREE_HASH


@pytest.fixture
def memory_engine(tmp_path: Path) -> Engine:
    """创建一个使用完整内存后端的 Engine 实例。"""
    db = InMemoryDB()
    history_manager = InMemoryHistoryManager(db)
    # The root_dir is just a placeholder for the in-memory engine
    engine = Engine(root_dir=tmp_path, db=db, reader=history_manager, writer=history_manager)
    return engine


class TestEngineWithMemoryBackend:
    def test_align_clean_genesis(self, memory_engine: Engine):
        """测试在创世状态下的对齐。"""
        status = memory_engine.align()
        assert status == "CLEAN"
        assert memory_engine.current_node is None

    def test_capture_drift_from_genesis(self, memory_engine: Engine):
        """测试从创世状态捕获漂移。"""
        # 1. 模拟文件变更
        memory_engine.git_db.vfs.write("a.txt", "hello")
        current_hash = memory_engine.git_db.get_tree_hash()
        assert current_hash != EMPTY_TREE_HASH

        # 2. 对齐，应为 DIRTY (或 ORPHAN)
        status = memory_engine.align()
        assert status == "ORPHAN"

        # 3. 捕获漂移
        node = memory_engine.capture_drift(current_hash, message="Initial commit")
        assert node is not None
        assert node.node_type == "capture"
        assert node.input_tree == EMPTY_TREE_HASH
        assert node.output_tree == current_hash

        # 4. 再次对齐，应为 CLEAN
        status_after = memory_engine.align()
        assert status_after == "CLEAN"
        assert memory_engine.current_node == node

    def test_plan_node_creation(self, memory_engine: Engine):
        """测试 Plan 节点的创建流程。"""
        # State A
        memory_engine.git_db.vfs.write("a.txt", "v1")
        hash_a = memory_engine.git_db.get_tree_hash()
        node_a = memory_engine.create_plan_node(EMPTY_TREE_HASH, hash_a, "Plan A")

        # State B
        memory_engine.git_db.vfs.write("a.txt", "v2")
        hash_b = memory_engine.git_db.get_tree_hash()
        node_b = memory_engine.create_plan_node(hash_a, hash_b, "Plan B")

        assert len(memory_engine.history_graph) == 2
        assert node_b.parent == node_a
        assert node_a.children == [node_b]

        # 验证 checkout
        memory_engine.checkout(hash_a)
        assert memory_engine.git_db.vfs.read("a.txt") == "v1"
`````
