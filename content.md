## fix 修复 `quipu ui` 命令在启动时因表格列未初始化而导致的崩溃问题。

好的，我分析了 `tui.debug.log` 中的错误日志。

### 错误分析

错误是 `ValueError: More values provided than there are columns.`，发生在 `quipu/cli/tui.py` 的 `_populate_table` 方法调用 `table.add_row` 时。

根本原因是：
1.  在 `on_mount` 方法中，`DataTable` Widget (表格) 被创建，但没有定义任何列 (Columns)。
2.  随后 `on_mount` 调用 `_load_page(1)`，这个方法会获取第一页的数据并调用 `_populate_table`。
3.  `_populate_table` 尝试向一个没有列的表格中添加一个包含 3 个数据项的行，因此 `textual` 框架抛出了 `ValueError`。

### 用户需求

修复 `quipu ui` 命令在启动时因表格列未初始化而导致的崩溃问题。

### 评论

这是一个启动逻辑中的疏漏。修复方案很直接，即在第一次加载数据之前，确保 `DataTable` 的列已经被正确初始化。

### 目标

修改 `tui.py`，在 `on_mount` 阶段正确初始化表格的列，确保 UI 能够正常加载并显示第一页的历史数据。

### 基本原理

修复此问题的最清晰方法是在 `on_mount` 方法中，加载任何数据**之前**，为 `DataTable` 添加所需的列。`on_mount` 是组件挂载后执行一次性设置的理想生命周期钩子，这符合其设计意图。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/tui #task/action/bug-fix #task/state/begin #task/status/completed

---

### Script

#### Acts 1: 修复 TUI 表格列初始化逻辑

我将在 `on_mount` 方法中，获取 `DataTable` 实例，并在调用 `_load_page` 之前为其添加所需的列定义。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
            self.view_model = GraphViewModel(reader=self.engine.reader, current_hash=current_hash)
            self.view_model.initialize()
            
            logger.debug("TUI: Loading first page...")
            self._load_page(1)
        except Exception as e:
~~~~~
~~~~~python
            self.view_model = GraphViewModel(reader=self.engine.reader, current_hash=current_hash)
            self.view_model.initialize()

            table = self.query_one(DataTable)
            table.add_columns("Time", "Graph", "Node Info")
            
            logger.debug("TUI: Loading first page...")
            self._load_page(1)
        except Exception as e:
~~~~~

### 下一步建议
此修复完成后，`quipu ui` 命令应该可以正常启动。你可以再次运行该命令进行验证。
