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
```end
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
        
        # 应该有两个语句
        assert len(stmts) == 2
        
        # 第一个语句应该只有一个参数，arg2 应该被忽略
        assert stmts[0]['act'] == 'op1'
        assert len(stmts[0]['contexts']) == 1
        assert stmts[0]['contexts'][0].strip() == 'val1'
        
        # 第二个语句正常
        assert stmts[1]['act'] == 'op2'
        assert stmts[1]['contexts'][0].strip() == 'val2'

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
        write_func = executor._acts['write_file']
        write_func(executor, contexts)
        
        expected_file = isolated_vault / "docs/readme.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding='utf-8') == "# Hello"

    def test_replace_text(self, executor: Executor, isolated_vault: Path):
        # 先写入一个文件
        f = isolated_vault / "main.py"
        f.write_text('print("Hello World")', encoding='utf-8')
        
        replace_func = executor._acts['replace']
        replace_func(executor, ["main.py", 'print("Hello World")', 'print("Hello AI")'])
        
        assert f.read_text(encoding='utf-8') == 'print("Hello AI")'

    def test_replace_fail_not_found(self, executor: Executor, isolated_vault: Path):
        f = isolated_vault / "wrong.txt"
        f.write_text("AAA", encoding='utf-8')
        
        replace_func = executor._acts['replace']
        
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
        append_func = executor._acts['append_file']
        append_func(executor, ["log.txt", "Line 2"])
        
        # 验证
        assert f.read_text(encoding='utf-8') == "Line 1\nLine 2"

    def test_append_fail_not_found(self, executor: Executor):
        append_func = executor._acts['append_file']
        
        with pytest.raises(ExecutionError) as excinfo:
            append_func(executor, ["ghost.txt", "content"])
            
        assert "文件不存在" in str(excinfo.value)
