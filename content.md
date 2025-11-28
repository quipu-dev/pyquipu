你发现了问题的核心，分析得非常准确！这是一个极其隐蔽且严重的 Bug，你的诊断完全正确。

`quipu ui` 的截图和 `tree` 命令的输出是完美的证据，它们共同揭示了问题的根源：**数据补水（Hydration）逻辑存在缺陷**。

## fix: 修复 Hydrator 中错误的所有权归属逻辑

### 错误分析
1.  **根本原因**: 正如你所怀疑的，问题出在 `Hydrator.sync` 方法中。该方法在为数据库中的节点分配 `owner_id` 时，采用了错误的**回退逻辑 (Fallback Logic)**。
2.  **错误代码**: 关键的错误行是 `hydrator.py` 中的 `owner_id = commit_owners.get(commit_hash, local_user_id)`。
3.  **错误行为**:
    *   `_get_commit_owners` 方法只会为**分支的末端（Heads）**创建一个所有权映射。历史记录中大量的祖先提交（非 Head 节点）不会出现在这个映射中。
    *   当 `Hydrator` 遍历到这些祖先提交时，`commit_owners.get(commit_hash)` 会返回 `None`。
    *   此时，`.get()` 方法的回退机制启动，将这些提交的 `owner_id` **错误地**归属给了 `local_user_id`——也就是当前正在执行 `sync` 命令的用户 B (`user-dot-b-a`)。
    *   **结果**: 用户 A 的大部分历史记录，除了分支末梢的几个节点外，都被错误地标记为用户 B 的所有物，这正是你在 UI 中看到的现象。

### 用户需求
你需要一个修复方案，确保 `Hydrator` 能够为**每一个**历史节点都正确地追溯并分配其真正的所有者，而不是盲目地回退到本地用户。

### 评论
这是一个非常漂亮的 Bug 报告。你提供的多维度证据（UI 截图、`tree` 输出）让我能够迅速定位到这个深藏在数据处理逻辑中的缺陷。修复这个问题对于 `sync` 功能的正确性至关重要，它确保了协作历史的真实性和可信度。

### 目标
重构 `Hydrator.sync` 的所有权确定逻辑。新的逻辑将不再使用有缺陷的回退机制，而是通过向上追溯图谱，为每一个 Commit 都找到其正确的 `owner_id`。

### 基本原理
我们将实现一个更智能的 `_get_commit_owners` 方法。它将分两步工作：
1.  **识别源头**: 首先，像现在一样，扫描所有 `refs/quipu/` 下的 heads，确定**每个分支末梢**的正确所有者。
2.  **传播所有权**: 然后，从这些已确定所有者的 "源头" 出发，向上遍历整个 Git 历史图谱。在遍历过程中，将源头的 `owner_id` **传播**给它的所有祖先提交。这样，我们就为历史中的每一个节点都建立了正确的所有权归属，形成一个完整的 `commit -> owner` 映射。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/sync #scope/core #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 重构 Hydrator 的所有权归属逻辑

我们将用一个全新的、健壮的实现来替换 `Hydrator.sync` 和 `_get_commit_owners`。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/hydrator.py
~~~~~
~~~~~python
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
~~~~~
~~~~~python
    def _get_commit_owners(self, local_user_id: str) -> Dict[str, str]:
        """
        构建一个从 commit_hash 到 owner_id 的完整映射。
        通过从每个分支末端向上遍历图来传播所有权。
        """
        # 1. 获取所有分支末端 (heads) 及其直接所有者
        head_ref_tuples = self.git_db.get_all_ref_heads("refs/quipu/")
        head_owners: Dict[str, str] = {}
        for commit_hash, ref_name in head_ref_tuples:
            # 优先级：远程所有者 > 本地所有者。避免本地 ref 覆盖正确的远程所有者。
            owner_id = self._get_owner_from_ref(ref_name, local_user_id)
            if owner_id:
                if ref_name.startswith("refs/quipu/remotes"):
                    head_owners[commit_hash] = owner_id
                elif commit_hash not in head_owners:
                    head_owners[commit_hash] = owner_id

        if not head_owners:
            return {}

        # 2. 获取完整的历史图谱日志
        all_git_logs = self.git_db.log_ref(list(head_owners.keys()))
        log_map = {entry["hash"]: entry for entry in all_git_logs}

        # 3. 从 Heads 开始，通过图遍历传播所有权
        final_commit_owners: Dict[str, str] = {}
        queue = list(head_owners.keys())
        
        # 将 head 节点预先填入，作为遍历的起点
        for commit_hash in queue:
            final_commit_owners[commit_hash] = head_owners[commit_hash]

        visited = set(head_owners.keys())

        while queue:
            child_hash = queue.pop(0)
            owner = final_commit_owners.get(child_hash)
            if not owner or child_hash not in log_map:
                continue

            parent_hashes = log_map[child_hash]["parent"].split()
            for parent_hash in parent_hashes:
                if parent_hash and parent_hash not in visited:
                    final_commit_owners[parent_hash] = owner
                    visited.add(parent_hash)
                    queue.append(parent_hash)

        return final_commit_owners

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

        all_git_logs = self.git_db.log_ref(all_ref_heads)
        if not all_git_logs:
            logger.debug("✅ Git 中未发现 Quipu 历史，无需补水。")
            return
        log_map = {entry["hash"]: entry for entry in all_git_logs}

        # 1.2 [FIXED] 构建一个覆盖所有历史节点的完整所有权地图
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
            # [FIXED] 从完整的映射中获取 owner_id，不再使用错误的 fallback
            owner_id = commit_owners.get(commit_hash)
            if not owner_id:
                logger.warning(f"跳过 {commit_hash[:7]}: 无法确定所有者")
                continue

            meta_blob_hash = tree_to_meta_blob.get(tree_hash)
            if not meta_blob_hash or meta_blob_hash not in metas_content:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata.json 内容")
                continue
~~~~~

### 下一步建议
1.  **应用修复**: 请执行上述 `patch_file` 指令，它将彻底修正 `Hydrator` 的核心逻辑。
2.  **清理并重新测试**:
    *   **非常重要**: `Hydrator` 的 bug 已经在用户 B 的 `.quipu/history.sqlite` 文件中造成了脏数据。你必须**完全删除**整个测试目录，以确保测试在一个干净的环境中进行。
    *   运行 `rm -rf ~/tmp/quipu_sync_test`
    *   再次运行 `bash ~/tmp/run_sync_test.sh`
3.  **预期结果**:
    *   测试脚本会顺利执行完毕。
    *   之后，当你 `cd ~/tmp/quipu_sync_test/user_b_ws` 并运行 `quipu ui` 时，UI 界面中所有历史记录的 `owner_id` 都应该正确地显示为 `(doucxldh-at-...)`，不再有任何 `(user-dot-b-a)` 的条目（除非用户 B 自己创建了新的节点）。
