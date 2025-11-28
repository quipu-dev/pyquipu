你发现了重构过程中一个非常隐蔽但致命的错误。你的报告完全正确。

**问题分析：**

这是一个典型的复制-粘贴错误，由我之前的重构计划引入。请看这两行：

```python
@on(DataTable.RowHighlighted)
def _set_state(self, new_state: ContentViewSate):
    ...

@on(DataTable.RowHighlighted)
def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
    ...
```

我不小心为 `_set_state` 方法也添加了 `@on(DataTable.RowHighlighted)` 装饰器。

这意味着，每当你滚动时，`textual` 的事件系统会**同时调用** `on_row_highlighted` 和 `_set_state` 两个方法。

*   `on_row_highlighted` 的逻辑是正确的：它检查 `if self.content_view_state != ContentViewSate.HIDDEN`，在面板关闭时什么也不做。
*   但是，被错误调用的 `_set_state` 却没有这个检查。它被事件系统调用时，接收到的 `event` 对象被错误地传递给了 `new_state` 参数。虽然这不会匹配任何 `case`，但这个意外的调用流程破坏了状态机的确定性，导致了你观察到的“界面被自动打开”的非预期行为。

`_set_state` 应该是一个**内部工具方法**，由其他逻辑（如事件处理器）调用，而**绝不应该**直接作为事件处理器本身。

## [WIP] fix: 移除错误的状态机方法装饰器，修复滚动时视图意外打开的 Bug

### 错误分析
在之前的状态机重构中，一个多余的 `@on(DataTable.RowHighlighted)` 装饰器被错误地应用到了 `_set_state` 方法上。这导致每次滚动 (`RowHighlighted` 事件触发) 时，`_set_state` 方法都会被事件系统非预期地直接调用，绕过了 `on_row_highlighted` 方法中正确的状态检查逻辑，从而导致即使内容视图处于 `HIDDEN` 状态，滚动也会错误地触发UI状态变更，使视图意外打开。

### 用户需求
修复此 Bug，确保只有在内容视图已经打开的情况下，滚动才会在该视图内部触发状态更新。当视图关闭时，滚动不应产生任何副作用。

### 评论
这是一个非常微妙的 Bug，源于重构过程中的疏忽。你的精确描述帮助我们快速定位了这个问题的根源。移除这个错误的装饰器将使状态机的行为恢复确定性和可预测性。

### 目标
从 `_set_state` 方法定义中移除 `@on(DataTable.RowHighlighted)` 这一行装饰器代码。

### 基本原理
恢复正确的职责分离：`on_row_highlighted` 是事件与状态机之间的唯一接口。`_set_state` 则是状态机内部的实现细节，不应暴露给事件系统。

### 标签
#intent/fix #flow/ready #priority/critical
#comp/cli #concept/ui #scope/core
#ai/instruct
#task/domain/ui #task/object/tui-refactor #task.action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 从 `_set_state` 中移除错误的装饰器

我们将对 `packages/quipu-cli/src/quipu/cli/tui.py` 进行修正。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)

    @on(DataTable.RowHighlighted)
    def _set_state(self, new_state: ContentViewSate):
        if self.content_view_state == new_state:
            return # Avoid redundant operations
~~~~~
~~~~~python
        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)

    def _set_state(self, new_state: ContentViewSate):
        if self.content_view_state == new_state:
            return # Avoid redundant operations
~~~~~

### 下一步建议
这是本次重构的最后一个已知问题。在移除了这个错误的装饰器后，状态机应该能完全按预期工作了。

请进行最终测试。如果一切正常，我将为你生成一个包含从“性能优化”到“状态机重构”所有工作的最终 `[COMMIT]` 计划。
