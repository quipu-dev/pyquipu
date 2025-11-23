import pytest
from pathlib import Path
from core.parser import BacktickParser, TildeParser, get_parser
from core.executor import Executor, ExecutionError

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
        assert stmts[0]['act'] == 'write_file'
        assert stmts[0]['contexts'][0].strip() == 'test.txt'

    def test_end_block(self):
        """测试 end 块能正确终止语句"""
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
        
        # 应该有三个语句 (中间的 end 也是一个独立的 act)
        assert len(stmts) == 3
        
        # 第一个语句 (op1) 应该只有一个参数，arg2 应该被 "end" 语句吸走
        assert stmts[0]['act'] == 'op1'
        assert len(stmts[0]['contexts']) == 1
        assert stmts[0]['contexts'][0].strip() == 'val1'
        
        # 第三个语句 (op2) 正常
        assert stmts[2]['act'] == 'op2'
        assert stmts[2]['contexts'][0].strip() == 'val2'

    def test_tilde_parser(self):
        # 测试蓝幕模式：当内容中包含反引号时，外部使用波浪号
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
        assert stmts[0]['act'] == 'write_file'
        
        # 验证内部的反引号是否被完整保留
        content = stmts[0]['contexts'][1]
        assert '```python' in content
        assert 'print("hello")' in content
        assert '```' in content

    def test_factory(self):
        assert isinstance(get_parser("backtick"), BacktickParser)
        assert isinstance(get_parser("tilde"), TildeParser)
        with pytest.raises(ValueError):
            get_parser("unknown")

class TestBasicActs:
    def test_write_file(self, executor: Executor, isolated_vault: Path):
        # 模拟解析后的数据
        contexts = ["docs/readme.md", "# Hello"]
        
        # 直接调用注册在 executor 中的函数逻辑
        write_func, _ = executor._acts['write_file']
        write_func(executor, contexts)
        
        expected_file = isolated_vault / "docs/readme.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding='utf-8') == "# Hello"

    def test_replace_text(self, executor: Executor, isolated_vault: Path):
        # 先写入一个文件
        f = isolated_vault / "main.py"
        f.write_text('print("Hello World")', encoding='utf-8')
        
        replace_func, _ = executor._acts['replace']
        replace_func(executor, ["main.py", 'print("Hello World")', 'print("Hello AI")'])
        
        assert f.read_text(encoding='utf-8') == 'print("Hello AI")'

    def test_replace_fail_not_found(self, executor: Executor, isolated_vault: Path):
        f = isolated_vault / "wrong.txt"
        f.write_text("AAA", encoding='utf-8')
        
        replace_func, _ = executor._acts['replace']
        
        with pytest.raises(ExecutionError) as excinfo:
            replace_func(executor, ["wrong.txt", "BBB", "CCC"])
        
        assert "未找到指定的旧文本" in str(excinfo.value)

    def test_append_file(self, executor: Executor, isolated_vault: Path):
        # 准备初始文件
        f = isolated_vault / "log.txt"
        f.write_text("Line 1\n", encoding='utf-8')
        
        # 执行追加
        # 注意：这里假设 _acts 字典中已经有了 'append_file'，
        # 这通常通过 conftest.py 中的 register_basic_acts 自动完成
        append_func, _ = executor._acts['append_file']
        append_func(executor, ["log.txt", "Line 2"])
        
        # 验证
        assert f.read_text(encoding='utf-8') == "Line 1\nLine 2"

    def test_append_fail_not_found(self, executor: Executor):
        append_func, _ = executor._acts['append_file']
        
        with pytest.raises(ExecutionError) as excinfo:
            append_func(executor, ["ghost.txt", "content"])
            
        assert "文件不存在" in str(excinfo.value)
class TestHybridArgs:
    """测试 Act 块内参数与 Context 块参数的混合使用"""
    
    def test_inline_write_file(self, executor: Executor, isolated_vault: Path):
        """测试 write_file path 在 act 块中"""
        # 模拟解析器结果：act="write_file inline.txt", contexts=["content"]
        # 我们不能直接测 parser -> executor 链路，因为 parser 不会改，
        # 重点是 executor.execute 如何处理这种 Statement 结构
        
        stmts = [{
            "act": "write_file inline.txt",
            "contexts": ["Inline Content"]
        }]
        
        executor.execute(stmts)
        
        f = isolated_vault / "inline.txt"
        assert f.read_text(encoding='utf-8') == "Inline Content"

    def test_inline_quoted_args(self, executor: Executor, isolated_vault: Path):
        """测试带引号的文件名"""
        stmts = [{
            "act": 'write_file "name with spaces.txt"',
            "contexts": ["Hello"]
        }]
        
        executor.execute(stmts)
        
        f = isolated_vault / "name with spaces.txt"
        assert f.exists()

    def test_mixed_git_commit(self, executor: Executor):
        """测试 git_commit -m message (纯 act 块)"""
        # 我们 mock 一下 git_commit，因为不想真的跑 git
        called_args = []
        def mock_commit(exc, args):
            called_args.extend(args)
            
        executor.register("mock_commit", mock_commit)
        
        stmts = [{
            "act": 'mock_commit -m "fix bug"',
            "contexts": []
        }]
        
        executor.execute(stmts)
        
        assert called_args == ["-m", "fix bug"]

    def test_act_parsing_error(self, executor: Executor):
        """测试引号未闭合的错误"""
        stmts = [{
            "act": 'write_file "unclosed string',
            "contexts": []
        }]
        
        with pytest.raises(ExecutionError) as exc:
            executor.execute(stmts)
        assert "Act 命令行解析错误" in str(exc.value)
