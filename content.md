好的，我将创建一个计划来修复这些由 `ruff` 报告的代码风格和未使用的变量问题。

这个计划将通过一系列 `patch_file` 操作来精确地修正每个文件中的问题，确保代码库的整洁和一致性。

## [WIP] style: 修复 ruff 报告的 linting 错误

### 用户需求
根据 `ruff` 的输出，修复项目中存在的代码风格问题，主要包括行太长 (E501) 和未使用的变量 (F841, F811)。

### 评论
这是一次常规的代码健康度维护。通过修复这些 linting 问题，可以提升代码的可读性，并消除潜在的逻辑错误（例如，由于未使用的变量赋值而掩盖了函数没有按预期返回的问题）。

### 目标
1.  修正所有 `E501` (Line too long) 错误，将过长的代码行进行格式化换行。
2.  移除所有 `F841` (Local variable ... is assigned to but never used) 错误中不必要的变量赋值。
3.  修复 `F811` (Redefinition of unused ...) 错误，移除不必要的 `import`。
4.  确保所有修改后，测试套件依然能成功通过。

### 基本原理
我们将使用 `patch_file` 指令，为 `ruff` 报告的每个问题提供精确的、上下文感知的修复。对于未使用的变量，我们将只移除赋值操作，保留有副作用的函数调用。对于过长的代码行，我们将通过添加换行符来重新格式化代码，使其符合 120 个字符的行长度限制。

### 标签
#intent/tune #flow/ready #priority/medium #comp/runtime #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/linting #task/action/fix #task/state/begin

---

### Script

#### Acts 1: 修复 `quipu-runtime` 中的超长行

我们将 `executor.py` 中过长的 f-string 日志消息拆分为两行。

~~~~~act
patch_file
packages/quipu-runtime/src/pyquipu/runtime/executor.py
~~~~~
~~~~~python
                    if block_contexts:
                        logger.debug(
                            f"ℹ️  [{act_name} - Exclusive] Inline args detected, ignoring {len(block_contexts)} subsequent Block(s)."
                        )
~~~~~
~~~~~python
                    if block_contexts:
                        logger.debug(
                            f"ℹ️  [{act_name} - Exclusive] Inline args detected,"
                            f" ignoring {len(block_contexts)} subsequent Block(s)."
                        )
~~~~~

#### Acts 2: 修复 CLI 测试中的未使用变量

在 `test_query_commands.py` 中，移除对 `engine.capture_drift` 结果的不必要赋值。

~~~~~act
patch_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
    (work_dir / "f1").touch()
    node1 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    node2 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
~~~~~
~~~~~python
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
~~~~~

#### Acts 3: 修复 Engine SQLite 测试中的未使用变量

在 `test_reader.py` 中，移除对 `git_writer.create_node` 结果的不必要赋值。

~~~~~act
patch_file
tests/engine/sqlite/test_reader.py
~~~~~
~~~~~python
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        node_a_git = git_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Content A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        node_b_git = git_writer.create_node("plan", hash_a, hash_b, "Content B")
~~~~~
~~~~~python
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        git_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Content A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        git_writer.create_node("plan", hash_a, hash_b, "Content B")
~~~~~

#### Acts 4: 修复 Engine SQLite 测试中的超长行

在 `test_reader_integrity.py` 中，将过长的 SQL `INSERT` 语句换行以符合长度限制。

~~~~~act
patch_file
tests/engine/sqlite/test_reader_integrity.py
~~~~~
~~~~~python
    with conn:
        conn.execute(
            """
            INSERT INTO nodes (commit_hash, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (commit_hash, output_tree, "capture", time.time(), "Corrupted Self-Loop Node", "manual", "{}", None),
        )
~~~~~
~~~~~python
    with conn:
        conn.execute(
            """
            INSERT INTO nodes (
                commit_hash, output_tree, node_type, timestamp, summary,
                generator_id, meta_json, plan_md_cache
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (commit_hash, output_tree, "capture", time.time(), "Corrupted Self-Loop Node", "manual", "{}", None),
        )
~~~~~

#### Acts 5: 修复 Engine Git 测试中的未使用变量

在 `test_git_reader.py` 中，移除对 `writer.create_node` 结果的不必要赋值。

~~~~~act
patch_file
tests/engine/test_git_reader.py
~~~~~
~~~~~python
        (repo / "base").touch()
        hash_a = git_db.get_tree_hash()
        node_a = writer.create_node("plan", h0, hash_a, "Plan A", start_time=1000)
        time.sleep(0.01)
~~~~~
~~~~~python
        (repo / "base").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", h0, hash_a, "Plan A", start_time=1000)
        time.sleep(0.01)
~~~~~

#### Acts 6: 修复集成测试中的导入和未使用变量

在 `test_sync_modes.py` 中，修复 `F811` 错误，移除不必要的 `sync_test_environment` 导入；同时修复 `F841` 错误，移除未使用的 `user_a_id` 变量。

~~~~~act
patch_file
tests/integration/test_sync_modes.py
~~~~~
~~~~~python
from .test_sync_workflow import (  # noqa: F401, sync_test_environment  # noqa: F401, sync_test_environment
    run_git_command,
    sync_test_environment,
)
~~~~~
~~~~~python
from .test_sync_workflow import (  # noqa: F401
    run_git_command,
)
~~~~~

~~~~~act
patch_file
tests/integration/test_sync_modes.py
~~~~~
~~~~~python
    def test_push_force_mode(self, sync_test_environment):
        """User A force-pushes, deleting a stale ref on the remote."""
        remote_path, user_a_path, _ = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")

        # User A creates two nodes and pushes
~~~~~
~~~~~python
    def test_push_force_mode(self, sync_test_environment):
        """User A force-pushes, deleting a stale ref on the remote."""
        remote_path, user_a_path, _ = sync_test_environment

        # User A creates two nodes and pushes
~~~~~

#### Acts 7: 修复集成测试中的未使用变量

在 `test_sync_workflow.py` 中，移除未使用的 `remote_refs_before` 变量。

~~~~~act
patch_file
tests/integration/test_sync_workflow.py
~~~~~
~~~~~python
        # Sync to ensure remote has it
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        remote_refs_before = run_git_command(remote_path, ["for-each-ref", f"refs/quipu/users/{user_a_id}"])
        assert "plan3" in str(run_git_command(user_a_path, ["log", "--all"]))  # Verify creation
~~~~~
~~~~~python
        # Sync to ensure remote has it
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        run_git_command(remote_path, ["for-each-ref", f"refs/quipu/users/{user_a_id}"])
        assert "plan3" in str(run_git_command(user_a_path, ["log", "--all"]))  # Verify creation
~~~~~

### 下一步建议
在应用这些修复后，建议重新运行 `ruff check .` 以确认所有已报告的问题都已解决。之后，可以运行完整的测试套件 (`pytest`) 以确保这些风格修复没有引入任何回归性错误。
