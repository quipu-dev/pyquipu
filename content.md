好的，我理解了问题所在。当前的 `tests/helpers.py` 文件中的内存后端模拟实现 (`InMemoryDB`, `InMemoryHistoryManager`) 存在缺陷，导致了 `AttributeError` 和 `AssertionError`，使得依赖内存后端的引擎测试 (`test_engine_memory.py`) 失败。

你提供的旧版代码是正确的，它通过将节点存储的唯一事实来源 (`self.nodes`) 统一放在 `InMemoryDB` 中，并确保在创建节点时就正确链接父子关系，解决了状态不一致的问题。同时，它也包含了缺失的 `get_diff_stat` 方法。

我将生成一个计划，用你提供的正确实现来覆盖 `tests/helpers.py` 中的错误部分，同时保留文件中其他有效的、基于 Git 的辅助函数。

## [WIP] fix: 修复 `tests/helpers.py` 中错误的内存后端模拟实现

### 错误分析
当前的 `tests/helpers.py` 文件中，用于模拟 `Engine` 内存后端的 `InMemoryDB` 和 `InMemoryHistoryManager` 类存在几个严重的设计缺陷：

1.  **状态分裂**: `InMemoryDB` 和 `InMemoryHistoryManager` 各自维护了一个独立的节点列表 (`self.nodes`)，导致状态不一致。正确的做法应该是将 `InMemoryDB`作为唯一的事实来源。
2.  **父子关系链接失败**: `InMemoryHistoryManager` 的 `create_node` 方法没有在创建时正确地链接父节点，导致在 `test_plan_node_creation` 测试中，新节点的 `parent` 属性为 `None`，引发断言失败。
3.  **接口不匹配**: `InMemoryDB` 缺少 `get_diff_stat` 方法，该方法被 `Engine` 的 `capture_drift` 逻辑所调用，导致在 `test_capture_drift_from_genesis` 测试中出现 `AttributeError`。

### 用户需求
使用一份已知可用的、正确的内存后端模拟实现来完整替换 `tests/helpers.py` 中有问题的代码，以修复 `tests/engine/test_engine_memory.py` 中的测试失败。

### 评论
这是一个关键的修复，它能确保我们的核心 `Engine` 逻辑可以在一个快速、隔离的内存环境中被正确地、可靠地测试，而无需每次都依赖于较慢的、基于文件系统的 Git 操作。

### 目标
1.  使用 `write_file` 操作，将 `tests/helpers.py` 文件的内容更新为正确的版本。
2.  新的文件内容将包含：
    *   保留现有文件中正确的、基于 Git 的辅助函数 (`create_plan_node_with_change`, `create_capture_node_with_change`)。
    *   集成你提供的、正确的 `VirtualFileSystem`, `InMemoryDB`, `InMemoryHistoryManager` 实现。

### 基本原理
通过整合，我们将创建一个统一且正确的 `tests/helpers.py` 文件。新的 `InMemoryDB` 将作为节点存储的中心，而 `InMemoryHistoryManager` 将围绕它工作，确保在节点创建时就建立正确的图谱关系。这将解决所有已知的测试失败，并为未来的内存后端测试提供一个稳定的基础。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #concept/state #scope/core #ai/instruct #task/domain/testing #task/object/test-helpers #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 重写 `tests/helpers.py`

我们将用一个整合了原有 Git 辅助函数和新的正确内存后端模拟的版本来覆盖此文件。

~~~~~act
write_file
tests/helpers.py
~~~~~
~~~~~python
import hashlib
import copy
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from quipu.engine.state_machine import Engine
from quipu.interfaces.models import QuipuNode
from quipu.interfaces.storage import HistoryReader, HistoryWriter

# --- Constants ---

# The correct hash for an empty git tree.
EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# --- Git-based Test Helpers ---


def create_plan_node_with_change(
    engine: Engine, parent_hash: str, file_name: str, content: str, message: str
) -> str:
    """
    Creates a file change in the workspace and generates a new Plan node.
    Returns the output_tree hash of the new node.
    """
    (engine.root_dir / file_name).write_text(content)
    new_hash = engine.git_db.get_tree_hash()
    engine.create_plan_node(input_tree=parent_hash, output_tree=new_hash, plan_content=message)
    return new_hash


def create_capture_node_with_change(engine: Engine, file_name: str, content: str, message: str) -> str:
    """
    Creates a file change in the workspace and generates a new Capture node.
    The new node is parented to the current HEAD of the engine.
    Returns the output_tree hash of the new node.
    """
    (engine.root_dir / file_name).write_text(content)
    new_hash = engine.git_db.get_tree_hash()
    engine.capture_drift(new_hash, message=message)
    return new_hash


# --- In-Memory Backend Mocks for Engine Testing ---


class VirtualFileSystem:
    """一个简单的内存虚拟文件系统。"""

    def __init__(self):
        self._files: Dict[str, str] = {}

    def write(self, path: str, content: str):
        self._files[path] = content

    def read(self, path: str) -> Optional[str]:
        return self._files.get(path)

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

        sorted_files = sorted(self.vfs.files.items())
        hasher = hashlib.sha1()
        for path, content in sorted_files:
            hasher.update(path.encode("utf-8"))
            hasher.update(content.encode("utf-8"))

        tree_hash = hasher.hexdigest()
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


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
    """同时实现 Reader 和 Writer 接口的内存历史管理器。"""

    def __init__(self, db: InMemoryDB):
        self.db = db  # The db holds the single source of truth for nodes

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        summary_override: Optional[str] = None,
        **kwargs: Any,
    ) -> QuipuNode:
        fake_commit_hash = hashlib.sha1(f"{output_tree}{content}{time.time()}".encode()).hexdigest()

        node = QuipuNode(
            commit_hash=fake_commit_hash,
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.now(),
            filename=Path(f"memory://{fake_commit_hash}"),
            node_type=node_type,
            content=content,
            summary=summary_override or (content.splitlines()[0] if content else f"Node {output_tree[:7]}"),
        )

        # Correctly link parent upon creation
        if input_tree in self.db.nodes:
            parent_node = self.db.nodes[input_tree]
            node.parent = parent_node
            parent_node.children.append(node)

        self.db.nodes[output_tree] = node
        return node

    def load_all_nodes(self) -> List[QuipuNode]:
        # The relationships are already built, just return the list
        return sorted(list(self.db.nodes.values()), key=lambda n: n.timestamp)

    def get_node_count(self) -> int:
        return len(self.db.nodes)

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        all_nodes = sorted(self.db.nodes.values(), key=lambda n: n.timestamp, reverse=True)
        return all_nodes[offset : offset + limit]

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        candidates = list(self.db.nodes.values())

        if summary_regex:
            try:
                pattern = re.compile(summary_regex, re.IGNORECASE)
                candidates = [node for node in candidates if pattern.search(node.summary)]
            except re.error:
                return []

        if node_type:
            candidates = [node for node in candidates if node.node_type == node_type]

        candidates.sort(key=lambda n: n.timestamp, reverse=True)
        return candidates[:limit]

    def get_node_content(self, node: QuipuNode) -> str:
        return node.content

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        ancestors = set()
        if start_output_tree_hash not in self.db.nodes:
            return ancestors

        curr = self.db.nodes[start_output_tree_hash]
        while curr and curr.parent:
            parent_node = curr.parent
            ancestors.add(parent_node.output_tree)
            curr = parent_node
        return ancestors

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        descendants = set()
        if start_output_tree_hash not in self.db.nodes:
            return descendants

        queue = [self.db.nodes[start_output_tree_hash]]
        visited = {start_output_tree_hash}

        while queue:
            current_node = queue.pop(0)
            for child in current_node.children:
                if child.output_tree not in visited:
                    descendants.add(child.output_tree)
                    visited.add(child.output_tree)
                    queue.append(child)
        return descendants

    def get_node_position(self, output_tree_hash: str) -> int:
        all_nodes = sorted(self.db.nodes.values(), key=lambda n: n.timestamp, reverse=True)
        for i, node in enumerate(all_nodes):
            if node.output_tree == output_tree_hash:
                return i
        return -1

    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        return None

    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        return {}
~~~~~

### 下一步建议
在应用此修复后，请重新运行 `pytest tests/engine/test_engine_memory.py` 以确认问题已解决。如果所有测试通过，我们可以继续处理下一个任务，或者将此修复提交到版本控制中。
