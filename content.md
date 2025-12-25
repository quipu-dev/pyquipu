你的反馈非常有价值。这不仅仅是一个关于“点号”的问题，而是揭示了当前基于正则表达式的解析器 (`RegexBlockParser`) 的脆弱性。

问题分析

1.  **Pytest 警告**: `Unknown pytest.mark.timeout` 是因为缺少 `pytest-timeout` 插件或未注册该标记。这是一个配置噪音，容易修复。
2.  **解析器缺陷 (Root Cause)**:
    *   当前的正则 `(\w*(?:\.\w+)*)` 对语言标签的格式限制过死。
    *   它**不支持**带连字符的语言（如 `objective-c`, `python-old`）。
    *   它**不支持**带加号的语言（如 `c++`）。
    *   它**不支持**围栏后的空格（如 `~~~~~ python`）。
    *   关于 `python.old`：理论上当前的正则应该能匹配它，但在实际复杂的输入流中，基于正则的多行匹配非常容易受到行尾符、缓冲区边界等因素的干扰。

解决方案：轻量级 AST (状态机)

你提到的引入“简单的 AST 工具”是完全正确的方向。与其修补那个已经很复杂的正则表达式，不如重写解析器，使用一个**基于行的状态机 (Line-Based State Machine)**。

这种解析器就像一个轻量级的 AST 构建器：
1.  它逐行读取文本。
2.  它维护一个简单的状态：`IN_BLOCK` 或 `OUT_OF_BLOCK`。
3.  它能精确地处理围栏的开启和闭合，对语言标签 (`info string`) 没有任何字符限制（除了换行符），完全符合 CommonMark 规范的精神。

这将一劳永逸地解决 `python.old`, `c++`, `python-new` 以及空格容错性等所有问题。

下面是 TDD 计划。

## [WIP] refactor: 采用状态机解析器以支持复杂语言标签

### 用户需求
1.  消除 Pytest 的 `timeout` 标记警告。
2.  **核心需求**: 替换脆弱的正则解析器，实现一个能够处理 `python.old`、`c++`、`python-new` 等任意语言标签的健壮解析器。
3.  遵循 TDD：先写出当前无法通过的测试用例（针对特殊字符标签），然后通过重构解析器来实现它。

### 评论
当前的正则解析器是原型的产物。转向状态机解析器是代码成熟化的必经之路。这种新解析器不仅更健壮，而且更易于调试和扩展。

### 目标
1.  在 `conftest.py` 中注册 `timeout` 标记，消除警告。
2.  创建 `tests/runtime/test_parser_robustness.py`，包含 `c++`, `python-old` (模拟你的 `python.new` 场景) 以及带空格的围栏测试。
3.  重写 `packages/quipu-runtime/src/pyquipu/runtime/parser.py`，废弃 `RegexBlockParser`，实现 `LineBlockParser`。

### 基本原理
正则表达式处理嵌套结构和多行边界总是很痛苦且容易出错。状态机通过显式地处理每一行，将“解析”分解为简单的决策树，从而获得极高的稳定性和灵活性。

### 标签
#intent/refine #flow/ready #priority/high #comp/runtime #concept/parser #scope/core #ai/instruct #task/domain/parsing #task/object/state-machine-parser #task/action/rewrite #task/state/continue

---
### Script

#### Acts 1: 消除 Pytest 警告

我们先清理噪音，确保测试输出干净。

~~~~~act
patch_file
tests/runtime/conftest.py
~~~~~
~~~~~python
@pytest.fixture
def isolated_vault(executor: Executor) -> Path:
    """
    提供 Executor 实例的根工作目录。
    """
    return executor.root_dir
~~~~~
~~~~~python
@pytest.fixture
def isolated_vault(executor: Executor) -> Path:
    """
    提供 Executor 实例的根工作目录。
    """
    return executor.root_dir


def pytest_configure(config):
    """注册自定义标记以消除警告"""
    config.addinivalue_line("markers", "timeout(seconds): kill test after a certain time")
~~~~~

#### Acts 2: 创建针对解析器的红灯测试 (The "Red" Test)

我们将创建一个测试文件，其中包含当前正则解析器**必定会失败**的用例。特别是 `python-new`（含连字符）和 `c++`（含加号），这些在当前正则 `\w` 中是不被允许的。同时我们也测试 `python.old` 以确保新解析器也能处理它。

~~~~~act
write_file
tests/runtime/test_parser_robustness.py
~~~~~
~~~~~python
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
        parser = get_parser("tilde")
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
        parser = get_parser("tilde")
        stmts = parser.parse(text)
        
        # 解析器应该能提取出第一个有效的 act
        assert len(stmts) == 1
        assert stmts[0]["act"] == "valid"
        # unclosed block 应该被忽略，或者至少不应该导致之前的 act 丢失
~~~~~

### 下一步建议

请执行此计划。
运行 `pytest tests/runtime/test_parser_robustness.py`。
我预期 `test_parse_complex_language_tags` 会失败，因为当前的正则 `(\w*(?:\.\w+)*)` 无法匹配 `python-new` 和 `c++`，导致这些块被解析器忽略，最终 `len(stmt["contexts"])` 将小于 3。

一旦确认失败，我将生成下一个计划来重写 `parser.py`。
