# [fix]: 修复 TUI 无限滚动事件绑定错误

## 用户需求
用户在运行测试时遇到了 `AttributeError: type object 'DataTable' has no attribute 'Scroll'`。这是因为 `DataTable.Scroll` 并不是 Textual 中有效的事件引用。

## 评论
这是一个典型的 API 使用错误。在 Textual 中实现无限滚动，更稳健的方式是监听 `RowHighlighted` 事件（光标移动），并检查光标是否接近当前行数的底部。

## 目标
修复 `quipu-cli` 中的 `tui.py`，移除错误的事件绑定，并将分页加载触发逻辑整合到光标移动事件中。

## 基本原理
当用户向下移动光标时，如果光标位置超过了当前总行数的一定百分比（或倒数第 N 行），则触发下一页加载。这比监听滚动条事件更符合键盘操作的 TUI 直觉。

## 标签
#intent/fix #flow/ready #priority/critical
#comp/cli #concept/ui #scope/bug
#task/domain/ui #task/object/tui #task/action/bug-fix
#task/state/continue #task/status/active

---

## Script

### Acts 1: 修正事件监听逻辑

移除错误的 `on_scroll`，利用 `RowHighlighted` 实现无限滚动触发。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """当用户在表格中移动光标时触发"""
        row_key = event.row_key.value
        node = self.node_by_filename.get(row_key)
        if node:
            self.current_selected_node = node
            if self.is_split_mode:
                self._update_content_view()

    # 无限滚动触发器
    # 注意: Textual 版本差异，此处假设 DataTable 暴露 Scrolled 消息或我们需要轮询/计算
    # 在 0.58+ 中，可以使用 Message 监听
    @on(DataTable.Scroll)
    def on_scroll(self, event: DataTable.Scroll) -> None:
        # 检测是否滚动到底部附近
        table = self.query_one(DataTable)
        # 获取可视区域底部行索引
        # y 是滚动偏移量
        if not table.row_count:
            return
            
        # 简单的 heuristic: 如果当前 cursor 接近最后一行
        # 或者 scroll_offset 接近 max_scroll_y
        # 这里使用 cursor_row 作为近似触发，因为 Scroll 事件参数较为底层
        pass
        
    @on(DataTable.SelectionChanged) # 或 CursorMoved
    def on_cursor_move(self):
        # 备用方案：当光标移动到最后 10 行时触发加载
        table = self.query_one(DataTable)
        if table.cursor_row >= table.row_count - 10:
             self._load_next_page()
~~~~~
~~~~~python
    @on(DataTable.RowHighlighted)
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """当用户在表格中移动光标时触发"""
        # 1. 更新选中状态
        row_key = event.row_key.value
        node = self.node_by_filename.get(row_key)
        if node:
            self.current_selected_node = node
            if self.is_split_mode:
                self._update_content_view()
        
        # 2. 触发无限滚动加载
        # 当光标移动到倒数第 10 行以内时，尝试加载下一页
        table = self.query_one(DataTable)
        if table.row_count > 0 and table.cursor_row >= table.row_count - 10:
            self._load_next_page()
~~~~~
