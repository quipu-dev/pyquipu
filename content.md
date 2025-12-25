你完全正确，我的疏忽导致了这个错误。非常抱歉！

这个 `ImportError` 是我一手造成的。我在更新 `conftest.py` 时犯了一个根本性的错误：我试图为一个*测试文件* (`test_patch_ambiguity.py`) 创建一个模块路径补丁 (`pyquipu.acts.test_patch_ambiguity`)。

测试文件是用来*调用*和*测试*你的应用代码的，它本身并不属于 `pyquipu.acts` 这个包。因此，Python 找不到这个模块，因为它根本就不存在于那个命名空间里。真正需要被 mock 的 `bus` 位于 `pyquipu.acts.basic` 模块中，而这个路径已经在 `patch_targets` 列表里了。我添加的那一行是多余且错误的。

我将立即生成一个计划来修正这个问题。

## [WIP] fix: 修复 conftest.py 中错误的 bus 补丁路径

### 错误分析
根本原因是在 `tests/runtime/conftest.py` 文件中，为 `mock_runtime_bus` 的 `patch_targets` 列表增加了一个不存在的模块路径 `pyquipu.acts.test_patch_ambiguity.bus`。测试文件 `test_patch_ambiguity.py` 是测试代码，不属于 `pyquipu` 应用包的一部分，因此 Python 无法将其作为模块导入，导致 `ImportError`。`_patch_file` 函数实际使用的 `bus` 实例位于 `pyquipu.acts.basic` 模块，该模块已经被正确地 patch 了，因此无需任何额外配置。

### 用户需求
修正上一计划引入的 `ImportError`，以便新创建的测试用例能够正常运行（并按预期失败）。

### 评论
这是一个典型的路径配置错误，它完全阻塞了我们的 TDD 流程。修正这个低级错误是继续进行功能修复的前提。感谢你捕捉到这个问题。

### 目标
1.  从 `tests/runtime/conftest.py` 中的 `patch_targets` 列表中移除错误的 `pyquipu.acts.test_patch_ambiguity.bus` 条目。

### 基本原理
通过移除这个无效的补丁目标，`monkeypatch` 将不再尝试加载一个不存在的模块。这将解决 `ImportError`，使 `pytest` 能够成功加载并执行测试文件。执行后，我们应该能看到由业务逻辑缺陷（而不是配置错误）引起的预期测试失败。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #concept/config #scope/dx #ai/instruct #task/domain/testing #task/object/patch-ambiguity #task/action/bug-reproduction #task/state/continue

---
### Script

#### Acts 1: 移除 conftest.py 中的错误路径

我们将精确地移除导致 `ImportError` 的那一行。

~~~~~act
patch_file
tests/runtime/conftest.py
~~~~~
~~~~~python
    patch_targets = [
        "pyquipu.runtime.executor.bus",
        "pyquipu.runtime.plugin_loader.bus",
        "pyquipu.acts.basic.bus",
        "pyquipu.acts.check.bus",
        "pyquipu.acts.git.bus",
        "pyquipu.acts.memory.bus",
        "pyquipu.acts.read.bus",
        "pyquipu.acts.refactor.bus",
        "pyquipu.acts.shell.bus",
        # 新增对模糊性测试模块的 bus patch
        "pyquipu.acts.test_patch_ambiguity.bus",
    ]
~~~~~
~~~~~python
    patch_targets = [
        "pyquipu.runtime.executor.bus",
        "pyquipu.runtime.plugin_loader.bus",
        "pyquipu.acts.basic.bus",
        "pyquipu.acts.check.bus",
        "pyquipu.acts.git.bus",
        "pyquipu.acts.memory.bus",
        "pyquipu.acts.read.bus",
        "pyquipu.acts.refactor.bus",
        "pyquipu.acts.shell.bus",
    ]
~~~~~

### 下一步建议
请执行此计划。完成后，请再次运行测试：`pytest tests/runtime/acts/test_patch_ambiguity.py`。

这一次，`ImportError` 应该会消失。取而代之的是，你将看到 `test_patch_file_should_fail_on_ambiguous_content` 测试失败，因为它没有按预期抛出 `ExecutionError`。这将确认我们的 TDD "红灯" 已经正确建立，然后我们就可以进入 "绿灯" 阶段——修复 `patch_file` 的核心逻辑。
