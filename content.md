## 我们将彻底重写 `Hydrator.sync` 的逻辑，使其在重建时能够正确地识别和处理**所有**需要补水的节点，而不仅仅是分支末端。

你做得非常对。你的操作 (`quipu` vs `qd`) 和日志分析揭示了两个独立的问题，其中一个是我代码中的一个极其隐蔽且严重的 bug。

让我们一步步拆解，然后给出最终的、正确的修复方案。

### 错误分析

1.  **`ModuleNotFoundError` (环境问题)**:
    *   你运行 `quipu cache rebuild` 时失败，是因为 `quipu` 命令来自你虚拟环境中 `pip install -e .` 安装的版本。你在 `quipu-cli` 的 `pyproject.toml` 中添加了 `quipu-common` 作为依赖，但可能没有更新安装。这是一个次要的打包问题，通过 `qd` 绕过是完全正确的。

2.  **`FOREIGN KEY constraint failed` (核心 Bug)**:
    *   你运行 `qd cache rebuild` 后，日志显示 `发现 40 个需要补水的节点`，然后是外键错误。
    *   **这是真正的根本原因，也是我之前所有修复方案中未能发现的逻辑缺陷**:
        *   `Hydrator` 的 `_get_missing_commits_with_owner` 方法**只查找分支的末端节点 (heads)**。
        *   在 `sync` 方法中，主循环是 `for commit_hash in missing_hashes:`。
        *   这意味着，即使我们加载了完整的历史图谱到 `log_map`，代码也**只尝试处理那 40 个末端节点**，而完全忽略了历史记录中的另外 366 个中间节点。
        *   当它尝试为这 40 个末端节点创建指向其父节点的边时，由于父节点不在 `missing_hashes` 列表中，所以父节点没有被添加到 `nodes_to_insert` 批次中，从而导致了外键约束失败。

**结论**: 你的外部脚本完美地完成了 Git 引用的迁移。现在的问题纯粹是 `Hydrator` 在从零重建数据库时，其内部逻辑存在致命缺陷。

### 最终修复方案

我们将彻底重写 `Hydrator.sync` 的逻辑，使其在重建时能够正确地识别和处理**所有**需要补水的节点，而不仅仅是分支末端。

### 标签
#intent/fix #flow/ready #priority/critical 
#comp/engine #scope/core 
#ai/instruct
#task/domain/storage #task/object/hydrator #task/action/bug-fix
#task/state/end

---

### Script

#### Acts 1: 彻底重写 `Hydrator.sync`

这个 `write_file` 操作将用一个健壮的、逻辑正确的版本替换掉整个 `sync` 方法。

~~~~~act
write_file
packages/quipu-engine/src/quipu/core/hydrator.py
~~~~~
~~~~~python
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
        # 匹配 remote 镜像: refs/quipu/remotes/<remote_name>/<user_id>/heads/...
        remote_match = re.match(r"refs/quipu/remotes/[^/]+/([^/]+)/heads/.*", ref_name)
        if remote_match:
            return remote_match.group(1)

        # 匹配 local heads
        if ref_name.startswith("refs/quipu/local/heads/"):
            return local_user_id

        return None

    def _get_commit_owners(self, local_user_id: str) -> Dict[str, str]:
        """
        构建一个从 commit_hash 到 owner_id 的映射。
        一个 commit 的所有者由指向它的最高优先级引用决定。
        """
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
        # 1.1 获取所有 Quipu 历史中的 commit 日志
        all_ref_heads = [t[0] for t in self.git_db.get_all_ref_heads("refs/quipu/")]
        if not all_ref_heads:
            logger.debug("✅ Git 中未发现 Quipu 引用，无需补水。")
            return

        all_git_logs = self.git_db.log_ref(all_ref_heads)
        if not all_git_logs:
            logger.debug("✅ Git 中未发现 Quipu 历史，无需补水。")
            return
            
        log_map = {entry["hash"]: entry for entry in all_git_logs}
        
        # 1.2 确定所有者的映射关系
        commit_owners = self._get_commit_owners(local_user_id)

        # 1.3 计算真正需要插入的节点 (所有历史节点 - 已在数据库中的节点)
        db_hashes = self.db_manager.get_all_node_hashes()
        missing_hashes = set(log_map.keys()) - db_hashes
        
        if not missing_hashes:
            logger.debug("✅ 数据库与 Git 历史一致，无需补水。")
            return
            
        logger.info(f"发现 {len(missing_hashes)} 个需要补水的节点。")

        # --- 阶段 2: 批量准备数据 ---
        nodes_to_insert: List[Tuple] = []
        edges_to_insert: List[Tuple] = []

        # 2.1 批量获取 Trees
        tree_hashes = [log_map[h]["tree"] for h in missing_hashes if h in log_map]
        trees_content = self.git_db.batch_cat_file(tree_hashes)

        # 2.2 解析 Trees, 批量获取 Metas
        tree_to_meta_blob: Dict[str, str] = {}
        meta_blob_hashes: List[str] = []
        for tree_hash, content_bytes in trees_content.items():
            entries = self._parser._parse_tree_binary(content_bytes)
            if "metadata.json" in entries:
                blob_hash = entries["metadata.json"]
                tree_to_meta_blob[tree_hash] = blob_hash
                meta_blob_hashes.append(blob_hash)
        metas_content = self.git_db.batch_cat_file(meta_blob_hashes)

        # 2.3 构建插入数据 (只遍历需要补水的节点)
        for commit_hash in missing_hashes:
            log_entry = log_map[commit_hash]
            tree_hash = log_entry["tree"]
            # 确定所有者：优先从 head 映射中获取，如果没有则认为是本地用户
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
                # 处理边关系：父节点必须存在于我们的完整历史记录中
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
~~~~~

### 下一步建议

你已经完成了最困难的部分。外部脚本已经成功地将 Git 引用迁移到了 v1.1 格式。现在，只需应用这个最终的 `Hydrator` 修复，然后重建数据库即可。

1.  **应用代码补丁**: 使用上述 `write_file` 内容，覆盖 `packages/quipu-engine/src/quipu/core/hydrator.py`。

2.  **重建缓存**:
    ```bash
    # 确保 .quipu/history.sqlite 不存在
    rm .quipu/history.sqlite

    # 运行重建命令
    qd cache rebuild --force
    ```

3.  **验证**:
    *   **检查日志**: 这次，你应该看到 `发现 406 个需要补水的节点。`，并且**不会**再有 `FOREIGN KEY` 错误。
    *   **运行 `qd ui`**: 它现在会正常启动，并显示包含所有 406 个节点的、关系完整的历史图谱。
