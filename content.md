# feat: 为 TUI 增加 j/k 导航键

## 用户需求
你希望在 TUI 界面中，除了使用上下箭头外，也能够使用 `j` 键向下移动、`k` 键向上移动光标，这符合 Vim 等工具的常见操作习惯。

## 目标
在 `quipu.cli.tui.QuipuUiApp` 中添加新的按键绑定，将 `j` 映射到 `cursor_down` 动作，将 `k` 映射到 `cursor_up` 动作。

## 基本原理
`textual` 框架通过 `BINDINGS` 类属性来定义按键绑定。`DataTable` 小部件已经内置了 `cursor_up` 和 `cursor_down` 动作，并且默认已绑定到方向键。我们只需要为 `j` 和 `k` 添加新的 `Binding` 条目，将它们指向相同的动作即可。

## 标签
#ui #keybinding

---

## Script

### Act 1: 修改 tui.py 以添加 j/k 按键绑定

我将修改 `packages/quipu-cli/src/quipu/cli/tui.py` 文件，在 `QuipuUiApp` 类的 `BINDINGS` 列表中增加 `j` 和 `k` 的绑定。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("h", "toggle_hidden", "显隐非关联分支"),
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
    ]
~~~~~
~~~~~python
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("h", "toggle_hidden", "显隐非关联分支"),
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
        Binding("k", "cursor_up", "上移", show=False),
        Binding("j", "cursor_down", "下移", show=False),
    ]
~~~~~