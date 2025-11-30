这是一个非常敏锐的观察，完全正确。

你的分析比我最初的提案更深刻。你说得对，我提出的那个简单的“连续 `save`”测试存在一个缺陷：**它无法区分“正确遵循 HEAD 指针”和“错误地回退到最新节点恰好是同一个节点”这两种情况。**

在 `save -> save` 的线性场景中，`HEAD` 指针指向的节点 *恰好* 也是时间上最新的节点。因此，即使我的修复存在问题，那个有缺陷的“自动回退”机制也可能会意外地选择正确的父节点，从而导致一个**假阳性 (false positive)** 的测试结果。

你提出的测试方案（A -> B -> checkout A -> C）则完美地解决了这个问题。它通过 `checkout` 操作，**人为地制造了“HEAD 指向的节点 (A)”和“时间上最新的节点 (B)”之间的不一致**。在这种情况下，只有正确读取并遵循 `HEAD` 指针的逻辑才能通过测试。这是一个健壮得多的回归测试。

我将废弃我之前的计划，并根据你更优越的逻辑生成一个新的、更严格的测试计划。

## [WIP] test: 增加 HEAD 指针在非线性历史中的回归测试

### 用户需求
在 `test_head_tracking.py` 中添加一个更严格的回归测试。该测试需要验证当 `.quipu/HEAD` 指针指向一个非最新的历史节点时，`engine.capture_drift`（`quipu save` 的核心）依然能够正确地选择 `HEAD` 指向的节点作为父节点，而不是错误地回退到时间上最新的节点。

### 评论
这个测试用例通过创建一个分支场景（或称之为“分离 HEAD”场景），能够精确地验证 `capture_drift` 是否真正依赖 `HEAD` 文件作为其父节点来源的唯一真相，从而彻底杜绝“丢失 HEAD 指针”的回归 Bug。

### 目标
1.  在 `TestHeadTracking` 中添加一个名为 `test_capture_drift_on_detached_head` 的新测试。
2.  测试步骤：
    a. 创建一个线性历史 `A -> B`，此时 B 是最新节点。
    b. 执行 `checkout` 操作，将工作区和 `HEAD` 指针都重置到较旧的节点 `A`。
    c. 在此基础上创建一个新的文件变更 `C`。
    d. 调用 `capture_drift` 捕获变更，生成节点 `C`。
3.  断言：
    a. 节点 `C` 的父节点是节点 `A` (`C.input_tree == A.output_tree`)。
    b. 明确断言节点 `C` 的父节点**不是**节点 `B`，以确保回退逻辑没有被触发。

### 基本原理
此测试的核心在于 `engine.checkout(hash_a)` 这一步。它同时修改了物理工作区和逻辑 `HEAD` 指针，造成了 `HEAD` 指向的 `A` 和历史顶端的 `B` 之间的分离。这为 `capture_drift` 的父节点选择逻辑创造了一个明确的、无歧义的测试条件。

### 标签
#intent/tooling #flow/ready #priority/critical #comp/tests #comp/engine #concept/state #concept/history #concept/navigation #scope/core #ai/instruct #task/domain/storage #task/object/head-pointer #task/action/bug-fix #task/state/end #task/status/completed

---

### Script

#### Acts 1: 向 `test_head_tracking.py` 添加更严格的回归测试

我们将追加一个新的、更强大的测试用例到 `TestHeadTracking` 类。

~~~~~act
patch_file
tests/engine/test_head_tracking.py
~~~~~
~~~~~python
        # 5. Assert Logical State (HEAD)
        assert engine._read_head() == hash_a
~~~~~
~~~~~python
        # 5. Assert Logical State (HEAD)
        assert engine._read_head() == hash_a

    def test_capture_drift_on_detached_head(self, engine_with_repo):
        """
        A more robust regression test. Ensures capture_drift uses the HEAD
        pointer even when it's not pointing to the latest node in history.
        """
        engine = engine_with_repo
        engine.align()

        # 1. Create linear history A -> B
        (engine.root_dir / "f.txt").write_text("state A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "State A")

        (engine.root_dir / "f.txt").write_text("state B")
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")
        engine.align()  # History graph is now loaded, B is the latest node

        # 2. Checkout to the older node A. This moves the HEAD pointer.
        engine.checkout(hash_a)
        assert engine._read_head() == hash_a

        # 3. Create a new change (State C) based on State A
        (engine.root_dir / "f.txt").write_text("state C")
        hash_c = engine.git_db.get_tree_hash()

        # 4. Capture the drift. This should create Node C parented to A.
        node_c = engine.capture_drift(hash_c, message="State C")

        # 5. Assertions
        # The parent MUST be A, not B. This proves the logic reads HEAD
        # and doesn't just fall back to the "latest" node.
        assert node_c.input_tree == hash_a
        assert node_c.input_tree != hash_b
        assert node_c.output_tree == hash_c
        assert engine._read_head() == hash_c
~~~~~
