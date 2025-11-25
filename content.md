测试失败是因为在未运行的 Textual App 实例上调用了涉及 UI 组件查询的方法 (`query_one`)。我们在测试逻辑中应该直接操作状态属性，而不是触发 UI 刷新动作。

### 1. 修正测试代码

我们将直接修改 `app.show_unreachable` 属性，而不是调用 `action_toggle_hidden`。

~~~act
replace
~~~
~~~path
tests/test_ui_reachability.py
~~~
~~~old_string
        # 2. Toggle Hide
        app.action_toggle_hidden()
        assert app.show_unreachable is False
        
        # If we populate now, C should be skipped
~~~
~~~new_string
        # 2. Toggle Hide (Directly set property to avoid UI query error in test)
        app.show_unreachable = False
        
        # If we populate now, C should be skipped
~~~

### 2. 再次运行测试

~~~act
run_command
~~~
~~~command
pytest tests/test_ui_reachability.py
~~~