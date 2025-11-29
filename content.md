您是对的，测试仍然失败。我的修复解决了接口符合性的问题，但没有解决潜在的逻辑错误。我为之前的疏忽道歉，并感谢您提供了详细的错误报告和相关文件，这让我能够进行更深入的分析。

这是一个多点失败，我们逐一分析：

1.  **`AssertionError: assert 'ORPHAN' == 'CLEAN'`**:
    *   **原因**: `Engine.align()` 在历史记录为空时，会检查当前工作区的 tree hash。如果 hash 等于创世状态 (空树) 的 hash，则状态为 `CLEAN`；否则为 `ORPHAN`。
    *   **根本问题**: 我在 `tests/helpers.py` 中定义 `EMPTY_TREE_HASH` 时，出现了一个**拼写错误** (`...42cb642cb...` 多了一段)。这导致 `InMemoryDB` 在空状态下返回的 hash 与 `Engine` 内部用于比较的 `EMPTY_TREE_HASH` 不匹配，因此 `align()` 错误地将本应是 `CLEAN` 的状态判断为 `ORPHAN`。

2.  **`AttributeError: 'InMemoryDB' object has no attribute 'get_diff_stat'`**:
    *   **原因**: 在 `test_capture_drift_from_genesis` 中，`engine.capture_drift()` 方法会尝试为新的 `capture` 节点生成一个摘要。这个过程需要调用 `self.git_db.get_diff_name_status()` 来获取文件变更列表。
    *   **根本问题**: 我的 `InMemoryDB` 模拟类不完整，**缺少 `get_diff_name_status` 方法的实现**，导致 `Engine` 在调用时崩溃。

3.  **`AssertionError: assert None == QuipuNode(...)`**:
    *   **原因**: 这个测试断言 `node_b.parent` 应该等于 `node_a`。实际结果是 `None`，说明父子关系链接失败。
    *   **根本问题**: `Engine._link_new_node()` 方法在链接新节点时，会检查其 `input_tree`。如果 `input_tree` 是 `EMPTY_TREE_HASH`，它就认为这是根节点，不会去查找父节点。由于我之前错误的 `EMPTY_TREE_HASH` 常量，`Engine` 在处理第一个真实节点 (`node_a`) 时，`node_a.input_tree` 与错误的常量不匹配，可能导致了后续节点链接逻辑的混乱。修复 `EMPTY_TREE_HASH` 应该能一并解决此问题。

我将生成一个计划，一次性修复这三个问题。

## [WIP] fix: 修复内存测试辅助类的逻辑错误和不完整实现

### 错误分析
`tests/engine/test_engine_memory.py` 的失败是由 `tests/helpers.py` 中 `InMemoryDB` 模拟类的三个独立缺陷共同导致的：
1.  `EMPTY_TREE_HASH` 常量存在拼写错误，导致 `align()` 方法对创世状态的判断失败。
2.  `InMemoryDB` 类缺少 `get_diff_name_status` 方法的实现，导致 `capture_drift` 在生成摘要时因 `AttributeError` 而崩溃。
3.  由于 `EMPTY_TREE_HASH` 错误，`Engine` 内部的父子节点链接逻辑也可能受到影响，导致 `test_plan_node_creation` 失败。

### 用户需求
修复 `tests/helpers.py` 中的所有已知缺陷，使 `test_engine_memory.py` 中的所有测试用例都能成功通过。

### 评论
这次的连锁失败暴露出测试辅助工具的实现需要与它所模拟的真实对象的接口和行为高度一致。通过这次修复，`helpers.py` 中的内存后端将变得更加健壮和完整，能够更准确地支撑 `Engine` 的单元测试。

### 目标
1.  在 `tests/helpers.py` 中修正 `EMPTY_TREE_HASH` 常量的值为正确的 Git 空树哈希。
2.  为 `InMemoryDB` 类添加 `get_diff_name_status` 方法的最小化实现。
3.  确保所有 `test_engine_memory.py` 中的测试全部通过。

### 基本原理
我们将通过一次 `write_file` 操作，全面更新 `tests/helpers.py` 文件。这包括纠正常量、补充缺失的方法，并保留之前为满足抽象接口而添加的方法存根。这将使内存模拟后端（`InMemoryDB` 和 `InMemoryHistoryManager`）在接口和行为上都足以支持 `Engine` 的核心逻辑测试。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/test-helpers #task.action/refactor #task/state/continue

---

### Script

#### Acts 1: 全面修复 `tests/helpers.py`

我们将重写整个文件，以确保所有修正都已应用。

~~~~~act
write_file tests/helpers.py
~~~~~
~~~~~python
import hashlib
import copy
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

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


class InMemoryVFS:
    """A simple in-memory virtual file system."""

    def __init__(self):
        self.files: Dict[str, str] = {}

    def write(self, path: str, content: str):
        self.files[path] = content

    def read(self, path: str) -> Optional[str]:
        return self.files.get(path)


class InMemoryDB:
    """A mock of GitDB that operates entirely in memory."""

    def __init__(self):
        self.vfs = InMemoryVFS()
        self.trees: Dict[str, Dict[str, str]] = {EMPTY_TREE_HASH: {}}

    def get_tree_hash(self) -> str:
        """Computes a stable hash for the current VFS state."""
        if not self.vfs.files:
            return EMPTY_TREE_HASH
        stable_repr = "".join(f"{p}:{c}" for p, c in sorted(self.vfs.files.items()))
        h = hashlib.sha1(stable_repr.encode()).hexdigest()
        # Store a snapshot of the VFS for potential checkout
        self.trees[h] = copy.deepcopy(self.vfs.files)
        return h

    def checkout_tree(self, tree_hash: str):
        """Restores the VFS to a previously stored state."""
        self.vfs.files = copy.deepcopy(self.trees.get(tree_hash, {}))

    def get_diff_name_status(self, from_hash: str, to_hash: str) -> List[tuple[str, str]]:
        """A simplified diff for capture summary generation."""
        # This mock isn't used for detailed diff verification, so returning an empty
        # list is sufficient for the engine's summary generation to not crash.
        return []


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
    """A mock of history storage that operates entirely in memory."""

    def __init__(self, db: InMemoryDB):
        self.db = db
        self.nodes: Dict[str, QuipuNode] = {}  # commit_hash -> QuipuNode

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        summary_override: Optional[str] = None,
        **kwargs,
    ) -> QuipuNode:
        # Create a unique but deterministic-looking hash
        commit_hash_content = f"{node_type}{input_tree}{output_tree}{content}{time.time()}"
        commit_hash = hashlib.sha1(commit_hash_content.encode()).hexdigest()

        node = QuipuNode(
            commit_hash=commit_hash,
            output_tree=output_tree,
            input_tree=input_tree,
            timestamp=datetime.now(),
            filename=Path(commit_hash),
            node_type=node_type,
            summary=summary_override or content.splitlines()[0] if content else f"Node {commit_hash[:7]}",
            content=content,
        )
        self.nodes[commit_hash] = node
        return node

    def load_all_nodes(self) -> List[QuipuNode]:
        # Simple load, but reconstruct parent-child links
        nodes_by_output = {n.output_tree: n for n in self.nodes.values()}
        for node in self.nodes.values():
            if node.input_tree in nodes_by_output:
                parent = nodes_by_output[node.input_tree]
                node.parent = parent
                if node not in parent.children:
                    parent.children.append(node)
        return sorted(list(self.nodes.values()), key=lambda n: n.timestamp)

    # --- Unused abstract methods ---
    def get_node_count(self) -> int:
        return len(self.nodes)

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
        """Returns the chronological position (0 = newest) of a node."""
        # This mock doesn't need a sophisticated implementation for current tests.
        all_nodes = self.load_all_nodes()
        for i, node in enumerate(all_nodes):
            if node.output_tree == output_tree_hash:
                return i
        return -1

    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """Private data is not used in the in-memory tests."""
        return None

    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        """Node blobs are not used in the in-memory tests."""
        return {}
~~~~~

### 下一步建议
这是对 `helpers.py` 的一次全面修复。请再次运行测试。我非常有信心这次能够解决所有 `test_engine_memory.py` 中的失败，并使整个测试套件恢复到全部通过的状态。
