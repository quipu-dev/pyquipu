from pyquipu.runtime.parser import detect_best_parser, get_parser


class TestParserRobustness:
    def test_parse_complex_language_tags(self):
        """
        验证解析器能否处理包含特殊字符的语言标签。
        当前的 RegexBlockParser 会在 python-new 和 c++ 上失败。
        """
        text = """
```act
test_act
```
```python.old
print("dot")
```
```python-new
print("hyphen")
```
```c++
std::cout << "plus";
```
"""
        # 使用自动检测（应该是 tilde）
        parser_name = detect_best_parser(text)
        parser = get_parser(parser_name)
        stmts = parser.parse(text)

        assert len(stmts) == 1
        stmt = stmts[0]
        assert stmt["act"] == "test_act"

        # 验证是否捕获了所有上下文块
        # 如果 regex 失败，它会跳过无法匹配的头，导致上下文丢失
        assert len(stmt["contexts"]) == 3

        assert 'print("dot")' in stmt["contexts"][0]
        assert 'print("hyphen")' in stmt["contexts"][1]
        assert 'std::cout << "plus";' in stmt["contexts"][2]

    def test_parse_with_spaces_in_fence(self):
        """
        验证解析器能否处理围栏后的空格（CommonMark 标准允许）。
        例如: '~~~~~ python'
        """
        text = """
```act
test_act
```
``` python
print("space")
```
"""
        parser = get_parser("backtick")
        stmts = parser.parse(text)

        assert len(stmts) == 1
        assert len(stmts[0]["contexts"]) == 1
        assert 'print("space")' in stmts[0]["contexts"][0]

    def test_unclosed_block_handling(self):
        """
        验证未闭合的块是否被安全处理（例如忽略或报错，但不应崩溃）。
        """
        text = """
```act
valid
```
```unclosed
starts but never ends...
"""
        parser = get_parser("backtick")
        stmts = parser.parse(text)

        # 解析器应该能提取出第一个有效的 act
        assert len(stmts) == 1
        assert stmts[0]["act"] == "valid"
        # unclosed block 应该被忽略，或者至少不应该导致之前的 act 丢失
