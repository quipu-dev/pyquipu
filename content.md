好的，我们已经成功修复了集成测试，并通过了验证。现在，我们将把这些成果固化为一个原子性的提交。

## [COMMIT] test(integration): 修正 MessageBus 重构后失效的集成测试

### 用户需求
修复 `tests/integration/test_cli_workflow.py` 中所有因 `MessageBus` 重构而失败的测试。关键要求是，更新后的测试应避免对硬编码的、本地化的错误字符串进行断言，转而验证更稳定的语义信息，如消息 ID 和异常类型。

### 评论
这次提交是 `MessageBus` 重构工作的一个重要收尾环节。它不仅恢复了测试套件的健康状态，更重要的是，它为项目建立了一套更健壮的测试模式：控制器层的测试验证业务逻辑的契约（`QuipuResult` 对象），而 CLI 层的测试验证最终的用户输出。这种分离使得测试对 UI 文本的变化更具弹性。

### 目标
1.  已在 `locales/zh/cli.json` 中补全缺失的 `common.error.fileNotFound` 等消息条目。
2.  已更新 `test_run_quipu_execution_error`，使其断言正确的异常类型和消息 ID，并检查错误消息中包含的动态上下文，而不是硬编码的字符串。
3.  已更新 `test_run_quipu_empty_plan`，使其断言正确的成功状态 (`success=True`) 和消息 ID。
4.  已确保 `test_cli_workflow.py` 中的所有测试全部通过。
5.  创建一个 Git 提交，将此项改进持久化。

### 基本原理
我们遵循关注点分离的原则来修复测试。控制器层的测试被修改为直接验证其公共 API 的输出——即 `QuipuResult` 对象的内容，包括其中封装的异常对象和消息 ID。这使得测试与 UI 表示层完全解耦。对于 CLI 层的测试，其失败的根本原因是资源文件缺失，通过补全 `cli.json` 中的消息模板即可修复。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/testing #task/object/message-bus #task/action/refactor #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交变更

现在，我们将所有相关的修改添加到 Git 暂存区，并创建一个内容详尽的提交。

`````````act
git_add
locales/zh/cli.json
tests/integration/test_cli_workflow.py
`````````

`````````act
git_commit
`````````
`````````text
test(integration): fix tests broken by MessageBus refactor

Aligns integration tests in `test_cli_workflow.py` with the new MessageBus architecture, resolving failures and improving robustness.

Key changes:
- **Controller Test Fix**: The controller-level tests (`TestController`) are updated to assert on the semantic content of the `QuipuResult` object (e.g., message ID, exception type, context in `msg_kwargs`) rather than on hardcoded, localized UI strings. This makes the tests more resilient to changes in wording.
- **Resource Fix**: Adds missing message IDs (`common.error.fileNotFound`, etc.) to `locales/zh/cli.json` to fix a failure in the CLI-level test `test_cli_run_file_not_found`.
- **Logic Fix**: Corrects the assertion in `test_run_quipu_empty_plan` to expect `success=True`, as an empty plan is a harmless, successful operation.

This commit completes the necessary test adjustments following the MessageBus refactoring, ensuring the test suite is stable and follows best practices.
`````````

### 下一步建议
我们已经完成了 `MessageBus` 迁移的核心工作和相关的测试修复。现在，整个系统的输出路径更加统一和健壮。

下一步，我们可以将注意力转向 `quipu-runtime` 模块，将所有 `acts` 中的用户反馈（例如 `✅ [写入] ...`）也迁移到 `MessageBus` 系统中，以完成整个重构计划。
