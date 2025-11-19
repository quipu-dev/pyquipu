import pytest
from pathlib import Path
from core.parser import MarkdownParser
from core.executor import Executor, ExecutionError

class TestParser:
    def test_parse_simple_flow(self):
        md = """
Instruction text...
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
        parser = MarkdownParser()
        stmts = parser.parse(md)
        
        assert len(stmts) == 1
        assert stmts[0]['act'] == 'write_file'
        # parser 会保留 block 中的换行符，这里用 strip 验证核心内容
        assert stmts[0]['contexts'][0].strip() == 'test.txt'
        assert stmts[0]['contexts'][1].strip() == 'hello'

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
