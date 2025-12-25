很抱歉，这是我的失误。解析器的逻辑其实已经修复了，但是我在编写**测试用例**时犯了低级错误：测试文本使用的是反引号（```），但我却硬编码让它使用波浪号解析器（`tilde`），导致解析器完全忽略了这些块。

这就是为什么 `test_parse_complex_language_tags` 通过了（因为它使用了 `detect_best_parser` 自动检测），而后面两个手动指定解析器的测试却失败了。

我将立即修正测试用例中的这一不一致。

## [WIP] fix: 修正测试用例中的解析器类型不匹配

### 错误分析
在 `tests/runtime/test_parser_robustness.py` 中：
1.  `test_parse_with_spaces_in_fence`: 文本使用 ` ``` `，但代码调用 `get_parser("tilde")`。
2.  `test_unclosed_block_handling`: 文本使用 ` ``` `，但代码调用 `get_parser("tilde")`。

这导致 `TildeParser` 扫描文本时找不到任何 `~~~` 开头的块，因此返回空列表，触发断言失败。

### 用户需求
修正测试代码，使其使用的解析器与测试文本中的围栏符号一致。

### 评论
这是一个典型的“测试代码本身的 Bug”。修正后，我们可以验证新解析器的真实能力。

### 目标
修改 `tests/runtime/test_parser_robustness.py`，将硬编码的 `get_parser("tilde")` 改为 `get_parser("backtick")`，或者将测试文本改为使用 `~~~`。为了保持一致性，我将把解析器调用改为 `backtick`。

### 基本原理
匹配测试数据与测试逻辑。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #concept/parser #scope/core #ai/instruct #task/domain/testing #task/object/test-case-fix #task/action/correction #task/state/continue

---
### Script

#### Acts 1: 修正测试文件

~~~~~act
patch_file
tests/runtime/test_parser_robustness.py
~~~~~
~~~~~python
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
        parser = get_parser("tilde")
        stmts = parser.parse(text)
        
        assert len(stmts) == 1
~~~~~
~~~~~python
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
~~~~~

~~~~~act
patch_file
tests/runtime/test_parser_robustness.py
~~~~~
~~~~~python
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
        parser = get_parser("tilde")
        stmts = parser.parse(text)
        
        # 解析器应该能提取出第一个有效的 act
~~~~~
~~~~~python
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
~~~~~

### 下一步建议
请执行此计划。
然后运行全量测试：`pytest tests/runtime/test_parser_robustness.py tests/runtime/acts/test_patch_ambiguity.py`。
这一次，所有测试都应该通过。
