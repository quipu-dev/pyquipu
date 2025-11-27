## fix: 修复 TUI 光标定位方法调用错误

### 错误分析
日志明确指出了问题所在：
`AttributeError: 'DataTable' object has no attribute 'is_valid_row_key'. Did you mean: 'is_valid_row_index'?`

我在之前的修改中使用了 `table.is_valid_row_key(row_key)`，这是一个不存在的方法。在 Textual 的 `DataTable` API 中，用于检查 key 是否有效的标准方法实际上是 `table.is_valid_row_index(table.get_row_index(key))`，或者更直接地，在调用 `get_row_index(key)` 时捕获 `KeyError` 异常（Textual 文档推荐的做法是假设 key 存在，不存在会抛异常）。

### 用户需求
修复光标无法定位的 Bug。

### 目标
修正 `_focus_current_node` 中错误的 API 调用。

### 基本原理
将错误的 `is_valid_row_key` 检查替换为 `try-except KeyError` 结构，这更加 Pythonic 且符合 Textual 的设计模式。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #scope/ux #ai/instruct #task/domain/ui #task/object/reachability #task/action/bug-fix #task/state/end

---

### Script

#### Acts 1: 修正 API 调用

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
        try:
            row_key = str(target_node.filename)
            logger.debug(f"DEBUG: Target row key: {row_key}")

            if table.is_valid_row_key(row_key):
                row_index = table.get_row_index(row_key)
                logger.debug(f"DEBUG: Row index found: {row_index}. Setting cursor.")
                
                # 1. 设置视觉光标
                table.cursor_coordinate = Coordinate(row=row_index, column=0)
                
                # 2. 同步逻辑状态 (防止事件未触发)
                self.current_selected_node = target_node
                
                # 3. 刷新关联视图
                if self.is_split_mode:
                    self._update_content_view()
            else:
                logger.warning(f"DEBUG: Row key {row_key} is invalid in DataTable (maybe filtered?).")
        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)
~~~~~
~~~~~python
        try:
            row_key = str(target_node.filename)
            logger.debug(f"DEBUG: Target row key: {row_key}")

            # Textual 的 DataTable API 中，get_row_index 会在 key 不存在时抛出 KeyError
            # 或者 RowKeyError，具体取决于版本，但 KeyError 是基类
            try:
                row_index = table.get_row_index(row_key)
                logger.debug(f"DEBUG: Row index found: {row_index}. Setting cursor.")
                
                # 1. 设置视觉光标
                table.cursor_coordinate = Coordinate(row=row_index, column=0)
                
                # 2. 同步逻辑状态 (防止事件未触发)
                self.current_selected_node = target_node
                
                # 3. 刷新关联视图
                if self.is_split_mode:
                    self._update_content_view()
            except LookupError:
                 # LookupError 捕获 RowKeyError 等
                logger.warning(f"DEBUG: Row key {row_key} not found in DataTable.")

        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)
~~~~~
