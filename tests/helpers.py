import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter

# --- Constants ---

# The correct hash for an empty git tree.
EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# --- Git-based Test Helpers ---


def create_plan_node_with_change(engine: Engine, parent_hash: str, file_name: str, content: str, message: str) -> str:
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

    def checkout_tree(self, new_tree_hash: str, old_tree_hash: Optional[str] = None):
        # InMemoryDB 总是执行“瞬间切换”，不需要模拟 diff 优化逻辑
        tree_hash = new_tree_hash
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
