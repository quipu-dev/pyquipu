好的，我将解决这个问题。

问题在于 `SQLiteHistoryWriter` 在双写过程中没有获取并存入 `owner_id`。当一个新节点被创建时，它的所有者应该是当前的本地用户。

解决方案分为两部分：
1.  **`Engine` (状态机)**: 在创建节点 (`capture_drift`, `create_plan_node`) 时，它将负责从 `.quipu/config.yml` 中读取 `user_id`。
2.  **`SQLiteHistoryWriter` (存储层)**: `Engine` 会将获取到的 `user_id` 作为 `owner_id` 传递给 `create_node` 方法，该方法会将其写入 SQLite 数据库。

这样可以确保每次创建新节点时，所有权信息都会被实时、准确地记录在数据库缓存中，无需等待下一次数据补水。

## fix: 在双写时实时写入 owner_id 至数据库

### 错误分析
当前的 `SQLiteHistoryWriter` 在执行“双写”操作时，虽然会将节点元数据写入 SQLite，但其 `INSERT` 语句遗漏了 `owner_id` 字段。这导致新创建的本地节点的 `owner_id` 在数据库中为空，直到下一次 `sync` 或 `align` 触发数据补水 (`Hydrator`) 时才被填充。这种延迟破坏了数据的一致性，并可能导致 UI 在补水前显示不正确的或缺失的所有者信息。

### 用户需求
确保当 `quipu save` 或 `quipu run` 创建一个新节点时，该节点的 `owner_id` (即当前用户的 ID) 能够被立即写入 `.quipu/history.sqlite` 数据库的 `nodes` 表中。

### 评论
这是一个关键的数据完整性修复。通过在写入路径上直接注入所有者信息，我们确保了 SQLite 缓存始终是 Git 底层状态的准确反映，简化了系统逻辑并提升了 UI 的即时正确性。

### 目标
1.  修改 `Engine` 模块，使其在调用 `HistoryWriter.create_node` 时，能够从配置中读取 `user_id` 并将其作为 `owner_id` 参数传递。
2.  修改 `SQLiteHistoryWriter.create_node` 方法，使其能够接收 `owner_id` 参数，并更新 SQL `INSERT` 语句以包含该字段。

### 基本原理
在系统的写入流程中，`Engine` 是唯一能够访问工作区上下文 (用于读取配置) 并协调存储写入的角色。因此，由 `Engine` 负责提供 `owner_id` 是最符合架构职责分离原则的做法。`SQLiteHistoryWriter` 则专注于执行数据库写入的原子操作。

### 标签
#intent/fix #flow/ready #priority/high #comp/engine #concept/history #scope/core #ai/instruct #task/domain/storage #task/object/sqlite-backend #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修改 `Engine` 以传递 `owner_id`

我们将修改 `state_machine.py` 中的 `capture_drift` 和 `create_plan_node` 方法，让它们在调用 `writer.create_node` 时注入 `owner_id`。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
        body = (
            f"# 📸 Snapshot Capture\n\n"
            f"{user_message_section}"
            f"检测到工作区发生变更。\n\n"
            f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
        )

        new_node = self.writer.create_node(
            node_type="capture", input_tree=input_hash, output_tree=current_hash, content=body, message=message
        )

        self.history_graph[current_hash] = new_node
~~~~~
~~~~~python
        body = (
            f"# 📸 Snapshot Capture\n\n"
            f"{user_message_section}"
            f"检测到工作区发生变更。\n\n"
            f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
        )

        config = ConfigManager(self.root_dir)
        user_id = config.get("sync.user_id", "unknown-local-user")

        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        self.history_graph[current_hash] = new_node
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
    def create_plan_node(
        self, input_tree: str, output_tree: str, plan_content: str, summary_override: Optional[str] = None
    ) -> QuipuNode:
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")

        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
        )

        self.history_graph[output_tree] = new_node
~~~~~
~~~~~python
    def create_plan_node(
        self, input_tree: str, output_tree: str, plan_content: str, summary_override: Optional[str] = None
    ) -> QuipuNode:
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")

        config = ConfigManager(self.root_dir)
        user_id = config.get("sync.user_id", "unknown-local-user")

        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        self.history_graph[output_tree] = new_node
~~~~~

#### Acts 2: 更新 `SQLiteHistoryWriter` 以存入 `owner_id`

现在，我们修改 `sqlite_storage.py` 中的 `SQLiteHistoryWriter.create_node` 方法，使其能够处理 `owner_id` 并将其存入数据库。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
            # 2.2 写入 'nodes' 表
            self.db_manager.execute_write(
                """
                INSERT OR REPLACE INTO nodes 
                (commit_hash, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_hash,
                    output_tree,
                    node_type,
                    start_time,
                    summary,
                    metadata["generator"]["id"],
                    meta_json_str,
                    content,  # 热缓存: 新创建的节点内容直接写入缓存
                ),
            )
~~~~~
~~~~~python
            # 2.2 写入 'nodes' 表
            owner_id = kwargs.get("owner_id", "unknown-local-user")
            self.db_manager.execute_write(
                """
                INSERT OR REPLACE INTO nodes 
                (commit_hash, owner_id, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_hash,
                    owner_id,
                    output_tree,
                    node_type,
                    start_time,
                    summary,
                    metadata["generator"]["id"],
                    meta_json_str,
                    content,  # 热缓存: 新创建的节点内容直接写入缓存
                ),
            )
~~~~~

### 下一步建议
修复完成后，建议运行完整的测试套件，特别是与 `quipu save` 和 `quipu ui` 相关的集成测试，以验证 `owner_id` 是否被正确写入和显示。
