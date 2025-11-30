import hashlib
import copy
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter

# --- Constants ---

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
        changes = [("A", f) for f in added]
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

    def create_node(self, node_type: str, input_tree: str, output_tree: str, content: str, **kwargs: Any) -> QuipuNode:
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
