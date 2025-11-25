import json
import logging
import os
import platform
import time
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime
import importlib.metadata

from quipu.core.models import QuipuNode
from quipu.core.git_db import GitDB
from quipu.core.file_system_storage import FileSystemHistoryReader

logger = logging.getLogger(__name__)

class HistoryMigrator:
    """
    负责将旧的文件系统历史记录迁移到 Git 对象存储格式。
    遵循 QDPS v1.0 规范中的迁移策略。
    """

    def __init__(self, root_dir: Path, git_db: GitDB):
        self.root_dir = root_dir
        self.git_db = git_db
        self.fs_reader = FileSystemHistoryReader(root_dir / ".quipu" / "history")

    def _get_migrator_version(self) -> str:
        try:
            return importlib.metadata.version("quipu-engine")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def _build_metadata(self, node: QuipuNode, assumed_env: List[str]) -> Dict[str, Any]:
        """根据 QDPS v1.0 迁移规范构建 metadata.json"""
        
        # 提取时间戳
        # 旧文件名格式: {input}_{output}_{YYYYMMDDHHMMSS}.md
        # 已经在 node.timestamp 中解析好了
        start_time = node.timestamp.timestamp()

        metadata = {
            "meta_version": "1.0-migrated",
            "type": node.node_type,
            "summary": node.summary,
            "generator": {
                "id": "manual-migrated",
                "tool": "quipu-cli-legacy"
            },
            "env": {
                "quipu": "unknown",
                # 知情猜测
                "python": platform.python_version(),
                "os": platform.system().lower()
            },
            "exec": {
                "start": start_time,
                "duration_ms": -1
            },
            "migration_info": {
                "migrated_at": time.time(),
                "migrator_version": self._get_migrator_version(),
                "assumed_env": assumed_env
            }
        }
        return metadata

    def migrate(self, dry_run: bool = False) -> int:
        """
        执行迁移过程。
        
        Returns:
            int: 迁移成功的节点数量
        """
        if not (self.root_dir / ".quipu" / "history").exists():
            logger.warning("未找到旧版历史目录 (.quipu/history)，无需迁移。")
            return 0

        # 1. 加载所有旧节点
        # load_all_nodes 会处理排序和父子关系
        nodes = self.fs_reader.load_all_nodes()
        if not nodes:
            logger.info("旧版历史目录为空。")
            return 0

        logger.info(f"找到 {len(nodes)} 个旧历史节点，准备迁移...")

        # 2. 准备状态映射表: output_tree_hash -> new_commit_hash
        # 用于将基于 Tree 的链接转换为基于 Commit 的链接
        tree_to_commit: Dict[str, str] = {}
        
        # 创世哈希 (Empty Tree)
        GENESIS_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        
        migrated_count = 0
        assumed_env = ["python", "os"]

        # 按照时间顺序处理
        # 确保父节点先被处理并进入映射表
        sorted_nodes = sorted(nodes, key=lambda n: n.timestamp)

        for node in sorted_nodes:
            # 查找父 Commit
            parent_commit: Optional[str] = None
            
            if node.input_tree == GENESIS_HASH:
                # 根节点，无父 Commit
                parent_commit = None
            elif node.input_tree in tree_to_commit:
                parent_commit = tree_to_commit[node.input_tree]
            else:
                # 这是一个断链的节点（input_tree 指向了一个未知的状态，或者之前的节点尚未迁移）
                # 在旧的线性历史中，这可能意味着它是另一个分支的开始，或者历史不完整
                # 策略：视为新的根节点
                logger.warning(f"节点 {node.filename.name} 的输入状态 {node.input_tree[:7]} 未在已迁移历史中找到。将其作为新的根节点处理。")
                parent_commit = None

            if dry_run:
                logger.info(f"[Dry Run] Would migrate node: {node.summary} ({node.timestamp})")
                migrated_count += 1
                # 模拟更新映射，以便后续节点能找到父节点
                tree_to_commit[node.output_tree] = f"mock_commit_for_{node.output_tree}"
                continue

            # --- Git 底层操作 ---
            
            # 1. 准备 Metadata
            meta_data = self._build_metadata(node, assumed_env)
            meta_bytes = json.dumps(meta_data, sort_keys=False, ensure_ascii=False).encode('utf-8')
            
            # 2. 准备 Content
            # 移除可能存在的 Frontmatter (虽然 fs_reader 已经解析了，但 content 属性可能还保留着纯文本)
            # QuipuNode.content 是 body_content，已经去除了 Frontmatter
            content_bytes = node.content.encode('utf-8')

            # 3. Hash Objects
            meta_blob = self.git_db.hash_object(meta_bytes)
            content_blob = self.git_db.hash_object(content_bytes)

            # 4. Make Tree
            # 必须使用 tab 分隔
            tree_desc = (
                f"100444 blob {meta_blob}\tmetadata.json\n"
                f"100444 blob {content_blob}\tcontent.md"
            )
            tree_hash = self.git_db.mktree(tree_desc)

            # 5. Commit Tree
            parents = [parent_commit] if parent_commit else []
            # Subject
            message = f"{node.summary}\n\nX-Quipu-Output-Tree: {node.output_tree}"
            
            commit_hash = self.git_db.commit_tree(tree_hash, parents, message)
            
            # 6. 更新映射
            tree_to_commit[node.output_tree] = commit_hash
            
            # 7. 更新 Ref (每次都更新，确保 HEAD 指向最新的)
            # 注意：对于分叉的情况，这会导致 HEAD 在不同分支间跳动，最终指向时间戳最新的那个
            # 这对于单线历史是可以的。对于复杂图谱，我们可能需要更复杂的 ref 管理
            # 但 QDPS v1.0 暂定使用单一 refs/quipu/history
            self.git_db.update_ref("refs/quipu/history", commit_hash)
            
            migrated_count += 1
            logger.debug(f"已迁移节点: {node.summary} -> {commit_hash[:7]}")

        logger.info(f"迁移完成。共迁移 {migrated_count} 个节点。")
        return migrated_count