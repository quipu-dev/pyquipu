这是一个由多个相互关联的缺陷导致的连锁失败：

1.  **`AttributeError: 'InMemoryDB' object has no attribute 'get_diff_stat'`**:
    *   **原因**: 我的模拟完全搞错了方法名。`Engine` 在生成 `capture` 节点摘要时，调用的方法是 `get_diff_stat`，而不是我实现的 `get_diff_name_status`。这是一个直接的接口不匹配。

2.  **`AssertionError: assert None == QuipuNode(...)`**:
    *   **原因**: 这是由我的 `InMemoryHistoryManager` 和 `InMemoryDB` 之间**错误的职责划分和状态管理**导致的。
    *   **缺陷**: 我的 `InMemoryHistoryManager.create_node` 只是创建了一个孤立的 `QuipuNode` 对象并将其存储在自己的 `self.nodes` 列表中。当 `Engine` 调用它创建 `node_a`，然后又调用它创建 `node_b` 时，`InMemoryHistoryManager` 没有任何机制去查找 `node_a` 并将其链接为 `node_b` 的父节点。
    *   **正确的设计 (如您提供的参考代码所示)**:
        *   `InMemoryDB` 应该是状态的**唯一真实来源**，它不仅存储文件快照，还应该存储已创建的 `QuipuNode` 对象（例如，通过 `output_tree` 索引）。
        *   `InMemoryHistoryManager.create_node` 在创建新节点时，必须**立即**使用 `input_tree` 哈希去 `InMemoryDB` 中查询父节点，并完成链接。
    *   我的实现完全颠覆了这种逻辑，导致父子关系从未建立，`node_b.parent` 自然是 `None`。

我之前的所有修复都只是在表面打补丁，而没有重构这个核心的、错误的设计。唯一的解决方案是彻底废弃我之前的所有 `InMemory` 实现，并根据您提供的参考代码和对 `Engine` 行为的正确理解，**从头开始编写一个行为正确的模拟后端**。

## [WIP] fix: 重写内存测试后端以正确模拟状态和行为

### 用户需求
彻底修复 `test_engine_memory.py` 的所有失败，通过重写 `tests/helpers.py` 中的内存模拟后端，使其在接口、状态管理和行为上都与真实系统保持一致。

### 评论
这次失败是一次深刻的教训，它表明模拟一个复杂的系统不仅要匹配其静态的接口，更要精确地模拟其动态的行为和状态流。这次重构将产生一个真正可靠的内存测试环境，为 `Engine` 的单元测试提供坚实的保障。

### 目标
1.  重写 `tests/helpers.py` 中的 `InMemoryDB` 和 `InMemoryHistoryManager`。
2.  在 `InMemoryDB` 中实现正确的 `get_diff_stat` 方法。
3.  在 `InMemoryHistoryManager` 的 `create_node` 方法中实现即时的父子节点链接逻辑。
4.  确保 `test_engine_memory.py` 中的所有测试用例都能一次性全部通过。

### 基本原理
我们将编写一个全新的、正确的 `InMemory` 后端。`InMemoryDB` 将作为所有状态（文件快照和节点对象）的中央存储。`InMemoryHistoryManager` 将作为一个无状态的协调器，在创建节点时，利用 `InMemoryDB` 来查询父节点并建立链接，从而精确模拟 `Engine` 的工作流。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/test-helpers #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 全面重写 `tests/helpers.py`

我将用一个全新的、正确的实现来替换整个文件。

~~~~~act
write_file tests/helpers.py
~~~~~
~~~~~python
import hashlib
import copy
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from quipu.engine.state_machine import Engine
from quipu.interfaces.models import QuipuNode
from quipu.interfaces.storage import HistoryReader, HistoryWriter

# --- Constants ---

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
    """A simple in-memory virtual file system."""

    def __init__(self):
        self.files: Dict[str, str] = {}

    def write(self, path: str, content: str):
        self.files[path] = content

    def read(self, path: str) -> Optional[str]:
        return self.files.get(path)

    def copy(self):
        new_vfs = VirtualFileSystem()
        new_vfs.files = self.files.copy()
        return new_vfs


class InMemoryDB:
    """A mock of GitDB that correctly manages state for engine tests."""

    def __init__(self):
        self.vfs = VirtualFileSystem()
        self.snapshots: Dict[str, VirtualFileSystem] = {EMPTY_TREE_HASH: VirtualFileSystem()}
        self.nodes: Dict[str, QuipuNode] = {}  # output_tree -> Node

    def get_tree_hash(self) -> str:
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
        self.vfs = self.snapshots.get(tree_hash, VirtualFileSystem()).copy()

    def get_diff_name_status(self, old_tree: str, new_tree: str) -> List[Tuple[str, str]]:
        old_vfs = self.snapshots.get(old_tree, VirtualFileSystem()).files
        new_vfs = self.snapshots.get(new_tree, VirtualFileSystem()).files
        old_files, new_files = set(old_vfs.keys()), set(new_vfs.keys())
        added, deleted = new_files - old_files, old_files - new_files
        common = old_files & new_files
        changes = [( "A", f) for f in added]
        changes.extend(("D", f) for f in deleted)
        changes.extend(("M", f) for f in common if old_vfs[f] != new_vfs[f])
        return sorted(changes)

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        # Correctly implement the missing method
        changes = self.get_diff_name_status(old_tree, new_tree)
        return "\n".join(f"{status}\t{path}" for status, path in changes)


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
    """A history manager that correctly simulates engine behavior."""

    def __init__(self, db: InMemoryDB):
        self.db = db

    def create_node(
        self, node_type: str, input_tree: str, output_tree: str, content: str, **kwargs: Any
    ) -> QuipuNode:
        fake_commit_hash = hashlib.sha1(f"{output_tree}{datetime.now().timestamp()}".encode()).hexdigest()
        node = QuipuNode(
            commit_hash=fake_commit_hash,
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.now(),
            filename=Path(f"memory://{output_tree}"),
            node_type=node_type,
            content=content,
            summary=kwargs.get("summary_override", f"Summary for {output_tree[:7]}"),
        )
        # Correctly link parent AT CREATION TIME
        if input_tree in self.db.nodes:
            parent_node = self.db.nodes[input_tree]
            node.parent = parent_node
            parent_node.children.append(node)
        # Store node in the central DB, indexed by output_tree
        self.db.nodes[output_tree] = node
        return node

    def load_all_nodes(self) -> List[QuipuNode]:
        return sorted(list(self.db.nodes.values()), key=lambda n: n.timestamp)

    # --- Methods to satisfy abstract base classes ---
    def get_node_count(self) -> int:
        return len(self.db.nodes)

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        all_nodes = self.load_all_nodes()
        return all_nodes[offset : offset + limit]

    def find_nodes(self, **kwargs) -> List[QuipuNode]:
        return []

    def get_node_content(self, node: QuipuNode) -> str:
        return node.content

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        return set()

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        return set()

    def get_node_position(self, output_tree_hash: str) -> int:
        return -1

    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        return None

    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        return {}
~~~~~

### 下一步建议
这次修复是全面且根本性的。请再次运行测试。我相信这次能够彻底解决所有问题，使测试套件完全恢复正常。
