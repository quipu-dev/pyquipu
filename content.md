好的，我们继续执行任务列表中的下一项：**任务 5.1**。

现在数据已经能正确地从后端传递到前端，我们需要在用户界面 (TUI) 上将这些`owner_id`信息展示出来，让用户能够直观地看到每个历史节点的作者。

---
## feat: 在 TUI 历史视图中显示节点所有者信息

### 用户需求
在实现了多用户同步的后端逻辑后，TUI 需要相应升级，以展示每个历史节点的 `owner_id`。这能让用户在复杂的协作历史中，直观地区分自己和他人的工作分支。

### 评论
这是一个直接的 UI 增强任务。我们将利用 `QuipuNode` 对象中已经可用的 `owner_id` 数据，在历史表格的“节点信息”列中，为每个节点摘要添加一个简短、带颜色的所有者前缀。

### 目标
修改 `quipu-cli` 的 `tui.py` 模块中的 `_populate_table` 方法，使其能够渲染出经过截断和着色的 `owner_id`。

### 基本原理
为了保持 UI 的整洁，我们将 `user_id` 截断为前 12 个字符，并以 `(user-id-prefix)` 的格式显示在节点摘要之前。通过使用 `yellow` (黄色) 来渲染，可以使其在视觉上与节点类型、哈希等其他信息区分开来。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/owner-visualization #task/action/implementation #task/state/begin #task/status/active

---

### Script

#### Acts 1: 修改 TUI 渲染逻辑

我们将对 `_populate_table` 方法进行修改，在构建节点信息字符串时，如果 `node.owner_id` 存在，则在最前面加上所有者信息。

`````````act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
`````````
`````````python
            summary = self._get_node_summary(node)
            info_text = f"[{base_color}][{node.node_type.upper()}] {node.short_hash}[/{base_color}] - {summary}"
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))
`````````
`````````python
            summary = self._get_node_summary(node)

            owner_info = ""
            if node.owner_id:
                owner_display = node.owner_id[:12]
                owner_info = f"[yellow]({owner_display}) [/yellow]"

            info_text = f"{owner_info}[{base_color}][{node.node_type.upper()}] {node.short_hash}[/{base_color}] - {summary}"
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))
`````````

### 下一步建议
我们已经完成了 UI 的基本信息展示。下一步是 **任务 5.2**，验证在多用户历史并存的情况下，可达性高亮逻辑 (即区分主干分支和非关联分支的视觉效果) 依然能够正确工作，确保新引入的多用户分支不会干扰核心的导航体验。
