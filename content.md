# fix-head-sync 修复检出操作未更新 HEAD 指针的问题

## 目标
确保 `axon checkout` 和 `axon discard` 命令在重置物理工作区的同时，正确更新 `.axon/HEAD` 指针文件，保持逻辑状态与物理状态的一致性。

## 基本原理
*   **状态封装**: 所有的状态变更（包括“回到过去”）都应该通过 `Engine` 进行，而不是直接操作底层的 `GitDB`。
*   **Engine 扩展**: 在 `Engine` 类中增加 `checkout` 方法，统一处理物理检出 (`git_db.checkout_tree`) 和元数据更新 (`_write_head`)。

## 标签
#fix #core #engine #cli

---

## Script

### Act 1: 在 Engine 中添加 `checkout` 方法

我们将在 `core/engine.py` 中添加一个 `checkout` 方法，作为状态切换的标准入口。

~~~~~act
replace core/engine.py
~~~~~

~~~~~python
        logger.info(f"✅ Plan 已归档: {filename.name}")
        return new_node
~~~~~

~~~~~python
        logger.info(f"✅ Plan 已归档: {filename.name}")
        return new_node

    def checkout(self, target_hash: str):
        """
        将工作区重置到指定状态，并更新 HEAD 指针。
        """
        # 1. 执行物理检出
        self.git_db.checkout_tree(target_hash)
        
        # 2. 更新 HEAD 指针
        self._write_head(target_hash)
        
        # 3. 尝试更新内存中的当前节点状态
        # 注意：如果 history_graph 尚未加载，这里不会更新 current_node，
        # 但这通常没问题，因为下一次操作会重新 align
        if target_hash in self.history_graph:
            self.current_node = self.history_graph[target_hash]
        
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")
~~~~~

### Act 2: 更新 CLI 使用 Engine 进行检出

修改 `main.py` 中的 `discard` 和 `checkout` 命令，将直接调用 `git_db` 改为调用 `engine.checkout`。

~~~~~act
replace main.py
~~~~~

~~~~~python
    if not force:
        typer.confirm(f"🚨 即将丢弃工作区所有未记录的变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？", abort=True)
    try:
        engine.git_db.checkout_tree(target_tree_hash)
        typer.secho(f"✅ 工作区已成功恢复到节点 {latest_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
~~~~~

~~~~~python
    if not force:
        typer.confirm(f"🚨 即将丢弃工作区所有未记录的变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？", abort=True)
    try:
        engine.checkout(target_tree_hash)
        typer.secho(f"✅ 工作区已成功恢复到节点 {latest_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
~~~~~

~~~~~act
replace main.py
~~~~~

~~~~~python
    if not force:
        typer.confirm(f"🚨 即将重置工作区到状态 {target_node.short_hash} ({target_node.timestamp})。\n此操作会覆盖未提交的更改。是否继续？", abort=True)
    try:
        engine.git_db.checkout_tree(target_tree_hash)
        typer.secho(f"✅ 已成功将工作区恢复到节点 {target_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
~~~~~

~~~~~python
    if not force:
        typer.confirm(f"🚨 即将重置工作区到状态 {target_node.short_hash} ({target_node.timestamp})。\n此操作会覆盖未提交的更改。是否继续？", abort=True)
    try:
        engine.checkout(target_tree_hash)
        typer.secho(f"✅ 已成功将工作区恢复到节点 {target_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
~~~~~

### Act 3: 添加测试验证 HEAD 更新

在 `tests/test_head_and_root.py` 中添加测试用例，验证 `checkout` 操作后 HEAD 是否被正确写入。

~~~~~act
append_file tests/test_head_and_root.py
~~~~~

~~~~~python


    def test_checkout_updates_head(self, engine_with_repo):
        """验证 engine.checkout 正确更新 HEAD"""
        engine = engine_with_repo
        
        # 1. Create State A (Plan)
        (engine.root_dir / "f.txt").write_text("v1")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "State A")
        
        # 2. Create State B (Plan)
        (engine.root_dir / "f.txt").write_text("v2")
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")
        
        assert engine._read_head() == hash_b
        
        # 3. Checkout to State A
        engine.checkout(hash_a)
        
        # 4. Assert Physical State
        assert (engine.root_dir / "f.txt").read_text() == "v1"
        
        # 5. Assert Logical State (HEAD)
        assert engine._read_head() == hash_a
~~~~~