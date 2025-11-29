好的，我理解了。当前的 `tests/helpers.py` 文件中的内存模拟后端 (`in-memory backend`) 存在功能缺失和逻辑错误（幻觉），导致依赖它的测试（如 `Engine` 的单元测试）不可靠。你需要我基于你提供的、之前可用的 `InMemoryDB` 实现，来重写 `tests/helpers.py`，创建一个功能完备、高保真度的内存测试助手。

我将生成一个计划，使用 `write_file` 指令一次性地、完整地替换 `tests/helpers.py` 的内容。新的实现将融合你提供的代码中的健壮逻辑和当前代码中一些好的模式（如图重构），以确保我们得到一个可靠的、功能齐全的内存测试后端。

## [WIP] refactor(tests): 重写 in-memory 测试助手以提高保真度和正确性

### 错误分析
当前的 `tests/helpers.py` 文件中的内存模拟后端存在严重的功能缺陷：
1.  **`InMemoryDB.get_diff_name_status`** 仅是一个空实现 (`return []`)，这导致了依赖它的 `capture_drift` 等功能的摘要生成逻辑在测试中完全失效。
2.  **`InMemoryHistoryManager`** 缺失了大量 `HistoryReader` 接口的关键方法实现，如 `find_nodes`, `get_ancestor_output_trees`, `get_descendant_output_trees` 等，它们都是空的或不存在的。
3.  这些缺陷导致依赖内存后端的单元测试（如 `tests/engine/test_engine_memory.py` 和 `tests/cli/test_view_model.py`）无法准确地模拟真实场景，甚至无法测试某些核心功能（如 TUI 的可达性过滤）。

### 用户需求
基于一个之前可用的、功能更完整的内存后端实现，完整地重写 `tests/helpers.py` 文件。新的助手必须：
1.  提供一个功能完备的、高保真度的 `InMemoryDB`，特别是 `get_diff_name_status` 方法。
2.  提供一个完整实现了 `HistoryReader` 和 `HistoryWriter` 所有接口的 `InMemoryHistoryManager`。
3.  确保 `Engine` 在使用此内存后端时，其行为与使用真实 Git 后端时在逻辑上是一致的。

### 评论
这是一个至关重要的重构。一个可靠的、快速的内存测试后端是实现 `Engine` 和 `ViewModel` 等核心组件的健壮单元测试的基石。它能让我们在不依赖真实文件系统和 Git 子进程的情况下，隔离并验证核心的图谱逻辑、状态转换和数据查询逻辑，从而极大地提升测试速度和稳定性。

### 目标
1.  创建一个新的 `tests/helpers.py` 文件。
2.  在该文件中，实现一个 `VirtualFileSystem` 类来模拟文件操作。
3.  实现一个 `InMemoryDB` 类，它能模拟 `GitDB` 的核心功能，包括基于 VFS 内容生成确定性哈希、创建状态快照、恢复状态 (`checkout_tree`) 以及计算状态差异 (`get_diff_name_status`)。
4.  实现一个 `InMemoryHistoryManager` 类，它完整地实现了 `HistoryReader` 和 `HistoryWriter` 接口，能够进行节点的创建、加载、父子关系链接、查找和遍历。
5.  保留文件中原有的、基于真实 Git 环境的测试助手函数 (`create_plan_node_with_change`, `create_capture_node_with_change`)，因为它们在集成测试中仍然有用。

### 基本原理
我们将采用你提供的可靠实现作为蓝本，因为它包含了所有关键功能的正确逻辑。同时，我们会对结构进行微调，以确保接口的清晰和实现的健壮性。例如，我们会将节点（Nodes）的管理放在 `InMemoryHistoryManager` 中，而状态快照（Snapshots）的管理放在 `InMemoryDB` 中，以实现更好的关注点分离。最终，通过一个 `write_file` 操作，我们将这个经过精心设计的、完整的内存后端写入 `tests/helpers.py`，从而一劳永逸地解决当前测试助手的功能缺陷问题。

### 标签
#intent/refactor #intent/fix #flow/ready #priority/high #comp/tests #concept/state #concept/history #scope/dx #ai/instruct #task/domain/testing #task/object/test-helpers #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 重写 `tests/helpers.py`

这个操作将使用一个完整的、经过验证的实现来覆盖当前的 `tests/helpers.py` 文件。

~~~~~act
write_file tests/helpers.py
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


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
    """同时实现 Reader 和 Writer 接口的内存历史管理器。"""

    def __init__(self, db: InMemoryDB):
        self.db = db
        self.nodes: Dict[str, QuipuNode] = {}  # output_tree -> QuipuNode

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

        self.nodes[output_tree] = node
        return node

    def load_all_nodes(self) -> List[QuipuNode]:
        """加载所有节点并重建父子关系图。"""
        all_nodes = list(self.nodes.values())
        # Reset relationships before rebuilding
        for node in all_nodes:
            node.parent = None
            node.children = []

        for node in all_nodes:
            if node.input_tree in self.nodes:
                parent_node = self.nodes[node.input_tree]
                node.parent = parent_node
                if node not in parent_node.children:
                    parent_node.children.append(node)

        return sorted(all_nodes, key=lambda n: n.timestamp)

    def get_node_count(self) -> int:
        return len(self.nodes)

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        all_nodes = sorted(self.nodes.values(), key=lambda n: n.timestamp, reverse=True)
        return all_nodes[offset : offset + limit]

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        candidates = list(self.nodes.values())

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
        if start_output_tree_hash not in self.nodes:
            return ancestors

        curr = self.nodes[start_output_tree_hash]
        while curr and curr.input_tree in self.nodes:
            parent_node = self.nodes[curr.input_tree]
            ancestors.add(parent_node.output_tree)
            curr = parent_node
        return ancestors

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        descendants = set()
        if start_output_tree_hash not in self.nodes:
            return descendants

        queue = [self.nodes[start_output_tree_hash]]
        visited = {start_output_tree_hash}

        while queue:
            current_node = queue.pop(0)
            # Rebuild children on the fly for correctness
            children = [n for n in self.nodes.values() if n.input_tree == current_node.output_tree]
            for child in children:
                if child.output_tree not in visited:
                    descendants.add(child.output_tree)
                    visited.add(child.output_tree)
                    queue.append(child)
        return descendants

    def get_node_position(self, output_tree_hash: str) -> int:
        all_nodes = sorted(self.nodes.values(), key=lambda n: n.timestamp, reverse=True)
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
在执行完这个计划后，`tests/helpers.py` 将被一个功能完备的实现所取代。下一步最关键的操作是：
1.  **运行完整的测试套件**: 执行 `pytest` 命令，确保所有测试都能通过。
2.  **检查失败的测试**: 特别关注 `tests/engine/test_engine_memory.py` 和 `tests/cli/test_view_model.py` 中的测试。如果它们之前因为 mock 功能不全而跳过或失败，现在应该能够正常通过。如果出现新的失败，则说明 `Engine` 或 `ViewModel` 的逻辑与新 mock 的行为不符，需要进行调试。
3.  **扩展测试**: 基于这个可靠的内存后端，为 `Engine` 和 `ViewModel` 补充更多的单元测试，覆盖之前无法测试的边界情况。
