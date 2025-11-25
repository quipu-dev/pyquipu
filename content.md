~~~act
log_thought
~~~
~~~text
The user reported that an idempotent node (where input_tree == output_tree) was successfully created but did not appear in the TUI. This suggests a potential bug in `ui/tui.py` related to how the node graph is calculated, sorted, or rendered. Specifically, the logic might not be correctly handling cases where a node's parent is itself (conceptually) or when filtering nodes. While this plan focuses on versioning cleanup, this UI behavior should be investigated in a future step.
~~~

~~~act
write_file
~~~
~~~path
VERSION
~~~
~~~content
0.3.0
~~~

~~~act
replace
~~~
~~~path
core/engine.py
~~~
~~~old_string
        # v4.3 策略变更：即使状态未发生变更 (Idempotent)，也记录节点。
~~~
~~~new_string
        # 即使状态未发生变更 (Idempotent)，也记录节点。
~~~