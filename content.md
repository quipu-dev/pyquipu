好的，收到了测试结果。`pytest` 报告了两个失败的测试用例，我们需要逐一分析并修复它们。

## fix: 修复 CLI 测试中的逻辑错误与验证问题

### 错误分析
测试执行结果显示，两个关键的测试用例失败了：

1.  **`test_find_command` in `test_query_commands.py`**:
    -   **现象**: `find` 命令未能找到一个预期的 "plan" 节点。
    -   **根因**: 测试代码在创建 "plan" 节点时，使用了无效的 `output_tree="hash_placeholder"`。`quipu find` 命令依赖 `GitObjectHistoryReader` 从真实的 Git 对象中读取历史。一个指向不存在的 tree 对象的节点是无效的，因此在命令的执行上下文中无法被加载和找到。

2.  **`test_save_with_changes` in `test_workspace_commands.py`**:
    -   **现象**: `quipu save` 命令在一个没有任何 Quipu 历史的 "genesis" 仓库中执行失败，返回了非零退出码。
    -   **根因**:
        1.  **验证逻辑错误**: 测试用例在 `runner.invoke` 之后检查了 `engine.history_graph` 的长度。`runner.invoke` 在一个独立的子流程中创建了全新的 `engine` 实例，测试函数作用域内的 `engine` 对象的状态不会被更新。因此，这个断言是无效的。
        2.  **潜在的 Genesis Bug**: 命令的失败表明在仓库中创建第一个节点（创世节点）的逻辑路径中可能存在一个未被发现的 bug。修复测试的验证逻辑是解决此问题的第一步，我们将通过更可靠的集成测试方式来确保其正确性。

### 用户需求
-   修复所有失败的测试，确保 CI 流水线恢复健康。
-   提高测试代码的健壮性，使用正确的集成测试模式来验证 CLI 命令的副作用。

### 评论
这些测试失败暴露了测试用例编写中的一些常见陷阱：测试数据与生产逻辑不一致（无效的哈希），以及对命令执行副作用的验证方式不当。修复这些问题将显著提高我们测试套件的可靠性。

### 目标
1.  **修正 `test_find_command`**: 重构该测试，确保在创建 "plan" 节点时使用通过 `engine.git_db.get_tree_hash()` 获取的真实、有效的 `input_tree` 和 `output_tree` 哈希。
2.  **修正 `test_save_with_changes`**:
    -   移除对过时 `engine` 实例状态的无效断言。
    -   采用更可靠的集成测试方法：在 `save` 命令成功后，立即执行 `quipu log` 命令，并断言新创建的快照摘要出现在 `log` 的输出中。

### 基本原理
-   **忠于现实**: 测试的设置（Setup）阶段应尽可能模拟真实的使用场景。创建历史节点时，必须确保其数据在底层存储（Git objects）中是完整和有效的。
-   **通过公共接口验证**: 测试 CLI 命令的副作用时，最佳实践是通过执行另一个公共的、只读的 CLI 命令（如 `log` 或 `status`）来验证状态变更，而不是检查内部对象的内存状态。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/cli-commands #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修复 `test_find_command` 的节点创建逻辑

我们将确保 `create_plan_node` 使用的是在文件系统上真实存在的状态哈希。

~~~~~act
patch_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
def test_find_command(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Fix bug")
    
    (work_dir / "f2").touch()
    engine.create_plan_node(
        input_tree=engine.git_db.get_tree_hash(),
        output_tree="hash_placeholder",
        plan_content="content",
        summary_override="Implement feature"
    )
    
    # 查找 "Fix"
~~~~~
~~~~~python
def test_find_command(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    (work_dir / "f1").touch()
    capture_node = engine.capture_drift(engine.git_db.get_tree_hash(), message="Fix bug")
    hash_v1 = capture_node.output_tree

    (work_dir / "f2").touch()
    hash_v2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(
        input_tree=hash_v1,
        output_tree=hash_v2,
        plan_content="content",
        summary_override="Implement feature",
    )

    # 查找 "Fix"
~~~~~

#### Acts 2: 修复 `test_save_with_changes` 的验证逻辑

我们将重写此测试，使其通过 `quipu log` 命令来验证 `save` 操作是否成功。

~~~~~act
patch_file
tests/cli/test_workspace_commands.py
~~~~~
~~~~~python
def test_save_with_changes(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    # 制造变更
    (work_dir / "file.txt").write_text("v2")
    
    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "快照已保存" in result.stderr
    assert "(My Snapshot)" in result.stderr
    
    # 验证历史记录增加
    assert len(engine.history_graph) == 1
~~~~~
~~~~~python
def test_save_with_changes(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace

    # 制造变更
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0, f"Save command failed with stderr: {result.stderr}"
    assert "快照已保存" in result.stderr
    assert "(My Snapshot)" in result.stderr

    # 验证历史记录已增加，通过 log 命令
    log_result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert log_result.exit_code == 0
    assert "My Snapshot" in log_result.stderr
~~~~~

### 下一步建议
再次运行 `pytest tests/cli` 确认所有测试都已通过。通过之后，我们可以继续为其他模块（如 `remote` 命令）或 `acts` 补充测试用例，进一步提升代码库的质量。
