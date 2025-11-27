import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

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

    def get_node_count(self) -> int:
        return len(self.db.nodes)

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        all_nodes = sorted(self.db.nodes.values(), key=lambda n: n.timestamp, reverse=True)
        return all_nodes[offset : offset + limit]

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        符合新接口的内存实现。
        从指定的 output_tree 哈希开始，向上遍历父节点，收集所有祖先的 output_tree 哈希。
        """
        ancestors = set()
        # 内存数据库使用 output_tree 作为节点的键
        if start_output_tree_hash in self.db.nodes:
            curr = self.db.nodes[start_output_tree_hash]
            while curr.parent:
                ancestors.add(curr.parent.output_tree)
                # 向上移动到父节点
                if curr.parent.output_tree in self.db.nodes:
                    curr = self.db.nodes[curr.parent.output_tree]
                else:
                    # 如果父节点由于某种原因不在图中（在内存测试中不应该发生），则停止
                    break
        return ancestors

    def get_private_data(self, commit_hash: str) -> Optional[str]:
        return None

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
        # Generate a fake commit hash for memory backend
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

        # Link parent
        if input_tree in self.db.nodes:
            parent_node = self.db.nodes[input_tree]
            node.parent = parent_node
            parent_node.children.append(node)

        self.db.nodes[output_tree] = node
        return node

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        """
        内存后端的节点查找实现，通过在内存中过滤所有节点来工作。
        """
        candidates = self.load_all_nodes()

        if summary_regex:
            try:
                pattern = re.compile(summary_regex, re.IGNORECASE)
                candidates = [node for node in candidates if pattern.search(node.summary)]
            except re.error:
                return []  # 在测试中，无效的正则表达式直接返回空列表

        if node_type:
            candidates = [node for node in candidates if node.node_type == node_type]

        # 按时间戳降序排序
        candidates.sort(key=lambda n: n.timestamp, reverse=True)

        return candidates[:limit]
