分析正确。当前 Quipu 的解析器，特别是 `RegexBlockParser` 中用于识别代码块语言的正则表达式，无法正确处理 `python.old` 这种带有后缀的语言标识符。它只期望一个纯粹的单词作为语言类型。

### 错误分析

`packages/quipu-runtime/src/pyquipu/runtime/parser.py` 中的 `RegexBlockParser` 使用以下正则表达式来识别代码块的起始围栏及其语言类型：
`self.start_pattern = re.compile(rf"^({re.escape(fence_char)}{{3,}})(\w*)\s*$", re.MULTILINE)`

其中 `(\w*)` 部分负责捕获语言标识符。`\w*` 匹配的是零个或多个“词字符”（字母、数字、下划线），但它**不包含点号 `.`**。因此，当遇到 ````python.old```` 这样的语法时，它只会捕获 `python`，而忽略 `.old` 部分，导致 `python.old` 无法被作为一个完整的语言标识符识别，其内容也不会被正确解析和添加到 `contexts`。

### 用户需求

修改 Quipu 的解析器，使其能够正确识别 `python.old` 或 `python.new` 这种带有后缀的语言类型代码块。

### 评论

支持这种带有后缀的语言标识符，对于处理文件的不同版本（例如在 `patch_file` 操作中展示旧代码和新代码）非常有用。它能提高 AI 在生成计划时对代码块的描述能力和语义清晰度，从而提升人机协作的效率。

### 目标

1.  修改 `packages/quipu-runtime/src/pyquipu/runtime/parser.py` 中 `RegexBlockParser` 的 `start_pattern` 正则表达式，使其能够捕获 `lang.suffix` 格式的语言标识符。
2.  添加新的单元测试，验证 `BacktickParser` 和 `TildeParser` 都能正确解析这种新格式的代码块，并将其内容作为 `act` 语句的上下文进行存储。

### 基本原理

通过调整正则表达式中的语言捕获部分，将其从 `(\w*)` 扩展为 `(\w*(?:\.\w+)*)`。
*   `\w*`: 匹配基础语言部分（如 `python`）。
*   `(?: \. \w+ )*`: 这是一个非捕获组，允许零次或多次出现。
    *   `\.`: 匹配字面量点号。
    *   `\w+`: 匹配点号后的一位或多位词字符（如 `old`, `new`, `v2`）。

这个改变将确保整个 `python.old` 字符串被识别为 `lang`，其内容能够被正确提取。由于 `RegexBlockParser` 在处理非 `act` 块时，只是将其内容添加到当前语句的 `contexts` 列表中，所以这个修改不会影响现有的 `act` 处理逻辑，而是增强了对多种内容块类型的识别能力。

### 标签
#intent/refine #flow/ready #priority/high
#comp/runtime #comp/tests #concept/parser #scope/dx
#ai/instruct
#task/domain/runtime #task/object/parser #task/action/feature-extension #task/state/begin

---

### Script

#### Acts 1: 修改 `parser.py` 中的正则表达式

我们将修改 `packages/quipu-runtime/src/pyquipu/runtime/parser.py` 文件，更新 `RegexBlockParser` 中 `start_pattern` 的正则表达式。

~~~~~act
patch_file
packages/quipu-runtime/src/pyquipu/runtime/parser.py
~~~~~
~~~~~python
        self.start_pattern = re.compile(rf"^({re.escape(fence_char)}{{3,}})(\w*)\s*$", re.MULTILINE)
~~~~~
~~~~~python
        self.start_pattern = re.compile(rf"^({re.escape(fence_char)}{{3,}})(\w*(?:\.\w+)*)\s*$", re.MULTILINE)
~~~~~

#### Acts 2: 添加新的解析器测试用例

我们将在 `tests/runtime/test_parser_and_basic_acts.py` 中添加一个新的测试方法，以验证 `BacktickParser` 和 `TildeParser` 都能正确处理带有后缀的语言标识符。

~~~~~act
patch_file
tests/runtime/test_parser_and_basic_acts.py
~~~~~
~~~~~python
        assert f.read_text(encoding="utf-8") == "Line 1\nLine 2"

    def test_append_fail_not_found(self, executor: Executor):
        append_func, _, _ = executor._acts["append_file"]
        ctx = ActContext(executor)

        with pytest.raises(ExecutionError, match="acts.basic.error.fileNotFound"):
            append_func(ctx, ["ghost.txt", "content"])


class TestHybridArgs:
    # These tests use executor.execute(), which correctly creates the context,
    # so they don't need changes.
    def test_inline_write_file(self, executor: Executor, isolated_vault: Path):
        stmts = [{"act": "write_file inline.txt", "contexts": ["Inline Content"]}]
        executor.execute(stmts)
        f = isolated_vault / "inline.txt"
        assert f.read_text(encoding="utf-8") == "Inline Content"

    def test_inline_quoted_args(self, executor: Executor, isolated_vault: Path):
        stmts = [{"act": 'write_file "name with spaces.txt"', "contexts": ["Hello"]}]
        executor.execute(stmts)
        f = isolated_vault / "name with spaces.txt"
        assert f.exists()

    def test_mixed_git_commit(self, executor: Executor):
        called_args = []

        def mock_commit(ctx, args):
            called_args.extend(args)

        executor.register("mock_commit", mock_commit)
        stmts = [{"act": 'mock_commit -m "fix bug"', "contexts": []}]
        executor.execute(stmts)
        assert called_args == ["-m", "fix bug"]

    def test_act_parsing_error(self, executor: Executor):
        stmts = [{"act": 'write_file "unclosed string', "contexts": []}]
        with pytest.raises(ExecutionError) as exc:
            executor.execute(stmts)
        assert "Error parsing Act command line" in str(exc.value)
~~~~~
~~~~~python
        assert f.read_text(encoding="utf-8") == "Line 1\nLine 2"

    def test_append_fail_not_found(self, executor: Executor):
        append_func, _, _ = executor._acts["append_file"]
        ctx = ActContext(executor)

        with pytest.raises(ExecutionError, match="acts.basic.error.fileNotFound"):
            append_func(ctx, ["ghost.txt", "content"])

    def test_variable_lang_parser_recognition(self):
        """测试解析器能够识别并捕获 python.old 或 python.new 等后缀语言块的内容"""
        md_backtick_with_act = """
```act
my_test_act
```
```python.old
old_code_content_here
```
```python.new
new_code_content_here
```
"""
        parser_backtick = BacktickParser()
        stmts_backtick = parser_backtick.parse(md_backtick_with_act)
        assert len(stmts_backtick) == 1
        assert stmts_backtick[0]["act"] == "my_test_act"
        assert len(stmts_backtick[0]["contexts"]) == 2
        assert stmts_backtick[0]["contexts"][0].strip() == "old_code_content_here"
        assert stmts_backtick[0]["contexts"][1].strip() == "new_code_content_here"

        md_tilde_with_act = """
~~~act
another_test_act
~~~
~~~javascript.old
console.log("old");
~~~
~~~javascript.new
console.log("new");
~~~
"""
        parser_tilde = TildeParser()
        stmts_tilde = parser_tilde.parse(md_tilde_with_act)
        assert len(stmts_tilde) == 1
        assert stmts_tilde[0]["act"] == "another_test_act"
        assert len(stmts_tilde[0]["contexts"]) == 2
        assert stmts_tilde[0]["contexts"][0].strip() == 'console.log("old");'
        assert stmts_tilde[0]["contexts"][1].strip() == 'console.log("new");'


class TestHybridArgs:
    # These tests use executor.execute(), which correctly creates the context,
    # so they don't need changes.
    def test_inline_write_file(self, executor: Executor, isolated_vault: Path):
        stmts = [{"act": "write_file inline.txt", "contexts": ["Inline Content"]}]
        executor.execute(stmts)
        f = isolated_vault / "inline.txt"
        assert f.read_text(encoding="utf-8") == "Inline Content"

    def test_inline_quoted_args(self, executor: Executor, isolated_vault: Path):
        stmts = [{"act": 'write_file "name with spaces.txt"', "contexts": ["Hello"]}]
        executor.execute(stmts)
        f = isolated_vault / "name with spaces.txt"
        assert f.exists()

    def test_mixed_git_commit(self, executor: Executor):
        called_args = []

        def mock_commit(ctx, args):
            called_args.extend(args)

        executor.register("mock_commit", mock_commit)
        stmts = [{"act": 'mock_commit -m "fix bug"', "contexts": []}]
        executor.execute(stmts)
        assert called_args == ["-m", "fix bug"]

    def test_act_parsing_error(self, executor: Executor):
        stmts = [{"act": 'write_file "unclosed string', "contexts": []}]
        with pytest.raises(ExecutionError) as exc:
            executor.execute(stmts)
        assert "Error parsing Act command line" in str(exc.value)
~~~~~

### 下一步建议

执行所有测试以确保修改没有引入回归问题，特别是验证 `tests/runtime/test_parser_and_basic_acts.py` 中新添加的 `test_variable_lang_parser_recognition` 测试通过。

```bash
pytest tests/runtime/test_parser_and_basic_acts.py
```
