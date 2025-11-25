非常抱歉，我在 `docs/03_user_guide/01_core_concepts.md` 的匹配文本中错误地使用了列表符号而不是二级标题符号。这导致了替换失败。

为了避免换行符带来的潜在匹配问题，我将缩小匹配范围到具体的行。以下是修正后的操作序列（包括之前未执行的部分）：

~~~act
replace
~~~
~~~path
docs/03_user_guide/01_core_concepts.md
~~~
~~~old_string
Axon v4.2 引入了革命性的状态管理机制，它基于 Git 底层对象模型，而非传统的文件数据库。
~~~
~~~new_string
Axon 引入了革命性的状态管理机制，它基于 Git 底层对象模型，而非传统的文件数据库。
~~~

~~~act
replace
~~~
~~~path
docs/03_user_guide/01_core_concepts.md
~~~
~~~old_string
*   **事件时间轴 (Event-based Timeline)**: Axon v4.3 之后，即使一个操作没有修改任何文件（如 `git commit` 或运行测试），它也会被记录为一个**幂等节点 (Idempotent Node)**。这确保了 Axon 的历史是一条完整的、可审计的**事件流**，而不仅仅是文件快照。
~~~
~~~new_string
*   **事件时间轴 (Event-based Timeline)**: Axon (v0.3.0+) 引入了事件流机制，即使一个操作没有修改任何文件（如 `git commit` 或运行测试），它也会被记录为一个**幂等节点 (Idempotent Node)**。这确保了 Axon 的历史是一条完整的、可审计的**事件流**，而不仅仅是文件快照。
~~~

~~~act
replace
~~~
~~~path
docs/05_developer_guide/01_architecture.md
~~~
~~~old_string
Axon v4.2 采用了 **核壳分离 (Core-Shell)** 架构。
~~~
~~~new_string
Axon 采用了 **核壳分离 (Core-Shell)** 架构。
~~~

~~~act
replace
~~~
~~~path
TODO.md
~~~
~~~old_string
## ✅ 已完成里程碑

我们已经成功完成了 Axon v4.2 架构的核心重构和引擎集成。主要成就包括：
~~~
~~~new_string
## ✅ 已完成里程碑

我们已经成功完成了 Axon 架构的核心重构和引擎集成。主要成就包括：
~~~

~~~act
replace
~~~
~~~path
TODO.md
~~~
~~~old_string
这是 v4.2 架构中最复杂、最核心的部分。我们已经构建并验证了一个功能完备的状态引擎地基。
~~~
~~~new_string
这是新架构中最复杂、最核心的部分。我们已经构建并验证了一个功能完备的状态引擎地基。
~~~

~~~act
replace
~~~
~~~path
TODO.md
~~~
~~~old_string
## 🚀 Axon v4.2 开发路线图
~~~
~~~new_string
## 🚀 Axon 开发路线图 (v0.3.x)
~~~

~~~act
replace
~~~
~~~path
TODO.md
~~~
~~~old_string
*   [x] **文档更新**：更新 `README.md` 和 `docs/` 目录，反映 v4.3 的新概念和工作流。
~~~
~~~new_string
*   [x] **文档更新**：更新 `README.md` 和 `docs/` 目录，反映 0.3.x 的新概念和工作流。
~~~