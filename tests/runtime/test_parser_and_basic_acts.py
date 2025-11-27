import pytest
from pathlib import Path
from quipu.core.parser import BacktickParser, TildeParser, get_parser
from quipu.core.executor import Executor, ExecutionError
from quipu.core.types import ActContext


class TestParser:
    # ... (Parser tests are unchanged)
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

        with pytest.raises(ExecutionError) as excinfo:
            patch_file_func(ctx, ["wrong.txt", "BBB", "CCC"])

        assert "未找到指定的旧文本" in str(excinfo.value)

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

        with pytest.raises(ExecutionError) as excinfo:
            append_func(ctx, ["ghost.txt", "content"])

        assert "文件不存在" in str(excinfo.value)


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
