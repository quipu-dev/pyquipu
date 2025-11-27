好的，分析收到了。这个错误 `AttributeError: 'InMemoryDB' object has no attribute 'get_diff_stat'` 表明我们的测试模拟数据库 `InMemoryDB` 没有跟上 `GitDB` 接口的更新。`Engine.capture_drift` 方法现在会调用 `get_diff_stat` 来生成变更摘要，而我们的内存模拟实现中缺少这个方法。

我将为 `InMemoryDB` 添加这个方法以及其依赖的 `get_diff_name_status` 方法，以修复测试。

### fix(tests): 为 InMemoryDB 实现 diff 方法以修复引擎测试

### 错误分析
`Engine.capture_drift` 调用了 `self.git_db.get_diff_stat`。在 `test_engine_memory.py` 测试中，`git_db` 是一个 `InMemoryDB` 实例，它没有实现 `get_diff_stat` 方法，导致了 `AttributeError`。

### 用户需求
修复 `test_engine_memory.py` 中的测试失败。

### 目标
在 `tests/helpers.py` 的 `InMemoryDB` 类中，实现 `get_diff_stat` 和 `get_diff_name_status` 方法，以模拟真实 `GitDB` 的行为。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/test-suite #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 在 `InMemoryDB` 中实现 diff 方法

我们将把这两个缺失的方法添加到 `tests/helpers.py` 文件中的 `InMemoryDB` 类。

~~~~~act
patch_file
tests/helpers.py
~~~~~
~~~~~python
    def checkout_tree(self, tree_hash: str):
        self.vfs.files = self.tree_states.get(tree_hash, {}).copy()


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
~~~~~
~~~~~python
    def checkout_tree(self, tree_hash: str):
        self.vfs.files = self.tree_states.get(tree_hash, {}).copy()

    def get_diff_name_status(self, old_tree: str, new_tree: str) -> List[Tuple[str, str]]:
        """Compares two tree states and returns a list of changes."""
        old_files = self.tree_states.get(old_tree, {})

        if new_tree == self.vfs.get_state_hash():
            new_files = self.vfs.files
        else:
            new_files = self.tree_states.get(new_tree, {})

        old_paths = set(old_files.keys())
        new_paths = set(new_files.keys())

        added = new_paths - old_paths
        deleted = old_paths - new_paths
        common = old_paths & new_paths

        changes = []
        for path in sorted(list(added)):
            changes.append(("A", path))
        for path in sorted(list(deleted)):
            changes.append(("D", path))

        for path in sorted(list(common)):
            if old_files.get(path) != new_files.get(path):
                changes.append(("M", path))

        return changes

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """Generates a simplified, human-readable diff summary."""
        changes = self.get_diff_name_status(old_tree, new_tree)
        return "\n".join(f"{status}\t{path}" for status, path in changes)


class InMemoryHistoryManager(HistoryReader, HistoryWriter):
~~~~~
