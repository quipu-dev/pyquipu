import json
import logging
import os
import platform
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import importlib.metadata

from quipu.core.git_db import GitDB
from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

logger = logging.getLogger(__name__)


class GitObjectHistoryReader(HistoryReader):
    """
    一个从 Git 底层对象读取历史的实现。
    使用批处理优化加载性能。
    """

    def __init__(self, git_db: GitDB):
        self.git_db = git_db

    def _parse_output_tree_from_body(self, body: str) -> Optional[str]:
        match = re.search(r"X-Quipu-Output-Tree:\s*([0-9a-f]{40})", body)
        return match.group(1) if match else None

    def _parse_tree_binary(self, data: bytes) -> Dict[str, str]:
        """
        解析 Git 原始二进制 Tree 对象。
        格式: [mode] [space] [path] [null] [20-byte-hash]
        返回: { filename: hex_hash }
        """
        entries = {}
        idx = 0
        length = len(data)
        while idx < length:
            # 1. Find space after mode
            space_idx = data.find(b" ", idx)
            if space_idx == -1:
                break

            # 2. Find null byte after filename
            null_idx = data.find(b"\0", space_idx + 1)
            if null_idx == -1:
                break

            # 3. Extract filename
            filename = data[space_idx + 1 : null_idx].decode("utf-8", errors="ignore")

            # 4. Extract hash (next 20 bytes)
            hash_start = null_idx + 1
            if hash_start + 20 > length:
                break

            hash_bytes = data[hash_start : hash_start + 20]
            hex_hash = hash_bytes.hex()

            entries[filename] = hex_hash

            # Move to next entry
            idx = hash_start + 20
        return entries

    def load_all_nodes(self) -> List[QuipuNode]:
        """
        加载所有节点。
        优化策略: Batch cat-file
        1. 获取所有 commits
        2. 批量读取所有 Trees
        3. 解析 Trees 找到 metadata.json Blob Hashes
        4. 批量读取所有 Metadata Blobs
        5. 组装 Nodes
        """
        # Step 1: Get Commits
        all_heads = self.git_db.get_all_ref_heads("refs/quipu/")
        if not all_heads:
            return []

        log_entries = self.git_db.log_ref(all_heads)
        if not log_entries:
            return []

        # Step 2: Batch fetch Trees
        tree_hashes = [entry["tree"] for entry in log_entries]
        trees_content = self.git_db.batch_cat_file(tree_hashes)

        # Step 3: Parse Trees to find Metadata Blob Hashes
        # Map tree_hash -> metadata_blob_hash
        tree_to_meta_blob = {}
        meta_blob_hashes = []

        for tree_hash, content_bytes in trees_content.items():
            try:
                # 使用二进制解析器
                entries = self._parse_tree_binary(content_bytes)
                if "metadata.json" in entries:
                    blob_hash = entries["metadata.json"]
                    tree_to_meta_blob[tree_hash] = blob_hash
                    meta_blob_hashes.append(blob_hash)
            except Exception as e:
                logger.warning(f"Error parsing tree {tree_hash}: {e}")

        # Step 4: Batch fetch Metadata Blobs
        metas_content = self.git_db.batch_cat_file(meta_blob_hashes)

        # Step 5: Assemble Nodes
        temp_nodes: Dict[str, QuipuNode] = {}
        parent_map: Dict[str, str] = {}

        for entry in log_entries:
            commit_hash = entry["hash"]
            tree_hash = entry["tree"]

            # Skip if already processed (though log entries shouldn't duplicate commits usually)
            if commit_hash in temp_nodes:
                continue

            try:
                # Retrieve metadata content
                if tree_hash not in tree_to_meta_blob:
                    logger.warning(f"Skipping commit {commit_hash[:7]}: metadata.json not found in tree.")
                    continue

                meta_blob_hash = tree_to_meta_blob[tree_hash]

                if meta_blob_hash not in metas_content:
                    logger.warning(f"Skipping commit {commit_hash[:7]}: metadata blob missing.")
                    continue

                meta_bytes = metas_content[meta_blob_hash]
                meta_data = json.loads(meta_bytes)

                output_tree = self._parse_output_tree_from_body(entry["body"])
                if not output_tree:
                    logger.warning(f"Skipping commit {commit_hash[:7]}: X-Quipu-Output-Tree trailer not found.")
                    continue

                # Content is lazy loaded
                content = ""

                node = QuipuNode(
                    commit_hash=commit_hash,
                    # Placeholder, will be filled in the linking phase
                    input_tree="",
                    output_tree=output_tree,
                    timestamp=datetime.fromtimestamp(
                        float(meta_data.get("exec", {}).get("start") or entry["timestamp"])
                    ),
                    filename=Path(f".quipu/git_objects/{commit_hash}"),
                    node_type=meta_data.get("type", "unknown"),
                    content=content,
                    summary=meta_data.get("summary", "No summary available"),
                )

                temp_nodes[commit_hash] = node
                parent_hash = entry["parent"].split(" ")[0] if entry["parent"] else None
                if parent_hash:
                    parent_map[commit_hash] = parent_hash

            except Exception as e:
                logger.error(f"Failed to load history node from commit {commit_hash[:7]}: {e}")

        # Phase 2: Link nodes (Same as before)
        for commit_hash, node in temp_nodes.items():
            parent_commit_hash = parent_map.get(commit_hash)
            if parent_commit_hash and parent_commit_hash in temp_nodes:
                parent_node = temp_nodes[parent_commit_hash]
                node.parent = parent_node
                parent_node.children.append(node)
                node.input_tree = parent_node.output_tree
            else:
                node.input_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # Sort children by timestamp
        for node in temp_nodes.values():
            node.children.sort(key=lambda n: n.timestamp)

        return list(temp_nodes.values())

    def get_node_count(self) -> int:
        """Git后端: 低效实现，加载所有节点后计数"""
        return len(self.load_all_nodes())

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """Git后端: 低效实现，加载所有节点后切片"""
        all_nodes = self.load_all_nodes()
        # load_all_nodes 通常按时间倒序返回
        return all_nodes[offset : offset + limit]

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """Git后端: 在内存中遍历图谱"""
        all_nodes = self.load_all_nodes()
        node_map = {n.output_tree: n for n in all_nodes}

        ancestors = set()
        queue = []

        if start_output_tree_hash in node_map:
            queue.append(node_map[start_output_tree_hash])

        while queue:
            current_node = queue.pop(0)
            if current_node.parent:
                p_hash = current_node.parent.output_tree
                if p_hash not in ancestors:
                    ancestors.add(p_hash)
                    queue.append(current_node.parent)

        return ancestors

    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """Git后端: 不支持私有数据"""
        return None

    def get_node_content(self, node: QuipuNode) -> str:
        """
        从 Git Commit 中按需读取 content.md。
        node.filename 被 hack 为 ".quipu/git_objects/{commit_hash}"
        """
        if node.content:
            return node.content

        try:
            commit_hash = node.commit_hash

            # 1. Get Tree Hash from Commit
            commit_bytes = self.git_db.cat_file(commit_hash, "commit")
            # Parse "tree {hash}" from the first line
            tree_line = commit_bytes.split(b"\n", 1)[0].decode("utf-8")
            if not tree_line.startswith("tree "):
                raise ValueError("Invalid commit object format")
            tree_hash = tree_line.split()[1]

            # 2. Get content.md Blob Hash from Tree
            # Use batch_cat_file to get RAW binary tree content, compatible with _parse_tree_binary
            tree_content_map = self.git_db.batch_cat_file([tree_hash])
            if tree_hash not in tree_content_map:
                return ""

            tree_content = tree_content_map[tree_hash]
            entries = self._parse_tree_binary(tree_content)

            blob_hash = entries.get("content.md")

            if not blob_hash:
                return ""  # No content found

            # 3. Read Blob (also raw binary)
            content_bytes = self.git_db.cat_file(blob_hash)
            content = content_bytes.decode("utf-8", errors="ignore")

            # Cache it
            node.content = content
            return content

        except Exception as e:
            logger.error(f"Failed to lazy load content for node {node.short_hash}: {e}")
            return ""

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        """
        GitObject 后端的查找实现。
        由于没有索引，此实现加载所有节点并在内存中进行过滤。
        """
        # 这是一个高成本操作，因为它需要加载整个图
        candidates = self.load_all_nodes()

        if summary_regex:
            try:
                pattern = re.compile(summary_regex, re.IGNORECASE)
                candidates = [node for node in candidates if pattern.search(node.summary)]
            except re.error as e:
                logger.error(f"无效的正则表达式: {summary_regex} ({e})")
                return []

        if node_type:
            candidates = [node for node in candidates if node.node_type == node_type]

        # 按时间戳降序排序
        candidates.sort(key=lambda n: n.timestamp, reverse=True)

        return candidates[:limit]


class GitObjectHistoryWriter(HistoryWriter):
    """
    一个将历史节点作为 Git 底层对象写入存储的实现。
    遵循 Quipu 数据持久化协议规范 (QDPS) v1.0。
    """

    def __init__(self, git_db: GitDB):
        self.git_db = git_db

    def _get_generator_info(self) -> Dict[str, str]:
        """根据 QDPS v1.0 规范，通过环境变量获取生成源信息。"""
        return {
            "id": os.getenv("QUIPU_GENERATOR_ID", "manual"),
            "tool": os.getenv("QUIPU_TOOL", "quipu-cli"),
        }

    def _get_env_info(self) -> Dict[str, str]:
        """获取运行时环境指纹。"""
        try:
            quipu_version = importlib.metadata.version("quipu-engine")
        except importlib.metadata.PackageNotFoundError:
            quipu_version = "unknown"

        return {
            "quipu": quipu_version,
            "python": platform.python_version(),
            "os": platform.system().lower(),
        }

    def _generate_summary(
        self,
        node_type: str,
        content: str,
        input_tree: str,
        output_tree: str,
        **kwargs: Any,
    ) -> str:
        """根据节点类型生成单行摘要。"""
        # 1. 如果传入了显式的摘要，直接使用
        if kwargs.get("summary_override"):
            return kwargs["summary_override"]

        if node_type == "plan":
            # Controller 优先负责生成摘要。此处的逻辑仅作为当 controller 未提供摘要时的回退。
            # 优先级 1: 尝试从 Markdown 的第一个标题中提取
            match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
            if match:
                return match.group(1).strip()

            # 最终回退: 使用内容的第一行
            first_line = next((line.strip() for line in content.strip().splitlines() if line.strip()), "Plan executed")
            return (first_line[:75] + "...") if len(first_line) > 75 else first_line

        elif node_type == "capture":
            user_message = (kwargs.get("message") or "").strip()

            changes = self.git_db.get_diff_name_status(input_tree, output_tree)
            if not changes:
                auto_summary = "Capture: No changes detected"
            else:
                formatted_changes = [f"{status} {Path(path).name}" for status, path in changes[:3]]
                summary_part = ", ".join(formatted_changes)
                if len(changes) > 3:
                    summary_part += f" ... and {len(changes) - 3} more files"
                auto_summary = f"Capture: {summary_part}"

            return f"{user_message} {auto_summary}".strip() if user_message else auto_summary

        return "Unknown node type"

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        """
        在 Git 对象数据库中创建并持久化一个新的历史节点。
        """
        start_time = kwargs.get("start_time", time.time())
        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)

        summary = self._generate_summary(node_type, content, input_tree, output_tree, **kwargs)

        metadata = {
            "meta_version": "1.0",
            "summary": summary,
            "type": node_type,
            "generator": self._get_generator_info(),
            "env": self._get_env_info(),
            "exec": {"start": start_time, "duration_ms": duration_ms},
        }

        meta_json_bytes = json.dumps(metadata, sort_keys=False, ensure_ascii=False).encode("utf-8")
        content_md_bytes = content.encode("utf-8")

        meta_blob_hash = self.git_db.hash_object(meta_json_bytes)
        content_blob_hash = self.git_db.hash_object(content_md_bytes)

        # 使用 100444 权限 (只读文件)
        tree_descriptor = f"100444 blob {meta_blob_hash}\tmetadata.json\n100444 blob {content_blob_hash}\tcontent.md"
        tree_hash = self.git_db.mktree(tree_descriptor)

        # 1. 确定父节点 (Topological Parent)
        parent_commit = self.git_db.get_commit_by_output_tree(input_tree)
        parents = [parent_commit] if parent_commit else None

        if not parent_commit and input_tree != "4b825dc642cb6eb9a060e54bf8d69288fbee4904":
            logger.warning(
                f"⚠️  Could not find parent commit for input state {input_tree[:7]}. This node may be detached."
            )

        # 2. 创建 Commit
        commit_message = f"{summary}\n\nX-Quipu-Output-Tree: {output_tree}"
        new_commit_hash = self.git_db.commit_tree(tree_hash=tree_hash, parent_hashes=parents, message=commit_message)

        # 3. 引用管理 (Multi-Head Strategy)
        self.git_db.update_ref("refs/quipu/history", new_commit_hash)
        self.git_db.update_ref(f"refs/quipu/heads/{new_commit_hash}", new_commit_hash)

        if parent_commit:
            self.git_db.delete_ref(f"refs/quipu/heads/{parent_commit}")

        logger.info(f"✅ History node created as commit {new_commit_hash[:7]}")

        # 返回一个 QuipuNode 实例，content 此时已在内存中，无需 Lazy Load
        node = QuipuNode(
            commit_hash=new_commit_hash,
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.fromtimestamp(start_time),
            filename=Path(f".quipu/git_objects/{new_commit_hash}"),
            node_type=node_type,
            content=content,
            summary=summary,  # Populate summary for immediate use
        )

        # 关键修改：显式填充 parent 信息，以便上层 Writer (如 SQLite) 可以直接获取确切的父节点 Hash
        # 而无需通过容易出错的 Tree 反查。我们使用一个最小化的占位节点。
        if parent_commit:
            node.parent = QuipuNode(
                commit_hash=parent_commit,
                input_tree="",  # Placeholder
                output_tree=input_tree,  # Use parent's output_tree which is our input_tree
                timestamp=datetime.fromtimestamp(0),  # Placeholder, not critical here
                filename=Path(f".quipu/git_objects/{parent_commit}"),
                node_type="unknown",
                content="",
                summary="",  # Placeholder
            )

        return node
