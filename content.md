# fix-perf: 优化 Git 对象存储读取性能 (Lazy Loading)

## 用户需求
用户在使用 `qd ui` (Git 对象存储模式) 时，发现加载 150+ 历史节点耗时约 2.7s，显著慢于旧版文件系统模式 (1.0s)。这导致了明显的交互卡顿。

## 评论
经过分析，瓶颈在于**进程调用开销 (Process Overhead)**。
目前 `GitObjectHistoryReader.load_all_nodes` 对每个节点都会触发 3 次 `git cat-file` 调用 (Commit -> Tree -> Metadata & Content)。
150 个节点意味着 450+ 次子进程创建与销毁，这是极其昂贵的。
**优化方案**：`ui` 和 `log` 列表视图**不需要** `content.md` 的完整内容，只需要 `metadata.json` 中的 `summary`。我们可以推迟加载内容（Lazy Loading）。

## 目标
1.  在接口层 (`HistoryReader`) 引入 `get_node_content` 方法，支持按需加载。
2.  在 `GitObjectHistoryReader` 中实现**懒加载**：列表加载时不再读取 `content.md`，将 IO 调用次数减少 1/3 (并减小数据传输量)。
3.  保持 `FileSystemHistoryReader` 兼容性 (FS 模式读取极快，暂维持预加载，但实现接口)。

## 基本原理
通过减少 `subprocess.run` 的调用次数来降低系统开销。
Git 的设计哲学是“元数据与内容分离”。我们在 QDPS v1.0 中将 `metadata.json` 和 `content.md` 存为独立的 Blob，正是为了此刻——我们可以只读前者而不读后者。

## 标签
#comp/engine #concept/history #scope/core #perf

---

## Script

### Acts 1: 更新存储接口 (Add Lazy Load Interface)

首先在抽象基类中添加获取内容的接口定义。

~~~~~act
write_file packages/quipu-interfaces/src/quipu/core/storage.py
~~~~~

~~~~~python
from abc import ABC, abstractmethod
from typing import List, Any
from .models import QuipuNode


class HistoryReader(ABC):
    """
    一个抽象接口，用于从存储后端读取历史图谱。
    """

    @abstractmethod
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从存储中加载所有历史事件，构建完整的父子关系图，
        并返回所有节点的列表。
        注意：为了性能，实现可能会选择不立即加载节点的 content 内容。
        """
        pass

    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass


class HistoryWriter(ABC):
    """
    一个抽象接口，用于向历史存储后端写入一个新节点。
    """

    @abstractmethod
    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        """
        在存储后端创建并持久化一个新的历史节点。

        Args:
            node_type: 节点的类型，例如 'plan' 或 'capture'。
            input_tree: 输入状态树的哈希。
            output_tree: 输出状态树的哈希。
            content: 节点的主要内容 (例如，Markdown 格式的计划) 。
            **kwargs: 针对特定节点类型的附加元数据，
                      例如 'capture' 节点的 'message'。

        Returns:
            新创建的 QuipuNode 实例。
        """
        pass
~~~~~

### Acts 2: 适配文件系统存储 (Compat)

旧版文件系统读取速度极快（OS Page Cache），因此维持 Eager Loading (预加载) 策略，接口实现仅作简单的返回。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/file_system_storage.py
~~~~~

~~~~~python
import logging
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Any

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter
from .history import load_all_history_nodes

logger = logging.getLogger(__name__)


class FileSystemHistoryReader(HistoryReader):
    """
    一个从文件系统 (.quipu/history/*.md) 读取历史的实现。
    """
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def load_all_nodes(self) -> List[QuipuNode]:
        """
        通过调用现有的 `load_all_history_nodes` 函数来加载图谱。
        注意：FS 实现目前是预加载所有内容的。
        """
        return load_all_history_nodes(self.history_dir)

    def get_node_content(self, node: QuipuNode) -> str:
        """
        对于 FS 存储，内容通常在加载节点时已经读取到了 node.content 中。
        为了稳健性，如果内存中为空，尝试重新读取文件。
        """
        if node.content:
            return node.content
        
        # Fallback: 重新读取
        try:
            if node.filename and node.filename.exists():
                # 我们需要重新解析一下以去除 frontmatter，复用 helper 函数
                from .history import _parse_frontmatter
                full_text = node.filename.read_text(encoding="utf-8")
                _, body = _parse_frontmatter(full_text)
                node.content = body
                return body
        except Exception as e:
            logger.error(f"Failed to lazy load content from {node.filename}: {e}")
        
        return ""


class FileSystemHistoryWriter(HistoryWriter):
    """
    一个将历史节点写入文件系统 (.quipu/history/*.md) 的实现。
    """
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        """
        在 history 目录中创建一个新的 .md 文件来持久化节点。
        """
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_tree}_{output_tree}_{ts_str}.md"

        meta = {
            "type": node_type,
            "input_tree": input_tree,
            "output_tree": output_tree,
        }
        # 将 kwargs 中的额外元数据也合并进去
        meta.update(kwargs)

        # 确保 content 末尾有换行符，以分隔 frontmatter
        body = f"{content.strip()}\n"
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"

        try:
            filename.write_text(frontmatter + body, "utf-8")
            logger.debug(f"History node written to {filename}")
        except Exception as e:
            # 考虑在这里抛出一个自定义的 StorageWriteError
            logger.error(f"Failed to write history node to {filename}: {e}")
            raise

        return QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=timestamp,
            filename=filename,
            node_type=node_type,
            content=body,
        )
~~~~~

### Acts 3: 优化 Git 对象存储 (Implement Lazy Loading)

这是性能优化的核心。
1. `load_all_nodes` 中**不再读取** `content.md`。
2. 实现 `get_node_content`，利用 Git Plumbing 命令按需精确查找并读取 Blob。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~

~~~~~python
import json
import logging
import os
import platform
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import importlib.metadata

from quipu.core.git_db import GitDB
from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

logger = logging.getLogger(__name__)


class GitObjectHistoryReader(HistoryReader):
    """
    一个从 Git 底层对象读取历史的实现。
    """
    def __init__(self, git_db: GitDB):
        self.git_db = git_db

    def _parse_output_tree_from_body(self, body: str) -> Optional[str]:
        match = re.search(r"X-Quipu-Output-Tree:\s*([0-9a-f]{40})", body)
        return match.group(1) if match else None

    def load_all_nodes(self) -> List[QuipuNode]:
        """
        加载所有节点。为了性能，跳过 content.md 的读取 (Lazy Loading)。
        """
        all_heads = self.git_db.get_all_ref_heads("refs/quipu/")
        if not all_heads:
            return []

        log_entries = self.git_db.log_ref(all_heads)
        if not log_entries:
            return []

        temp_nodes: Dict[str, QuipuNode] = {}
        parent_map: Dict[str, str] = {}

        for entry in log_entries:
            commit_hash = entry["hash"]
            if commit_hash in temp_nodes:
                continue

            tree_hash = entry["tree"]
            
            try:
                # 1. Read tree content to find metadata
                tree_content = self.git_db.cat_file(tree_hash, "tree").decode('utf-8')
                blob_hashes = {}
                for line in tree_content.splitlines():
                    parts = line.split()
                    if len(parts) == 4:
                        # format: <mode> <type> <hash>\t<filename>
                        blob_hashes[parts[3]] = parts[2]
                
                if "metadata.json" not in blob_hashes:
                    logger.warning(f"Skipping commit {commit_hash[:7]}: metadata.json not found.")
                    continue
                
                # 2. Read metadata ONLY (Skip content.md for performance)
                meta_bytes = self.git_db.cat_file(blob_hashes["metadata.json"])
                meta_data = json.loads(meta_bytes)
                
                # Optimization: Content is lazy loaded via get_node_content
                content = "" 

                output_tree = self._parse_output_tree_from_body(entry["body"])
                if not output_tree:
                    logger.warning(f"Skipping commit {commit_hash[:7]}: X-Quipu-Output-Tree trailer not found.")
                    continue

                node = QuipuNode(
                    # Placeholder, will be filled in the linking phase
                    input_tree="", 
                    output_tree=output_tree,
                    timestamp=datetime.fromtimestamp(float(meta_data.get("exec", {}).get("start") or entry["timestamp"])),
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

        # Phase 2: Link nodes
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

    def get_node_content(self, node: QuipuNode) -> str:
        """
        从 Git Commit 中按需读取 content.md。
        node.filename 被 hack 为 ".quipu/git_objects/{commit_hash}"
        """
        if node.content:
            return node.content

        try:
            # Extract commit hash from the virtual filename
            commit_hash = node.filename.name
            
            # 1. Get Tree Hash from Commit
            commit_bytes = self.git_db.cat_file(commit_hash, "commit")
            # Parse "tree {hash}" from the first line
            tree_line = commit_bytes.split(b"\n", 1)[0].decode("utf-8")
            if not tree_line.startswith("tree "):
                raise ValueError("Invalid commit object format")
            tree_hash = tree_line.split()[1]

            # 2. Get content.md Blob Hash from Tree
            tree_content = self.git_db.cat_file(tree_hash, "tree").decode('utf-8')
            blob_hash = None
            for line in tree_content.splitlines():
                # format: <mode> <type> <hash>\t<filename>
                parts = line.split()
                if len(parts) == 4 and parts[3] == "content.md":
                    blob_hash = parts[2]
                    break
            
            if not blob_hash:
                return "" # No content found
            
            # 3. Read Blob
            content_bytes = self.git_db.cat_file(blob_hash)
            content = content_bytes.decode('utf-8', errors='ignore')
            
            # Cache it
            node.content = content
            return content

        except Exception as e:
            logger.error(f"Failed to lazy load content for node {node.short_hash}: {e}")
            return ""


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
        if node_type == "plan":
            # 优先从 act 块中提取摘要
            summary = ""
            in_act_block = False
            for line in content.strip().splitlines():
                clean_line = line.strip()
                if clean_line.startswith(('~~~act', '```act')):
                    in_act_block = True
                    continue
                
                if in_act_block:
                    if clean_line.startswith(('~~~', '```')):
                        break  # 块结束
                    if clean_line:
                        summary = clean_line
                        break  # 找到摘要
            
            if summary:
                return (summary[:75] + '...') if len(summary) > 75 else summary

            # 回退：尝试从 Markdown 的第一个标题中提取
            match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            
            # Fallback to the first non-empty line
            first_line = next((line.strip() for line in content.strip().splitlines() if line.strip()), "Plan executed")
            return (first_line[:75] + '...') if len(first_line) > 75 else first_line

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

        summary = self._generate_summary(
            node_type, content, input_tree, output_tree, **kwargs
        )

        metadata = {
            "meta_version": "1.0",
            "summary": summary,
            "type": node_type,
            "generator": self._get_generator_info(),
            "env": self._get_env_info(),
            "exec": {"start": start_time, "duration_ms": duration_ms},
        }

        meta_json_bytes = json.dumps(
            metadata, sort_keys=False, ensure_ascii=False
        ).encode("utf-8")
        content_md_bytes = content.encode("utf-8")

        meta_blob_hash = self.git_db.hash_object(meta_json_bytes)
        content_blob_hash = self.git_db.hash_object(content_md_bytes)

        # 使用 100444 权限 (只读文件)
        tree_descriptor = (
            f"100444 blob {meta_blob_hash}\tmetadata.json\n"
            f"100444 blob {content_blob_hash}\tcontent.md"
        )
        tree_hash = self.git_db.mktree(tree_descriptor)

        # 1. 确定父节点 (Topological Parent)
        parent_commit = self.git_db.get_commit_by_output_tree(input_tree)
        parents = [parent_commit] if parent_commit else None
        
        if not parent_commit and input_tree != "4b825dc642cb6eb9a060e54bf8d69288fbee4904":
             logger.warning(f"⚠️  Could not find parent commit for input state {input_tree[:7]}. This node may be detached.")

        # 2. 创建 Commit
        commit_message = f"{summary}\n\nX-Quipu-Output-Tree: {output_tree}"
        new_commit_hash = self.git_db.commit_tree(
            tree_hash=tree_hash, parent_hashes=parents, message=commit_message
        )

        # 3. 引用管理 (Multi-Head Strategy)
        self.git_db.update_ref("refs/quipu/history", new_commit_hash)
        self.git_db.update_ref(f"refs/quipu/heads/{new_commit_hash}", new_commit_hash)
        
        if parent_commit:
            self.git_db.delete_ref(f"refs/quipu/heads/{parent_commit}")

        logger.info(f"✅ History node created as commit {new_commit_hash[:7]}")

        # 返回一个 QuipuNode 实例，content 此时已在内存中，无需 Lazy Load
        return QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.fromtimestamp(start_time),
            filename=Path(f".quipu/git_objects/{new_commit_hash}"),
            node_type=node_type,
            content=content,
        )
~~~~~