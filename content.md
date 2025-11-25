# refactor: 实现 Git 对象历史写入器

## 用户需求
根据 [Quipu 储存架构最终规范](Quipu%20储存架构最终规范.md) 和 [实施计划](Quipu%20储存架构改造实施计划%20(TODO).md) ，实现 `QDPS v1.0` 规范中定义的、基于 Git 底层命令的全新历史记录存储机制。具体任务是实现 `GitObjectHistoryWriter`。

## 评论
这是存储层改造的核心步骤。通过将历史记录的写入逻辑封装到一个遵循 `QDPS v1.0` 规范的新类中，我们为彻底替换旧的文件系统存储方式奠定了基础。这使得系统的历史记录功能将具备版本控制、高效存储和协作同步的能力。

## 目标
1.  在 `quipu.core.git_db` 模块中增加一个辅助方法，用于获取两个 Git Tree 之间的文件状态变更列表。
2.  创建一个新的模块 `quipu.core.git_object_storage`。
3.  在该新模块中，实现 `GitObjectHistoryWriter` 类，该类遵循 `HistoryWriter` 接口，并能将历史节点作为 Git 对象（Blobs, Tree, Commit）写入仓库。

## 基本原理
我们遵循“策略模式”和“依赖注入”的设计原则。`GitObjectHistoryWriter` 将作为一个具体的“写入策略”实现，它封装了所有与 Git 底层对象交互的复杂逻辑。`Engine` 模块未来将通过依赖注入的方式使用这个写入器，而无需关心其内部实现细节。这种解耦使得 `Engine` 的核心业务逻辑（状态协调）与数据持久化方式完全分离，提高了系统的可维护性和可扩展性。

## 标签
#comp/engine #concept/history #scope/core

---

## Script

### Acts 1: 增强 GitDB 模块

为了支持 `capture` 类型节点摘要的自动生成，我们需要在 `GitDB` 中添加一个新方法 `get_diff_name_status`，用于获取两个 tree 之间的文件变更状态列表。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from contextlib import contextmanager
from quipu.core.exceptions import ExecutionError
~~~~~
~~~~~python
import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager
from quipu.core.exceptions import ExecutionError
~~~~~

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        """
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()
~~~~~
~~~~~python
    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        """
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()

    def get_diff_name_status(self, old_tree: str, new_tree: str) -> List[Tuple[str, str]]:
        """
        获取两个 Tree 之间的文件变更状态列表 (M, A, D, etc.)。
        """
        result = self._run(["diff-tree", "--name-status", "--no-commit-id", "-r", old_tree, new_tree])
        changes = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                changes.append((status, path))
        return changes
~~~~~

### Acts 2: 实现 GitObjectHistoryWriter

现在，我们创建新的 `git_object_storage.py` 文件，并实现 `GitObjectHistoryWriter` 类。这个类将严格遵循 `QDPS v1.0` 规范，完成从构建元数据到创建 Git Commit 的完整流程。

~~~~~act
write_file
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_object_storage.py
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
from quipu.core.storage import HistoryWriter

logger = logging.getLogger(__name__)


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
            # 尝试从 Markdown 的第一个标题中提取
            match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            # 如果找不到标题，则从第一个非空行提取
            for line in content.strip().splitlines():
                clean_line = line.strip()
                if clean_line:
                    return (clean_line[:75] + '...') if len(clean_line) > 75 else clean_line
            return "Plan executed"

        elif node_type == "capture":
            user_message = kwargs.get("message", "").strip()
            
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

        last_commit_hash: Optional[str] = None
        res = self.git_db._run(["rev-parse", "refs/quipu/history"], check=False, log_error=False)
        if res.returncode == 0:
            last_commit_hash = res.stdout.strip()

        parents = [last_commit_hash] if last_commit_hash else None
        commit_message = f"{summary}\n\nX-Quipu-Output-Tree: {output_tree}"
        new_commit_hash = self.git_db.commit_tree(
            tree_hash=tree_hash, parent_hashes=parents, message=commit_message
        )

        self.git_db.update_ref("refs/quipu/history", new_commit_hash)
        logger.info(f"✅ History node created as commit {new_commit_hash[:7]}")

        # 返回一个 QuipuNode 实例以兼容现有接口
        return QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=datetime.fromtimestamp(start_time),
            # 使用 Commit Hash 作为唯一标识符，因为它不再对应单个文件
            filename=Path(f".quipu/git_objects/{new_commit_hash}"),
            node_type=node_type,
            content=content,
        )
~~~~~