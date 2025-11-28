好的。现在将本次会话中的所有成功修复整合为一次 Git 提交。

### 提交信息

**标题**: `fix(tests): 修复 Sync 集成测试的路径引用和配置问题`

**正文**:
本次提交修复了 `test_sync_workflow.py` 中存在的两个核心问题，确保了 Sync 功能集成测试的稳定性和正确性：

1.  **修复文件路径引用**: 在 `CliRunner` 调用 `quipu run` 时，将相对文件名（如 `"plan.md"`）修改为绝对路径。此问题导致测试无法找到计划文件，引发了级联故障。
2.  **显式启用 SQLite 模式**: 在 `test_collaboration_subscribe_and_fetch` 测试中，为 User B 的配置文件增加了 `storage: {type: sqlite}`。这确保了在测试数据补水（Hydration）功能时，SQLite 数据库能够被正确创建和验证。

通过这些修复，Sync 功能的 Onboarding、Push、Fetch、Pruning 和多用户数据聚合流程现在都得到了有效的自动化测试覆盖。

---

### Script

#### Acts 1: 将所有变更添加到暂存区

~~~~~act
git_add
tests/integration/test_sync_workflow.py
~~~~~

#### Acts 2: 执行 Git 提交

~~~~~act
git_commit
~~~~~
~~~~~
fix(tests): 修复 Sync 集成测试的路径引用和配置问题

本次提交修复了 `test_sync_workflow.py` 中存在的两个核心问题，确保了 Sync 功能集成测试的稳定性和正确性：

1.  **修复文件路径引用**: 在 `CliRunner` 调用 `quipu run` 时，将相对文件名（如 `"plan.md"`）修改为绝对路径。此问题导致测试无法找到计划文件，引发了级联故障。
2.  **显式启用 SQLite 模式**: 在 `test_collaboration_subscribe_and_fetch` 测试中，为 User B 的配置文件增加了 `storage: {type: sqlite}`。这确保了在测试数据补水（Hydration）功能时，SQLite 数据库能够被正确创建和验证。

通过这些修复，Sync 功能的 Onboarding、Push、Fetch、Pruning 和多用户数据聚合流程现在都得到了有效的自动化测试覆盖。
~~~~~
