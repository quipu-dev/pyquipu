分析正确。这是一个典型的回归错误，问题出在 `quipu save` 命令确定其父节点的方式上。

错误分析

根本原因在于 `pyquipu/engine/state_machine.py` 中的 `capture_drift` 方法在逻辑上犯了一个“苹果与橘子”的比较错误。

1.  **.quipu/HEAD 文件**: 这个文件存储的是上一次操作完成后的 **Tree Hash** (例如 `b09d442...`)。
2.  **Engine 的历史图谱**: `engine.history_graph` 是一个字典，它的键 (key) 是 **Commit Hash** (例如 `fbff7e4...`)。
3.  **错误的逻辑**: 当前的代码在 `capture_drift` 中读取了 `HEAD` 文件里的 **Tree Hash**，然后直接用这个 **Tree Hash** 去检查它是否存在于 `history_graph` 的 **键** 中。

这是出问题的代码行：
```python
# pyquipu/engine/state_machine.py

def capture_drift(...):
    # ...
    head_hash = self._read_head()  # head_hash 是一个 Tree Hash
    if head_hash and head_hash in self.history_graph: # 错误：用 Tree Hash 在 Commit Hash 字典里查找
        input_hash = head_hash
    elif self.history_graph:
        # ... 触发了这里的 fallback 逻辑
        logger.warning(f"⚠️  丢失 HEAD 指针...") 
```
这个 `if` 条件永远不会为 `True`，因为 Tree Hash 和 Commit Hash 是两种完全不同的哈希值。因此，程序总会错误地进入 `elif` 分支，报告“丢失 HEAD 指针”，并回退到使用时间戳最新的节点作为父节点，而不是遵循 `HEAD` 指针的指示。

解决方案

正确的做法是，我们应该遍历 `history_graph` 中的所有节点 (values)，找到那个 `output_tree` 属性与 `HEAD` 文件内容（Tree Hash）相匹配的节点。一旦找到这个节点，它就是当前状态正确的父节点。

我将修改 `capture_drift` 方法来执行正确的查找逻辑。同时，我将改进那条警告日志，使其在 `HEAD` 文件中的哈希确实无效时提供更精确的信息。

## [WIP] fix(engine): 修正 HEAD 指针的父节点查找逻辑

### 错误分析
`quipu save` 命令在连续执行时，第二次执行会错误地报告“丢失 HEAD 指针”。根本原因在于 `state_machine.py` 的 `capture_drift` 方法中，将从 `.quipu/HEAD` 文件读取的 Tree Hash 直接用于在以 Commit Hash 为键的历史图谱字典中进行查找。由于哈希类型不匹配，查找必然失败，导致程序错误地回退到“寻找最新节点”的逻辑，而不是使用 `HEAD` 指向的正确父节点。

### 用户需求
连续执行 `quipu save` 时，第二次 `save` 操作必须正确地将第一次 `save` 产生的状态作为其父状态，而不应报告“丢失 HEAD 指针”并错误地回退。

### 评论
这是一个关键的回归 Bug，影响了 `quipu save` 命令的核心功能和数据一致性。修复此问题对于保证历史图谱的拓扑结构正确性至关重要。

### 目标
1.  修改 `capture_drift` 方法，使其通过遍历 `history_graph` 的值来查找与 `HEAD` Tree Hash 匹配的节点。
2.  使用找到的节点作为新创建的 `capture` 节点的父节点。
3.  改进警告日志，使其在 `HEAD` 指针确实无效时能提供更明确的上下文。

### 基本原理
我们将从 `.quipu/HEAD` 读取 Tree Hash，然后使用 `next()` 和一个生成器表达式在 `engine.history_graph.values()` 中高效地查找 `output_tree` 属性与该 Tree Hash 匹配的 `QuipuNode`。如果找到，就使用它的 `output_tree` 作为 `input_hash`。如果找不到（例如 `HEAD` 文件损坏或指向一个不存在的状态），才执行现有的回退逻辑。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #concept/history #scope/core #ai/instruct #task/domain/storage #task/object/head-pointer #task/action/bug-fix #task/state/begin

---

### Script

#### Acts 1: 修正 `capture_drift` 中的父节点查找逻辑

我们将 `patch` `state_machine.py` 文件，替换掉错误的 `in` 检查，改为正确的遍历查找。

~~~~~act
patch_file
packages/quipu-engine/src/pyquipu/engine/state_machine.py
~~~~~
~~~~~python
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        input_hash = genesis_hash
        head_hash = self._read_head()
        if head_hash and head_hash in self.history_graph:
            input_hash = head_hash
        elif self.history_graph:
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            logger.warning(f"⚠️  丢失 HEAD 指针，自动回退到最新历史节点: {input_hash[:7]}")
~~~~~
~~~~~python
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        input_hash = genesis_hash
        head_tree_hash = self._read_head()
        parent_node = None

        if head_tree_hash:
            # 正确的逻辑：遍历节点，用 output_tree 匹配 head 的 tree hash
            parent_node = next(
                (node for node in self.history_graph.values() if node.output_tree == head_tree_hash), None
            )

        if parent_node:
            input_hash = parent_node.output_tree
        elif self.history_graph:
            # 只有当 HEAD 指针无效或丢失时，才执行回退逻辑
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            logger.warning(
                f"⚠️  HEAD 指针 '{head_tree_hash[:7] if head_tree_hash else 'N/A'}' 无效或丢失，自动回退到最新历史节点: {input_hash[:7]}"
            )
~~~~~

### 下一步建议
- **添加回归测试**：在 `tests/engine/test_head_tracking.py` 中添加一个专门的测试用例，模拟“连续执行两次 `save`”的场景，并断言第二次 `save` 创建的节点的 `input_tree` 哈希值等于第一次 `save` 的 `output_tree` 哈希值。这将防止此问题在未来再次出现。
