import importlib.metadata
import json
import logging
import os
import platform
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pyquipu.engine.git_db import GitDB
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter

logger = logging.getLogger(__name__)


class GitObjectHistoryReader(HistoryReader):
    def __init__(self, git_db: GitDB):
        self.git_db = git_db

    def _parse_output_tree_from_body(self, body: str) -> Optional[str]:
        match = re.search(r"X-Quipu-Output-Tree:\s*([0-9a-f]{40})", body)
        return match.group(1) if match else None

    def _parse_tree_binary(self, data: bytes) -> Dict[str, str]:
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
        # Step 1: Get Commits
        ref_tuples = self.git_db.get_all_ref_heads("refs/quipu/")
        if not ref_tuples:
            return []

        all_heads = list(set(t[0] for t in ref_tuples))
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
        return len(self.load_all_nodes())

    def get_node_position(self, output_tree_hash: str) -> int:
        all_nodes = self.load_all_nodes()
        # load_all_nodes 内部已经按时间倒序排序了
        # 但为了保险，还是在这里再次确认排序逻辑
        all_nodes.sort(key=lambda n: n.timestamp, reverse=True)

        for i, node in enumerate(all_nodes):
            if node.output_tree == output_tree_hash:
                return i
        return -1

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        all_nodes = self.load_all_nodes()
        # load_all_nodes 通常按时间倒序返回
        return all_nodes[offset : offset + limit]

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
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
        return None

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        all_nodes = self.load_all_nodes()
        node_map = {n.output_tree: n for n in all_nodes}

        descendants = set()
        queue = []

        if start_output_tree_hash in node_map:
            queue.append(node_map[start_output_tree_hash])

        while queue:
            current_node = queue.pop(0)
            for child in current_node.children:
                c_hash = child.output_tree
                if c_hash not in descendants:
                    descendants.add(c_hash)
                    queue.append(child)

        return descendants

    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        try:
            # 1. Get Tree Hash from Commit
            commit_content = self.git_db.cat_file(commit_hash, "commit").decode("utf-8", "ignore")
            tree_line = commit_content.split("\n", 1)[0]
            if not tree_line.startswith("tree "):
                raise ValueError("Invalid commit object format")
            tree_hash = tree_line.split()[1]

            # 2. 解析 Tree 并批量获取所有 blobs
            # We need to map blob hashes back to filenames.
            tree_content_bytes = self.git_db.cat_file(tree_hash, "tree")
            entries = self._parse_tree_binary(tree_content_bytes)

            blob_hashes = list(entries.values())
            blob_contents = self.git_db.batch_cat_file(blob_hashes)

            # Reconstruct the {filename: content} map
            result = {}
            for filename, blob_hash in entries.items():
                if blob_hash in blob_contents:
                    result[filename] = blob_contents[blob_hash]
            return result

        except Exception as e:
            logger.error(f"Failed to load blobs for commit {commit_hash[:7]}: {e}")
            return {}

    def get_node_content(self, node: QuipuNode) -> str:
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
            content_bytes = self.git_db.cat_file(blob_hash, "blob")
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
    def __init__(self, git_db: GitDB):
        self.git_db = git_db

    def _get_generator_info(self) -> Dict[str, str]:
        return {
            "id": os.getenv("QUIPU_GENERATOR_ID", "manual"),
            "tool": os.getenv("QUIPU_TOOL", "pyquipu-cli"),
        }

    def _get_env_info(self) -> Dict[str, str]:
        try:
            quipu_version = importlib.metadata.version("pyquipu-engine")
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
        # 关键修复：建立强引用！将 output_tree 作为名为 'snapshot' 的子目录挂载。
        # 这确保了 Git 的 GC 不会回收工作区快照，且 sync 时能同步实际内容。
        tree_descriptor = (
            f"100444 blob {meta_blob_hash}\tmetadata.json\n"
            f"100444 blob {content_blob_hash}\tcontent.md\n"
            f"040000 tree {output_tree}\tsnapshot"
        )
        tree_hash = self.git_db.mktree(tree_descriptor)

        # 1. 确定父节点 (Topological Parent)
        # 优先使用 Engine 提供的确切父节点，仅在未提供时回退到 Tree 反查
        parent_commit = kwargs.get("parent_commit_hash")
        if not parent_commit:
            parent_commit = self.git_db.get_commit_by_output_tree(input_tree)

        parents = [parent_commit] if parent_commit else None

        if not parent_commit and input_tree != "4b825dc642cb6eb9a060e54bf8d69288fbee4904":
            logger.warning(
                f"⚠️  Could not find parent commit for input state {input_tree[:7]}. This node may be detached."
            )

        # 2. 创建 Commit
        commit_message = f"{summary}\n\nX-Quipu-Output-Tree: {output_tree}"
        new_commit_hash = self.git_db.commit_tree(tree_hash=tree_hash, parent_hashes=parents, message=commit_message)

        # 3. 引用管理 (QDPS v1.1 - Local Heads Namespace)
        # 在本地工作区命名空间中为新的 commit 创建一个持久化的 head 引用。
        # 这是 push 操作的唯一来源，并且支持多分支图谱，因此不再删除父节点的 head。
        self.git_db.update_ref(f"refs/quipu/local/heads/{new_commit_hash}", new_commit_hash)

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
