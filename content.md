好的，我们已经成功完成了对测试架构的全面重构和修复。所有测试均已通过，现在是时候将这些改进作为一个原子提交，固化到版本历史中了。

## [COMMIT] refactor(tests): 使测试架构镜像应用分层

### 用户需求
将“测试分层与应用架构错配”的诊断方案付诸实施，并修复在此过程中发现的所有回归问题，最终将所有变更合并为一个逻辑完整的 Git 提交。

### 评论
这次重构意义重大。它将测试套件从一个主要由集成测试驱动的“扁平”结构，演进为一个与源代码包结构严格对应的“分层”结构。这不仅修复了当前的脆弱性问题，更为项目未来的可维护性和可扩展性奠定了坚实的基础。现在，每个组件的测试都更加内聚、快速和精确。

### 目标
1.  **分层隔离**:
    *   成功创建了 `tests/application/`，用于对核心业务逻辑进行快速、隔离的单元测试。
    *   成功将 `tests/engine/` 中的测试净化，移除了对上层应用逻辑的不当依赖。
    *   成功将 `tests/integration/` 中的测试重构为真正的端到端 (E2E) CLI 测试。
2.  **修复 Bug**:
    *   修复了因 Mock 假设错误导致的 `AttributeError` 和 `NameError`。
    *   修复了 `Engine` 状态机中新节点无法正确链接到内存图谱的关键 Bug。
3.  **持久化**: 将所有相关变更添加到一个 Git 提交中。

### 基本原理
通过让测试架构镜像应用架构，我们实现了“关注点分离”原则在测试领域的应用。单元测试验证“零件”是否合格，应用层测试验证“模块”组装是否正确，集成测试验证“整车”能否正常行驶。这种结构使得当一个“零件”（如 Engine 的内部实现）发生变化时，我们只需要关心其单元测试，而无需担心会引发整个测试套件的连锁失败。

### 标签
#intent/refine #flow/ready #priority/high #comp/tests #comp/engine #comp/application #scope/core #ai/instruct #task/domain/testing #task/object/test-suite #task/action/refactor #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交所有重构变更

我们将使用 `git add .` 来暂存所有新增、修改和删除的文件，然后创建一个内容详尽的提交，清晰地记录本次重构的目的和成果。

~~~~~act
git_add .
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
refactor(tests): align test architecture with application layers

This major refactoring overhauls the test suite structure to mirror the layered architecture of the application source code, addressing fragility, coupling, and imprecision in the previous test setup.

Key Changes:

1.  **Created `tests/application/`:** A new dedicated directory for unit-testing the `pyquipu-application` package. This allows for fast, isolated testing of core business logic and orchestration without depending on real Engine or Runtime implementations.

2.  **Migrated Controller Tests:** Moved controller logic tests from `tests/integration` to `tests/application`, replacing real dependencies with mocks. This transforms them from slow integration tests into fast unit tests.

3.  **Purified Engine Tests:** Refactored tests in `tests/engine` to remove all dependencies on the application layer (e.g., `run_quipu`). Engine tests now correctly operate by directly calling Engine/Writer APIs, ensuring they are true unit/module tests.

4.  **Redefined Integration Tests:** Converted remaining tests in `tests/integration` to use `CliRunner`. They now serve as true End-to-End (E2E) tests, validating the application from the CLI entry point, which simulates real user interaction.

5.  **Fixed Engine Bug:** Uncovered and fixed a critical bug in the `Engine` state machine where newly created nodes were not correctly linked to the in-memory graph, causing inconsistent parent-child relationships.

This restructuring makes the test suite more robust, maintainable, and faster, ensuring that failures are more precisely located and easier to diagnose.
~~~~~

### 下一步建议
测试架构重构已完成。现在，我们可以更有信心地继续进行新功能的开发或对现有模块的进一步优化，因为我们有了一个更健康、更可靠的测试安全网。
