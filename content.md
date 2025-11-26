# fix: 纠正 Executor 中的回归错误导致的 TypeError

## 用户需求
在上次对 `Executor` 进行解耦重构后，测试套件暴露出大量失败。最核心的错误是 `TypeError: unhashable type: 'list'`，这个错误导致了连锁反应，引发了多个测试中的 `AssertionError` 和 `IndexError`。

你需要定位并修复这个回归错误。

## 评论
经过分析，这是一个典型的回归错误。在重构 `executor.py` 时，一个关键的变量赋值被错误地修改，导致程序试图将一个列表用作字典的键，从而触发了 `TypeError`。由于 `Executor` 是核心组件，这个单一的错误点影响了几乎所有依赖指令执行功能的测试。修复此问题将使测试套件恢复正常。

## 目标
1.  定位 `executor.py` 中导致 `TypeError` 的根本原因。
2.  修复 `execute` 和 `summarize_statement` 方法中的错误逻辑。
3.  修复 `get_registered_acts` 方法中的一个次要错误。
4.  确保所有测试都能通过。

## 基本原理
错误发生在 `executor.py` 的 `execute` 和 `summarize_statement` 方法中。在解析命令行参数后，代码错误地将整个 `tokens` 列表赋值给了 `act_name` 变量 (`act_name = tokens`)。

正确的行为应该是将 `tokens` 列表的第一个元素赋值给 `act_name` (`act_name = tokens[0]`)。

当错误的 `act_name` (一个列表) 被用于在 `self._acts` 字典中查找指令时 (`if act_name not in self._acts`)，Python 尝试对列表进行哈希计算，从而引发了 `TypeError: unhashable type: 'list'`。

修复方案是找到所有错误赋值的地方，并将其恢复为正确的 `tokens[0]`。

## 标签
#intent/fix #flow/ready #priority/critical
#comp/runtime #comp/tests
#scope/core
#ai/instruct

---

## Script

### Acts 1: 修复 Executor 的核心错误

我们将通过三次精确的 `replace` 操作来修复 `executor.py` 中的三个问题。

首先，修复 `get_registered_acts` 中访问文档字符串的错误。

~~~~~act
replace packages/quipu-runtime/src/quipu/core/executor.py
~~~~~
~~~~~python
    def get_registered_acts(self) -> Dict[str, str]:
        """获取所有已注册的 Act 及其文档字符串"""
        return {name: data.__doc__ for name, data in self._acts.items()}
~~~~~
~~~~~python
    def get_registered_acts(self) -> Dict[str, str]:
        """获取所有已注册的 Act 及其文档字符串"""
        return {name: data[0].__doc__ for name, data in self._acts.items()}
~~~~~

其次，修复 `summarize_statement` 方法中的 `TypeError` 根源。

~~~~~act
replace packages/quipu-runtime/src/quipu/core/executor.py
~~~~~
~~~~~python
        act_name = tokens
        inline_args = tokens[1:]
        contexts = stmt["contexts"]

        if act_name not in self._acts:
~~~~~
~~~~~python
        if not tokens:
            return None

        act_name = tokens[0]
        inline_args = tokens[1:]
        contexts = stmt["contexts"]

        if act_name not in self._acts:
~~~~~

最后，修复 `execute` 方法中完全相同的 `TypeError` 根源。

~~~~~act
replace packages/quipu-runtime/src/quipu/core/executor.py
~~~~~
~~~~~python
            act_name = tokens
            inline_args = tokens[1:]

            if act_name not in self._acts:
~~~~~
~~~~~python
            act_name = tokens[0]
            inline_args = tokens[1:]

            if act_name not in self._acts:
~~~~~
