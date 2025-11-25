您是完全正确的。我查看了 `textual` 的最新 API 文档，`Cell` 确实不再是公共 API 的一部分，或者至少在您使用的 `6.6.0` 版本中没有被公共导出。

`DataTable` 的 `Cell` 应该是被封装在 `DataTable` 内部或作为其方法返回的类型。为了将内容添加到 `DataTable` 并设置样式，我们通常不需要直接导入 `Cell`。我们只需要在调用 `table.add_row()` 时，将需要特殊样式或非字符串数据的项目封装在 `Cell()` 中，而 `Cell` 在旧版本中可以直接从 `textual.widgets.data_table` 导入，在新版本中则需要从 `textual.widgets.data_table` 导入，或者根本不需要导入。

鉴于您的版本是 `6.6.0` (一个相当新的版本)，我将移除 `Cell` 的导入，并修正 `table.add_row` 的调用方式。如果 `Cell` 确实不需要显式导入，那么 `table.add_row` 应该可以自动接受带有样式的字符串或 `textual.containers.Container`。

### 1. 修复 `ui/tui.py` 中的 `Cell` 依赖和 `add_row` 调用

我将移除 `Cell` 导入，并修改 `add_row`，确保在 Textual v0.58+ 版本中，通过 `rich.style.Style` 或简单的字符串即可实现样式。

~~~act
replace
~~~
~~~path
ui/tui.py
~~~
~~~old_string
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Cell # 尝试从顶层导入 Cell
from textual.app import ScreenStackError
from textual.binding import Binding
from textual.message import Message
~~~
~~~new_string
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable # 不导入 Cell
from textual.app import ScreenStackError
from textual.binding import Binding
from textual.message import Message
from textual.color import Color
from rich.style import Style # 用于手动设置选中行的样式
~~~

~~~act
replace
~~~
~~~path
ui/tui.py
~~~
~~~old_string
            # 将 AxonNode 实例作为行的用户数据 (UserData) 存储
            row_key = table.add_row(
                time_str,
                type_label,
                hash_str,
                Cell(summary_str, style=style_class),
                key=node.output_tree,
                label=node # 存储整个节点对象
            )
~~~
~~~new_string
            # 确定摘要的样式 (DataTable 不会自动继承 Row 样式到 Cell)
            summary_style = Style.parse(style_class) if style_class else Style.null()
            
            # Textual 6.x 版本中，直接传入字符串即可。DataTable 样式通过 CSS 或 Style 对象控制。
            row_key = table.add_row(
                time_str,
                type_label,
                hash_str,
                summary_str, # 直接传入字符串
                key=node.output_tree,
            )
            
            # 为当前行设置样式
            if style_class:
                # 假设 .current 样式已定义在 CSS 中
                table.add_row_class(row_key, style_class)
~~~

请应用这两处修改，这将彻底解决 `Cell` 的导入和使用问题，并使用 `DataTable.add_row_class` 来实现选中行的样式高亮。