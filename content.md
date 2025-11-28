好的，我们来创建一个自动化的 `pytest` 集成测试，将 `run_sync_test.sh` 的核心逻辑固化到我们的测试套件中，并加入你要求的、更严格的所有权验证。

## test: 为 sync 工作流创建集成测试并验证 owner_id 完整性

### 用户需求
你需要一个 `pytest` 集成测试，用于自动化地验证 `quipu sync` 的完整工作流。这个测试必须严格检查在多用户协作场景下，数据补水器 (`Hydrator`) 是否为 SQLite 缓存中的**每一个**历史节点都正确地分配了 `owner_id`，以防止之前修复的 Bug 再次出现。

### 评论
将手动验证脚本转化为自动化测试是保证软件质量的关键一步。这个新的集成测试将成为 `sync` 功能的“守护者”，确保未来任何对相关代码的修改都不会破坏其核心的数据完整性。它将精确模拟真实协作流程，并执行比手动检查更严格的数据验证。

### 目标
1.  在 `tests/integration/test_sync_workflow.py` 文件中，添加一个新的、专门的测试用例 `test_owner_id_integrity_after_sync`。
2.  该测试将模拟用户 A 创建多个历史节点并推送。
3.  模拟用户 B 初始化、订阅用户 A 并拉取其历史。
4.  最关键的是，在测试的最后，连接到用户 B 的 SQLite 数据库，并逐一验证**所有**节点记录的 `owner_id` 是否与其真正的创建者匹配。

### 基本原理
我们将利用现有的 `sync_test_environment` pytest fixture 来搭建一个包含裸仓库和两个用户工作区的隔离环境。
1.  **生成历史**: 在两个用户的工作区中分别使用 `quipu run` 创建一系列 Quipu 节点。
2.  **执行同步**: 编排一系列 `quipu sync` 调用，模拟用户 A 推送、用户 B 订阅并拉取的完整流程。
3.  **收集证据**: 在同步完成后，分别从用户 A 和用户 B 的 Git 仓库中，通过 `git log` 提取出他们各自创建的 Quipu commit 哈希列表。
4.  **最终验证**: 连接到用户 B 的 `history.sqlite` 数据库，查询出所有 `(commit_hash, owner_id)` 的记录。然后，遍历这些记录，断言每一个 `commit_hash` 对应的 `owner_id` 都与其在**证据**列表中的归属完全一致。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #concept/sync #scope/core #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/build #task/state/begin

---

### Script

#### Acts 1: 增强集成测试文件

我们将使用 `patch_file` 来向现有的 `tests/integration/test_sync_workflow.py` 文件追加一个新的、更强大的测试用例。

~~~~~act
patch_file
tests/integration/test_sync_workflow.py
~~~~~
~~~~~python
        assert num_refs_after == num_refs_before - 1
        assert ref_to_delete.split("/")[-1] not in remote_refs_after
~~~~~
~~~~~python
        assert num_refs_after == num_refs_before - 1
        assert ref_to_delete.split("/")[-1] not in remote_refs_after

    def test_owner_id_integrity_after_sync(self, sync_test_environment):
        """
        A rigorous test to ensure every single node in the database has the correct
        owner_id after a multi-user sync, preventing data pollution.
        """
        _, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")
        user_b_id = get_user_id_from_email("user.b@example.com")

        # 1. User A creates a history of 2 nodes and pushes
        (user_a_path / "a1.md").write_text("~~~~~act\necho 'a1'\n~~~~~")
        (user_a_path / "a2.md").write_text("~~~~~act\necho 'a2'\n~~~~~")
        runner.invoke(app, ["run", str(user_a_path / "a1.md"), "--work-dir", str(user_a_path), "-y"])
        runner.invoke(app, ["run", str(user_a_path / "a2.md"), "--work-dir", str(user_a_path), "-y"])
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])

        # 2. User B creates 1 node and pushes
        (user_b_path / "b1.md").write_text("~~~~~act\necho 'b1'\n~~~~~")
        runner.invoke(app, ["run", str(user_b_path / "b1.md"), "--work-dir", str(user_b_path), "-y"])
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--remote", "origin"])

        # 3. User B subscribes to User A and fetches
        config_path_b = user_b_path / ".quipu" / "config.yml"
        with open(config_path_b, "r") as f:
            config_b = yaml.safe_load(f)
        config_b["sync"]["subscriptions"] = [user_a_id]
        with open(config_path_b, "w") as f:
            yaml.dump(config_b, f)
        
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--remote", "origin"])
        
        # 4. Trigger hydration in User B's workspace
        result = runner.invoke(app, ["cache", "sync", "--work-dir", str(user_b_path)])
        assert result.exit_code == 0

        # 5. --- THE CRITICAL VERIFICATION ---
        # Get ground truth: which commits belong to whom?
        quipu_log_cmd = ["log", "--all", "--grep=X-Quipu-Output-Tree", "--format=%H"]
        commits_a = set(run_git_command(user_a_path, quipu_log_cmd).splitlines())
        commits_b = set(run_git_command(user_b_path, quipu_log_cmd).splitlines())
        
        # We only care about commits created by user b specifically for this test
        user_b_only_commits = commits_b - commits_a
        
        assert len(commits_a) >= 2, "User A should have at least 2 Quipu commits"
        assert len(user_b_only_commits) >= 1, "User B should have at least 1 unique Quipu commit"

        # Check every single row in User B's database
        db_path_b = user_b_path / ".quipu" / "history.sqlite"
        assert db_path_b.exists()
        conn = sqlite3.connect(db_path_b)
        cursor = conn.cursor()
        cursor.execute("SELECT commit_hash, owner_id FROM nodes")
        all_nodes = cursor.fetchall()
        conn.close()

        assert len(all_nodes) == len(commits_a.union(user_b_only_commits))

        for commit_hash, owner_id in all_nodes:
            if commit_hash in commits_a:
                assert owner_id == user_a_id, f"Commit {commit_hash[:7]} from User A was wrongly owned by {owner_id}"
            elif commit_hash in user_b_only_commits:
                assert owner_id == user_b_id, f"Commit {commit_hash[:7]} from User B was wrongly owned by {owner_id}"
            else:
                pytest.fail(f"Unknown commit {commit_hash[:7]} found in the database.")
        
        print("\n✅ Verification successful: All nodes in the database have the correct owner_id.")
~~~~~

### 下一步建议
1.  **执行测试**:
    *   在你的项目根目录下，运行 `pytest` 命令，并指定新测试的文件路径：
        ```bash
        pytest tests/integration/test_sync_workflow.py
        ```
2.  **观察结果**: 测试应该会顺利通过。这个新的测试用例 `test_owner_id_integrity_after_sync` 将提供一个非常高的置信度，确保我们之前修复的 `Hydrator` Bug 不会再次出现。
3.  **提交测试**: 测试通过后，请将这个增强后的测试文件提交到版本库，为我们的 `sync` 功能提供持久的质量保障。
