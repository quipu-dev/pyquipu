import json
import logging
import re
from typing import List, Dict, Set, Tuple, Optional

from .git_db import GitDB
from .sqlite_db import DatabaseManager
from .git_object_storage import GitObjectHistoryReader  # Reuse parsing logic

logger = logging.getLogger(__name__)


class Hydrator:
    """
    负责将 Git 对象历史记录同步（补水）到 SQLite 数据库。
    """

    def __init__(self, git_db: GitDB, db_manager: DatabaseManager):
        self.git_db = git_db
        self.db_manager = db_manager
        # 复用 Reader 中的二进制解析逻辑，避免代码重复
        self._parser = GitObjectHistoryReader(git_db)

    def _get_owner_from_ref(self, ref_name: str, local_user_id: str) -> Optional[str]:
        """从 Git ref 路径中解析 owner_id。"""
        remote_match = re.match(r"refs/quipu/remotes/[^/]+/([^/]+)/heads/.*", ref_name)
        if remote_match:
            return remote_match.group(1)
        if ref_name.startswith("refs/quipu/local/heads/"):
            return local_user_id
        return None

    def _get_commit_owners(self, local_user_id: str) -> Dict[str, str]:
        """构建一个从 commit_hash 到 owner_id 的映射。"""
        ref_tuples = self.git_db.get_all_ref_heads("refs/quipu/")
        commit_to_owner: Dict[str, str] = {}
        for commit_hash, ref_name in ref_tuples:
            if commit_hash in commit_to_owner:
                continue
            owner_id = self._get_owner_from_ref(ref_name, local_user_id)
            if owner_id:
                commit_to_owner[commit_hash] = owner_id
        return commit_to_owner

    def sync(self, local_user_id: str):
        """
        执行增量补水操作。
        此实现经过重构，以确保在从零重建时能够处理完整的历史图谱。
        """
        # --- 阶段 1: 发现 ---
        all_ref_heads = [t[0] for t in self.git_db.get_all_ref_heads("refs/quipu/")]
        if not all_ref_heads:
            logger.debug("✅ Git 中未发现 Quipu 引用，无需补水。")
            return

        # 1.1 获取所有 Quipu 历史中的完整 commit 日志
        all_git_logs = self.git_db.log_ref(all_ref_heads)
        if not all_git_logs:
            logger.debug("✅ Git 中未发现 Quipu 历史，无需补水。")
            return
        log_map = {entry["hash"]: entry for entry in all_git_logs}
        
        # 1.2 确定 HEAD commit 的所有者
        commit_owners = self._get_commit_owners(local_user_id)

        # 1.3 计算需要插入的节点 (所有历史节点 - 已在数据库中的节点)
        db_hashes = self.db_manager.get_all_node_hashes()
        missing_hashes = set(log_map.keys()) - db_hashes
        
        if not missing_hashes:
            logger.debug("✅ 数据库与 Git 历史一致，无需补水。")
            return
            
        logger.info(f"发现 {len(missing_hashes)} 个需要补水的节点。")

        # --- 阶段 2: 批量准备数据 ---
        nodes_to_insert: List[Tuple] = []
        edges_to_insert: List[Tuple] = []

        tree_hashes = [log_map[h]["tree"] for h in missing_hashes if h in log_map]
        trees_content = self.git_db.batch_cat_file(tree_hashes)

        tree_to_meta_blob: Dict[str, str] = {}
        meta_blob_hashes: List[str] = []
        for tree_hash, content_bytes in trees_content.items():
            entries = self._parser._parse_tree_binary(content_bytes)
            if "metadata.json" in entries:
                blob_hash = entries["metadata.json"]
                tree_to_meta_blob[tree_hash] = blob_hash
                meta_blob_hashes.append(blob_hash)
        metas_content = self.git_db.batch_cat_file(meta_blob_hashes)

        for commit_hash in missing_hashes:
            log_entry = log_map[commit_hash]
            tree_hash = log_entry["tree"]
            owner_id = commit_owners.get(commit_hash, local_user_id)

            meta_blob_hash = tree_to_meta_blob.get(tree_hash)
            if not meta_blob_hash or meta_blob_hash not in metas_content:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata.json 内容")
                continue

            output_tree = self._parser._parse_output_tree_from_body(log_entry["body"])
            if not output_tree:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 Output-Tree trailer")
                continue

            try:
                meta_bytes = metas_content[meta_blob_hash]
                meta_data = json.loads(meta_bytes)
                nodes_to_insert.append(
                    (
                        commit_hash, owner_id, output_tree,
                        meta_data.get("type", "unknown"),
                        float(meta_data.get("exec", {}).get("start") or log_entry["timestamp"]),
                        meta_data.get("summary", "No summary"),
                        meta_data.get("generator", {}).get("id"),
                        meta_bytes.decode("utf-8"), None
                    )
                )
                for p_hash in log_entry["parent"].split():
                    if p_hash in log_map:
                        edges_to_insert.append((commit_hash, p_hash))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"解析 {commit_hash[:7]} 的元数据失败: {e}")

        # --- 阶段 3: 批量写入数据库 ---
        if nodes_to_insert:
            self.db_manager.batch_insert_nodes(nodes_to_insert)
            logger.info(f"💧 {len(nodes_to_insert)} 个节点元数据已补水。")
        if edges_to_insert:
            self.db_manager.batch_insert_edges(edges_to_insert)
            logger.info(f"💧 {len(edges_to_insert)} 条边关系已补水。")