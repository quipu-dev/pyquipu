# fix: 修复 TUI 无法显示节点描述的问题

## 用户需求
在 `qd ui` (TUI 界面) 中，历史节点的描述（Summary）无法显示。

## 评论
经过分析，这是一个 UI 层的问题。在之前的重构中，`GitObjectHistoryReader` 实现了“懒加载”机制，不再默认加载节点的 `content`。然而，TUI 中的 `_get_node_summary` 方法依然试图从 `node.content` 中实时解析摘要，导致因为内容为空而无法获取摘要。
`QuipuNode` 对象现在已经包含了一个权威的 `summary` 字段（从 `metadata.json` 或旧版 Frontmatter 中加载），UI 应该直接使用这个字段。

## 目标
修改 `packages/quipu-cli/src/quipu/cli/tui.py`，让 `_get_node_summary` 直接返回 `node.summary`，移除过时的解析逻辑。

## 基本原理
`QuipuNode` 的 `summary` 属性是单一真理来源 (Source of Truth)。UI 不应包含针对内容的解析逻辑。这不仅修复了 Bug，还提升了 UI 渲染性能。

## 标签
#comp/cli #concept/ui #fix #scope/ux

---

## Script

### Acts 1: 更新 TUI 摘要获取逻辑

~~~~~act
replace packages/quipu-cli/src/quipu/cli/tui.py
~~~~~

~~~~~python
    def _get_node_summary(self, node: QuipuNode) -> str:
        content = node.content.strip()
        lines = content.split('\n')
        summary = "No description"
        if node.node_type == 'plan':
            for line in lines:
                clean_line = line.strip()
                if clean_line.startswith(('~~~', '```')): continue
                if clean_line: summary = clean_line; break
        elif node.node_type == 'capture':
            summary = next((line.strip() for line in lines if line.strip() and not line.startswith(('#', '`', '-', "###"))), "Workspace Snapshot")
        return (summary[:60] + '...') if len(summary) > 60 else summary
~~~~~

~~~~~python
    def _get_node_summary(self, node: QuipuNode) -> str:
        # 直接使用预加载的 summary 字段，避免昂贵的 content 解析
        return node.summary or "No description"
~~~~~