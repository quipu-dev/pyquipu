from pathlib import Path

import pytest
from pyquipu.interfaces.types import ActContext
from pyquipu.runtime.executor import ExecutionError, Executor
from pyquipu.runtime.parser import BacktickParser, TildeParser, get_parser


class TestParser:
    def test_backtick_parser(self):
        md = """
```act
write_file
```
```path
test.txt
```
```content
hello
```
"""
        parser = BacktickParser()
        stmts = parser.parse(md)
        assert len(stmts) == 1
        assert stmts[0]["act"] == "write_file"
        assert stmts[0]["contexts"][0].strip() == "test.txt"

    def test_end_block(self):
        md = """
```act
op1
```
```arg1
val1
```
```act
end
```
```arg2
ignored_val
```
```act
op2
```
```arg3
val2
```
"""
        parser = BacktickParser()
        stmts = parser.parse(md)
        assert len(stmts) == 3
        assert stmts[0]["act"] == "op1"
        assert len(stmts[0]["contexts"]) == 1
        assert stmts[0]["contexts"][0].strip() == "val1"
        assert stmts[2]["act"] == "op2"
        assert stmts[2]["contexts"][0].strip() == "val2"

    def test_tilde_parser(self):
        md = """
~~~act
write_file
~~~
~~~path
markdown_guide.md
~~~
~~~markdown
Here is how you write code:
```python
print("hello")
```
~~~
"""
        parser = TildeParser()
        stmts = parser.parse(md)
        assert len(stmts) == 1
        assert stmts[0]["act"] == "write_file"
        content = stmts[0]["contexts"][1]
        assert "```python" in content

    def test_factory(self):
        assert isinstance(get_parser("backtick"), BacktickParser)
        assert isinstance(get_parser("tilde"), TildeParser)
        with pytest.raises(ValueError):
            get_parser("unknown")


class TestBasicActs:
    def test_write_file(self, executor: Executor, isolated_vault: Path):
        contexts = ["docs/readme.md", "# Hello"]
        write_func, _, _ = executor._acts["write_file"]
        ctx = ActContext(executor)
        write_func(ctx, contexts)

        expected_file = isolated_vault / "docs/readme.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == "# Hello"

    def test_patch_file_text(self, executor: Executor, isolated_vault: Path):
        f = isolated_vault / "main.py"
        f.write_text('print("Hello World")', encoding="utf-8")

        patch_file_func, _, _ = executor._acts["patch_file"]
        ctx = ActContext(executor)
        patch_file_func(ctx, ["main.py", 'print("Hello World")', 'print("Hello AI")'])

        assert f.read_text(encoding="utf-8") == 'print("Hello AI")'

    def test_patch_file_fail_not_found(self, executor: Executor, isolated_vault: Path):
        f = isolated_vault / "wrong.txt"
        f.write_text("AAA", encoding="utf-8")

        patch_file_func, _, _ = executor._acts["patch_file"]
        ctx = ActContext(executor)

        with pytest.raises(ExecutionError, match="acts.basic.error.patchContentMismatch"):
            patch_file_func(ctx, ["wrong.txt", "BBB", "CCC"])

    def test_append_file(self, executor: Executor, isolated_vault: Path):
        f = isolated_vault / "log.txt"
        f.write_text("Line 1\n", encoding="utf-8")

        append_func, _, _ = executor._acts["append_file"]
        ctx = ActContext(executor)
        append_func(ctx, ["log.txt", "Line 2"])

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
