# fix: Handle None message in capture summary generation

## 用户需求
在修复了上一个测试问题后，`test_capture_drift_git_object` 测试用例再次失败，这次抛出了 `AttributeError: 'NoneType' object has no attribute 'strip'`。

错误发生在 `GitObjectHistoryWriter` 的 `_generate_summary` 方法中。当 `engine.capture_drift(dirty_hash)`被调用时（未提供 `message` 参数），`kwargs['message']` 的值为 `None`。`kwargs.get("message", "")` 表达式因此返回 `None` 而不是预期的空字符串 `""`，导致在 `None` 上调用 `.strip()` 方法时程序崩溃。

## 评论
这是一个典型的边界情况处理错误。虽然看起来微小，但它阻止了新存储后端的 `capture` 节点在没有用户附带消息时的创建流程，是一个阻塞性的缺陷。修复这个问题将使核心的 `capture_drift` 功能恢复正常。

## 目标
修改 `GitObjectHistoryWriter._generate_summary` 方法，使其能够健壮地处理 `message` 参数为 `None` 的情况，确保代码不会因 `AttributeError` 而崩溃。

## 基本原理
问题的根源在于 `kwargs.get("message", "")` 的行为。当 `kwargs` 字典中存在 `message` 键且其值为 `None` 时，`.get()` 方法会返回 `None`，而不是第二个参数指定的默认值。

正确的处理方式是使用 `(kwargs.get("message") or "")` 这个 Python 惯用法。如果 `kwargs.get("message")` 的结果是 `None`（一个 "falsy" 值），`or` 表达式会取其右侧的值，即 `""`。这样，`.strip()` 方法将始终在一个安全的字符串上被调用，从而避免错误。

## 标签
#comp/engine #concept/history #scope/core

---

## Script

### Acts 1: 修复 `_generate_summary` 中的空指针问题

我们将修改 `git_object_storage.py` 中 `_generate_summary` 方法内的一行代码，以正确处理 `message` 为 `None` 的情况。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
        elif node_type == "capture":
            user_message = kwargs.get("message", "").strip()
            
            changes = self.git_db.get_diff_name_status(input_tree, output_tree)
            if not changes:
~~~~~
~~~~~python
        elif node_type == "capture":
            user_message = (kwargs.get("message") or "").strip()
            
            changes = self.git_db.get_diff_name_status(input_tree, output_tree)
            if not changes:
~~~~~