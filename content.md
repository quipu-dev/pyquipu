# fix-test: 修复 `test_generate_summary` 中的断言错误

## 用户需求
`pytest` 执行 `tests/test_storage_writer.py` 时出现两个断言失败。需要分析失败原因并修复测试用例。

## 评论
经过对测试失败日志的分析，定位到两个问题，均源于测试用例中的期望值与 `_generate_summary` 函数的正确实现不符。

1.  **第一个失败 (用户消息处理)**: 测试用例错误地期望在有文件变更的情况下，`capture` 节点的 `message` 参数会被忽略。而根据规范和实现，用户提供的 `message` 应该被预置在自动生成的摘要之前。
2.  **第二个失败 (文件列表截断)**: 测试用例期望在有 3 个文件变更时触发摘要截断逻辑，但实现（和规范）是在文件数**大于** 3 时才进行截断。此外，测试提供的 mock 数据只有 3 个文件，无法有效测试截断分支。

解决方案是修正测试用例，使其准确反映 `_generate_summary` 方法的预期行为。我们将调整一个测试用例的期望输出，并重构另一个，以清晰地分离对“完整列表”和“截断列表”两种场景的验证。

## 目标
1.  修正 `test_generate_summary` 中关于 `capture` 节点用户消息的测试用例，使其期望输出与实现逻辑一致。
2.  重构 `capture` 节点文件变更摘要的测试用例，创建一个新的测试场景以验证文件数小于等于 3 的情况，并修改现有场景以验证文件数大于 3 时的截断逻辑。

## 基本原理
测试用例是代码行为的“活文档”。当实现与测试不一致时，需要判断是实现错误还是测试用例错误。在此场景中，`GitObjectHistoryWriter` 的实现符合 `QDPS v1.0` 规范，因此问题出在测试用例上。通过修正测试用例，我们不仅能让测试通过，还能确保测试代码准确地描述和验证了我们期望的系统行为。

## 标签
#comp/tests #scope/dx

---

## Script

### Acts 1: 修正 `test_storage_writer.py` 中的测试用例

我们将修改 `test_generate_summary` 的 `parametrize` 数据，以纠正错误的期望值并增加一个新的测试场景，从而准确地验证所有逻辑分支。

~~~~~act
replace
~~~~~
~~~~~path
tests/test_storage_writer.py
~~~~~
~~~~~python
    @pytest.mark.parametrize(
        "node_type, content, kwargs, expected_summary",
        [
            ("plan", "# feat: Implement feature\nDetails here.", {}, "feat: Implement feature"),
            ("plan", "Just a simple plan content line.", {}, "Just a simple plan content line."),
            ("capture", "", {"message": "Initial capture"}, "Capture: No changes detected"),
            ("capture", "", {"message": "UI fix"}, "UI fix Capture: No changes detected"),
            ("capture", "", {}, "Capture: M file1.py, A file2.js ... and 1 more files"),
        ]
    )
    def test_generate_summary(self, node_type, content, kwargs, expected_summary):
        mock_git_db = MagicMock(spec=GitDB)
        mock_git_db.get_diff_name_status.return_value = [
            ("M", "path/to/file1.py"),
            ("A", "file2.js"),
            ("D", "old.css")
        ]
        
        if "No changes" in expected_summary:
            mock_git_db.get_diff_name_status.return_value = []

        writer = GitObjectHistoryWriter(mock_git_db)
        summary = writer._generate_summary(node_type, content, "hash_a", "hash_b", **kwargs)
        
        assert summary == expected_summary
~~~~~
~~~~~python
    @pytest.mark.parametrize(
        "node_type, content, kwargs, mock_changes, expected_summary",
        [
            # Plan a
            ("plan", "# feat: Implement feature\nDetails here.", {}, [], "feat: Implement feature"),
            ("plan", "Just a simple plan content line.", {}, [], "Just a simple plan content line."),
            # Capture with no changes
            ("capture", "", {"message": "Initial capture"}, [], "Initial capture Capture: No changes detected"),
            # Capture with changes (<= 3 files)
            ("capture", "", {}, [("M", "f1.py"), ("A", "f2.js")], "Capture: M f1.py, A f2.js"),
            # Capture with changes (> 3 files, should truncate)
            ("capture", "", {"message": "Big change"}, [("M", "f1.py"), ("A", "f2.js"), ("D", "f3.css"), ("A", "f4.html")], "Big change Capture: M f1.py, A f2.js, D f3.css ... and 1 more files"),
        ]
    )
    def test_generate_summary(self, node_type, content, kwargs, mock_changes, expected_summary):
        mock_git_db = MagicMock(spec=GitDB)
        mock_git_db.get_diff_name_status.return_value = mock_changes
        
        writer = GitObjectHistoryWriter(mock_git_db)
        summary = writer._generate_summary(node_type, content, "hash_a", "hash_b", **kwargs)
        
        assert summary == expected_summary
~~~~~