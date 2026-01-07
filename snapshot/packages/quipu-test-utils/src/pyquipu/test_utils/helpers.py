import hashlib
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pyquipu.cli.main import app
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter
from typer.testing import CliRunner

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


# --- CLI/Integration Test Helpers ---


def run_git_command(cwd: Path, args: list[str], check: bool = True) -> str:
    """Helper to run a git command and return stdout."""
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def get_local_quipu_heads(work_dir: Path) -> set[str]:
    """Helper to get a set of all local quipu head commit hashes."""
    refs_output = run_git_command(
        work_dir, ["for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads"], check=False
    )
    if not refs_output:
        return set()
    return set(refs_output.splitlines())


def create_node_via_cli(runner: CliRunner, work_dir: Path, content: str) -> str:
    """Helper to create a node via the CLI runner and return its commit hash."""
    heads_before = get_local_quipu_heads(work_dir)

    # [FIX] Add an explicit title to the plan to ensure predictable node summary.
    plan_title = f"Plan for {content}"
    plan_file = work_dir / f"{content}.md"
    plan_file.write_text(f"# {plan_title}\n\n~~~~~act\necho '{content}'\n~~~~~")

    result = runner.invoke(app, ["run", str(plan_file), "--work-dir", str(work_dir), "-y"])
    assert result.exit_code == 0

    heads_after = get_local_quipu_heads(work_dir)
    new_heads = heads_after - heads_before

    if not new_heads:
        raise AssertionError("No new Quipu nodes created.")

    # If only 1 node created, return it.
    if len(new_heads) == 1:
        return new_heads.pop()

    # If 2 nodes created (Capture + Plan), identify the Plan node by checking if
    # the explicit title is present in the commit message.
    for head in new_heads:
        msg = run_git_command(work_dir, ["log", "-1", "--format=%B", head])
        if plan_title in msg:
            return head

    raise AssertionError(f"Could not identify Plan node among {len(new_heads)} new heads: {new_heads}")


# --- Engine/Component Test Helpers ---


def create_branching_history(engine: Engine) -> Engine:
    """
    Creates a common branching history for testing.
    History:
    - n0 (root) -> n1 -> n2 (branch point) -> n3a (branch A) -> n4 (summary)
                                          \\-> n3b (branch B)
    """
    ws = engine.root_dir
    (ws / "file.txt").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, h0, "plan 0", summary_override="Root Node")
    (ws / "file.txt").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h0, h1, "plan 1", summary_override="Linear Node 1")
    (ws / "file.txt").write_text("v2")
    h2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2, "plan 2", summary_override="Branch Point")
    engine.visit(h2)
    (ws / "branch_a.txt").touch()
    h3a = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3a, "plan 3a", summary_override="Branch A change")
    engine.visit(h3a)
    engine.create_plan_node(h3a, h3a, "plan 4", summary_override="Summary Node")
    engine.visit(h2)
    (ws / "branch_b.txt").touch()
    h3b = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2, h3b, "plan 3b", summary_override="Branch B change")
    return engine


def create_complex_link_history(engine: Engine) -> Engine:
    """
    Creates a complex history to ensure a specific node has all navigation link types.
    Node n3 will have: a parent (n2b), a child (n4), an ancestor branch point (n1),
    and an ancestor summary node (n_summary).
    """
    ws = engine.root_dir
    engine.create_plan_node(EMPTY_TREE_HASH, EMPTY_TREE_HASH, "plan sum", summary_override="Ancestor_Summary")
    (ws / "f").write_text("v0")
    h0 = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, h0, "plan 0", summary_override="Root")
    (ws / "f").write_text("v1")
    h1 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h0, h1, "plan 1", summary_override="Branch_Point")
    engine.visit(h1)
    (ws / "a").touch()
    h2a = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2a, "plan 2a", summary_override="Branch_A")
    engine.visit(h1)
    (ws / "b").touch()
    h2b = engine.git_db.get_tree_hash()
    engine.create_plan_node(h1, h2b, "plan 2b", summary_override="Parent_Node")
    engine.visit(h2b)
    (ws / "c").touch()
    h3 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h2b, h3, "plan 3", summary_override="Test_Target_Node")
    engine.visit(h3)
    (ws / "d").touch()
    h4 = engine.git_db.get_tree_hash()
    engine.create_plan_node(h3, h4, "plan 4", summary_override="Child_Node")
    return engine


def create_linear_history(engine: Engine) -> Tuple[Engine, Dict[str, str]]:
    """
    Creates a simple linear history A -> B.
    - State A: a.txt
    - State B: b.txt (a.txt is removed)
    Returns the engine and a dictionary mapping state names ('a', 'b') to their output tree hashes.
    """
    ws = engine.root_dir

    # State A
    (ws / "a.txt").write_text("A")
    hash_a = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, hash_a, "Plan A", summary_override="State A")

    # State B
    (ws / "b.txt").write_text("B")
    (ws / "a.txt").unlink()
    hash_b = engine.git_db.get_tree_hash()
    engine.create_plan_node(hash_a, hash_b, "Plan B", summary_override="State B")

    hashes = {"a": hash_a, "b": hash_b}
    return engine, hashes


def create_dirty_workspace_history(engine: Engine) -> Tuple[Engine, str]:
    """
    Creates a history A -> B, then makes the workspace dirty.
    - State A: file.txt -> "v1"
    - State B (HEAD): file.txt -> "v2"
    - Dirty State: file.txt -> "v3"
    Returns the engine and the hash of state A for checkout tests.
    """
    work_dir = engine.root_dir
    file_path = work_dir / "file.txt"

    # State A
    file_path.write_text("v1")
    hash_a = engine.git_db.get_tree_hash()
    engine.capture_drift(hash_a, message="State A")

    # State B (HEAD)
    file_path.write_text("v2")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="State B")

    # Dirty State
    file_path.write_text("v3")

    return engine, hash_a


def create_linear_history_from_specs(engine: Engine, specs: List[Dict[str, Any]]):
    """
    Creates a linear history based on a list of specifications.
    Each spec is a dict: {'type': 'plan'|'capture', 'summary': str, 'content': Optional[str]}
    """
    parent_hash = EMPTY_TREE_HASH
    if engine.history_graph:
        # If history is not empty, start from the latest node
        latest_node = sorted(engine.history_graph.values(), key=lambda n: n.timestamp)[-1]
        parent_hash = latest_node.output_tree

    for i, spec in enumerate(specs):
        # Create a unique file change for each node to ensure a new tree hash
        (engine.root_dir / f"file_{time.time()}_{i}.txt").touch()
        new_hash = engine.git_db.get_tree_hash()

        if spec["type"] == "plan":
            engine.create_plan_node(
                input_tree=parent_hash,
                output_tree=new_hash,
                plan_content=spec.get("content", ""),
                summary_override=spec["summary"],
            )
        elif spec["type"] == "capture":
            engine.capture_drift(new_hash, message=spec["summary"])

        parent_hash = new_hash
    # Re-align to ensure the engine's internal graph is fully updated
    engine.align()


def create_query_branching_history(engine: Engine) -> Tuple[Engine, str]:
    """
    Creates a specific branching history for query reachability tests.
    History: root -> A -> B (HEAD)
                   \\-> C (unreachable)
    Returns the engine and the hash of state B (the HEAD).
    """
    ws = engine.root_dir
    # root -> A
    (ws / "f_a").touch()
    h_a = engine.git_db.get_tree_hash()
    node_a = engine.capture_drift(h_a, "Node A")

    # A -> B (This will become the main branch)
    (ws / "f_b").touch()
    h_b = engine.git_db.get_tree_hash()
    engine.capture_drift(h_b, "Node B")

    # Go back to A to create the branch
    engine.visit(node_a.output_tree)

    # A -> C
    (ws / "f_c").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), "Node C")

    # Checkout back to B to set it as the current HEAD for the test
    engine.visit(h_b)
    engine.align()
    return engine, h_b
