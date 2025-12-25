Excellent. We have successfully established the "Red" state of our TDD cycle. The failing test confirms the bug's existence and gives us a clear target.

Now, we move to the "Green" state. I will generate a plan to modify the `patch_file` implementation to perform a uniqueness check. Simultaneously, I will update the test suite to reflect this new, correct behavior, ensuring our tests accurately describe a robust system.

## [WIP] fix: Ensure patch_file fails on ambiguous content

### 错误分析
当前 `_patch_file` 的实现盲目地使用 `content.replace(old_str, new_str, 1)`，这总是替换第一个出现的匹配项，而没有检查文件中是否存在多个相同的 `old_str` 实例。这违反了补丁操作应有的确定性和安全性原则，可能导致在非预期位置进行修改。

### 用户需求
修改 `patch_file` 的核心逻辑，使其在执行替换前，必须验证 `old_str` 在目标文件中的匹配项是否**唯一**。如果匹配项为零或多于一个，操作必须失败并报告错误，而不是进行不确定的修改。

### 评论
这是一个关键的健壮性修复。强制要求补丁的唯一性可以从根本上消除一整类难以察觉的、危险的 bug。这使得 `patch_file` 成为一个更可靠、更值得信赖的自动化工具，完全符合 `d3-principle-quipu-patch-strategy-D3-P1` 的精神。

### 目标
1.  修改 `packages/quipu-runtime/src/pyquipu/acts/basic.py` 中的 `_patch_file` 函数。在新逻辑中，使用 `string.count()` 方法检查 `old_str` 的出现次数。如果计数不为 `1`，则通过 `ctx.fail` 抛出相应的错误。
2.  修改 `tests/runtime/acts/test_patch_ambiguity.py` 中先前用于暴露错误行为的测试用例。将其从一个验证“修改第一个匹配项”的测试，重构为一个验证“在内容不唯一时抛出异常”的测试，使其与我们的新逻辑保持一致。

### 基本原理
我们将采用“先检查，后执行”的策略。在 `_patch_file` 函数中，通过 `content.count(old_str)` 获取匹配数。
-   如果 `count == 0`，抛出 `patchContentMismatch` 错误。
-   如果 `count > 1`，抛出新的 `patchContentAmbiguous` 错误。
-   只有当 `count == 1` 时，才执行 `content.replace()` 操作。

相应的，我们重构测试用例 `test_patch_file_modifies_first_occurrence_on_ambiguous_content`，将其重命名并修改其断言逻辑，以确保它能正确测试这种多行文本下的模糊匹配失败场景。

### 标签
#intent/fix #flow/ready #priority/high #comp/runtime #comp/tests #concept/executor #scope/core #ai/instruct #task/domain/testing #task/object/patch-ambiguity #task/action/implementation #task/state/continue

---
### Script

#### Acts 1: 增强 `_patch_file` 的唯一性检查

我们将在 `basic.py` 中加入 `content.count()` 逻辑，以确保补丁的唯一性。

~~~~~act
patch_file
packages/quipu-runtime/src/pyquipu/acts/basic.py
~~~~~
~~~~~python
    if old_str not in content:
        ctx.fail(bus.get("acts.basic.error.patchContentMismatch", path=raw_path))

    new_content = content.replace(old_str, new_str, 1)
~~~~~
~~~~~python
    match_count = content.count(old_str)
    if match_count == 0:
        ctx.fail(bus.get("acts.basic.error.patchContentMismatch", path=raw_path))
    elif match_count > 1:
        ctx.fail(bus.get("acts.basic.error.patchContentAmbiguous", path=raw_path, count=match_count))

    new_content = content.replace(old_str, new_str, 1)
~~~~~

#### Acts 2: 更新测试用例以匹配新行为

现在，我们将修正 `test_patch_ambiguity.py` 中的测试，使其正确地期望在内容模糊时操作失败。

~~~~~act
patch_file
tests/runtime/acts/test_patch_ambiguity.py
~~~~~
~~~~~python
class TestPatchAmbiguity:
    def test_patch_file_modifies_first_occurrence_on_ambiguous_content(self, executor: Executor, isolated_vault):
        """
        这个测试验证了当前 patch_file 的错误行为。
        当存在重复内容时，它总是修改第一个，这可能不是用户的意图。
        这个测试在当前实现下会通过，但它暴露了逻辑缺陷。
        后续的修复会让这个测试失败，并代之以一个检查唯一性的新测试。
        """
        content = """
def function_a():
    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")

def function_b():
    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")
"""
        target_file = isolated_vault / "source.py"
        target_file.write_text(content)

        old_str = """    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")"""

        new_str = """    # This block has been modified.
    # The anchor is now different.
    print("world")"""

        # 执行 patch
        patch_func, _, _ = executor._acts["patch_file"]
        ctx = ActContext(executor)
        patch_func(ctx, [str(target_file), old_str, new_str])

        # 读取修改后的内容
        final_content = target_file.read_text()

        # 预期（错误）结果：第一个函数被修改，第二个不变
        expected_wrong_content = """
def function_a():
    # This block has been modified.
    # The anchor is now different.
    print("world")

def function_b():
    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")
"""
        assert final_content.strip() == expected_wrong_content.strip()

    def test_patch_file_should_fail_on_ambiguous_content(self, executor: Executor, isolated_vault):
~~~~~
~~~~~python
class TestPatchAmbiguity:
    def test_patch_file_fails_on_ambiguous_multiline_content(self, executor: Executor, isolated_vault):
        """
        验证当一个多行的 `old_str` 在文件中有多个匹配时，操作会失败。
        """
        content = """
def function_a():
    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")

def function_b():
    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")
"""
        target_file = isolated_vault / "source.py"
        target_file.write_text(content)

        old_str = """    # This is a unique block of text.
    # It serves as an anchor.
    print("hello")"""

        new_str = """    # This block has been modified."""

        with pytest.raises(ExecutionError, match="acts.basic.error.patchContentAmbiguous"):
            patch_func, _, _ = executor._acts["patch_file"]
            ctx = ActContext(executor)
            patch_func(ctx, [str(target_file), old_str, new_str])

        # 验证文件未被修改
        assert target_file.read_text() == content

    def test_patch_file_should_fail_on_ambiguous_content(self, executor: Executor, isolated_vault):
~~~~~

### 下一步建议
请执行此计划。完成后，请再次运行测试：`pytest tests/runtime/acts/test_patch_ambiguity.py`。

这一次，两个测试应该都会**通过**。这标志着我们已经成功地修复了 bug 并更新了测试以保证其长期稳定性。

之后，我将为你生成一个最终的 `[COMMIT]` 计划，用于将这些修改提交到版本控制中。
