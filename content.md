## [WIP] fix: 修复 Engine 中新节点的父子关系链接问题

### 错误分析
测试 `tests/engine/test_deduplication.py::TestDeduplication::test_idempotent_plan_creation` 失败。
断言错误：`assert node_b.parent == node_a`。

原因在于 `HistoryWriter`（特别是 `GitObjectHistoryWriter`）是无状态的。当它创建一个新节点（`node_b`）时，它通过 Git 查询找到父 Commit Hash，并构造了一个仅包含基本信息的**占位符（Stub）节点**作为 `node_b.parent`。

而 `Engine` 中维护了完整的 `history_graph`，其中包含了真实的、信息完整的 `node_a` 对象。

当 `node_b` 被创建并加入图谱时，`Engine` 没有执行“图谱维护（Graph Maintenance）”逻辑，即没有将 `node_b` 的占位符父节点替换为图谱中已存在的真实父节点对象。这导致：
1.  `node_b.parent` 指向一个残缺的 Stub 对象，与 `node_a` 不相等。
2.  `node_a.children` 列表没有被更新，不包含 `node_b`。

### 用户需求
确保当 Engine 创建新节点时（无论是通过 `create_plan_node` 还是 `capture_drift`），能够正确地将其链接到现有的内存图谱中，保持对象引用的一致性和完整性。

### 目标
1.  修改 `packages/quipu-engine/src/pyquipu/engine/state_machine.py`。
2.  在 `capture_drift` 和 `create_plan_node` 方法中，在从 Writer 获取新节点后，立即检查其父节点是否存在于 `self.history_graph` 中。
3.  如果存在，用图谱中的真实对象替换新节点的 Stub 父节点，并更新真实父节点的 `children` 列表。

### 基本原理
`Engine` 作为状态机，负责维护内存中对象图谱的完整性。Writer 只负责持久化并返回“它所知道的”局部信息。Engine 必须负责将这个局部信息正确地“缝合”到全局图谱中。这是一种标准的**图谱再水化 (Rehydration)** 或 **对象标识映射 (Identity Map)** 模式的应用。

### 标签
#intent/fix #flow/ready #priority/high #comp/engine #concept/state #scope/core #ai/instruct #task/domain/testing #task/object/graph-linking #task/action/fix #task/state/begin

---

### Script

#### Acts 1: 修复 Engine 状态机中的图谱链接逻辑

我们将修改 `state_machine.py`，在节点创建后增加父子关系的协调逻辑。

~~~~~act
patch_file
packages/quipu-engine/src/pyquipu/engine/state_machine.py
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        self.history_graph[new_node.commit_hash] = new_node
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        if new_node.parent and new_node.parent.commit_hash in self.history_graph:
            real_parent = self.history_graph[new_node.parent.commit_hash]
            new_node.parent = real_parent
            if new_node not in real_parent.children:
                real_parent.children.append(new_node)

        self.history_graph[new_node.commit_hash] = new_node
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/pyquipu/engine/state_machine.py
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        self.history_graph[new_node.commit_hash] = new_node
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        if new_node.parent and new_node.parent.commit_hash in self.history_graph:
            real_parent = self.history_graph[new_node.parent.commit_hash]
            new_node.parent = real_parent
            if new_node not in real_parent.children:
                real_parent.children.append(new_node)

        self.history_graph[new_node.commit_hash] = new_node
~~~~~
