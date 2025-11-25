# fix: 修复 GitDB 底层方法实现及测试用例

## 用户需求
在执行了 `feat: 增强 GitDB 以支持底层对象操作` 计划后，单元测试暴露出四个失败用例。这表明新添加的底层方法实现或相关的测试代码存在缺陷。我们需要立即修复这些问题，以确保 `GitDB` 模块的健壮性和正确性。

## 评论
测试失败是重构过程中的正常现象，它精确地指出了我们代码中的问题所在：
1.  `hash_object` 方法中向 `subprocess` 传递参数的格式不正确，导致 Git 命令执行失败。
2.  重命名 `create_anchor_commit` 为 `commit_tree` 后，未能同步更新所有调用该方法的测试文件，导致了 `AttributeError`。

通过修复这些问题，我们可以确保新的 Git 底层接口按预期工作，为后续的存储层改造打下坚实的基础。

## 目标
1.  修正 `git_db.py` 中 `hash_object` 方法的参数传递逻辑。
2.  更新 `tests/test_engine.py` 中对旧 commit 方法的调用，使其适配新的 `commit_tree` 接口。
3.  更新 `tests/test_git_db.py`，将针对 `create_anchor_commit` 的测试重构为针对 `commit_tree` 的测试。
4.  确保所有单元测试都能成功通过。

## 基本原理
本次修复遵循“发现问题 -> 定位根源 -> 修正代码 -> 验证修复”的标准流程。
*   对于 `hash-object` 的错误，我们将 `f"-t={object_type}"` 拆分为两个独立的列表元素 `["-t", object_type]`，这是向 `subprocess.run` 传递带值的命令行选项的标准做法。
*   对于 `AttributeError`，我们将逐一检查测试代码，将所有对 `create_anchor_commit` 的调用替换为对 `commit_tree` 的调用，并根据新的函数签名 (`parent_hashes`, `message`) 调整传入的参数。

## 标签
#fix #comp/engine #comp/tests #concept/state

---

## Script

### Acts 1: 修正 `hash_object` 方法

第一个修复是针对 `git hash-object` 命令的参数格式问题。我们将 `-t={type}` 拆分为两个独立的参数。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
        try:
            result = subprocess.run(
                ["git", "hash-object", "-w", f"-t={object_type}", "--stdin"],
                cwd=self.root,
                input=content_bytes,
~~~~~
~~~~~python
        try:
            result = subprocess.run(
                ["git", "hash-object", "-w", "-t", object_type, "--stdin"],
                cwd=self.root,
                input=content_bytes,
~~~~~

### Acts 2: 修复 `test_engine.py` 中的方法调用

接下来，修复 `test_engine.py` 中因方法重命名导致的 `AttributeError`。

~~~~~act
replace
~~~~~
~~~~~path
tests/test_engine.py
~~~~~
~~~~~python
    engine.writer.create_node("plan", "_" * 40, initial_hash, "Initial content")
    
    initial_commit = engine.git_db.create_anchor_commit(initial_hash, "Initial")
    engine.git_db.update_ref("refs/quipu/history", initial_commit)
    
    # 重新对齐以加载我们刚刚手动创建的节点
~~~~~
~~~~~python
    engine.writer.create_node("plan", "_" * 40, initial_hash, "Initial content")
    
    initial_commit = engine.git_db.commit_tree(initial_hash, parent_hashes=None, message="Initial")
    engine.git_db.update_ref("refs/quipu/history", initial_commit)
    
    # 重新对齐以加载我们刚刚手动创建的节点
~~~~~

### Acts 3: 修复 `test_git_db.py` 中的测试用例

最后，修复 `test_git_db.py` 中同样由于方法重命名导致的 `AttributeError`。

~~~~~act
replace
~~~~~
~~~~~path
tests/test_git_db.py
~~~~~
~~~~~python
    def test_anchor_commit_persistence(self, git_repo, db):
        """测试：创建影子锚点"""
        (git_repo / "f.txt").write_text("content")
        tree_hash = db.get_tree_hash()
        
        # 创建锚点
        commit_hash = db.create_anchor_commit(tree_hash, "Axon Shadow Commit")
        
        # 更新引用
        ref_name = "refs/quipu/history"
~~~~~
~~~~~python
    def test_anchor_commit_persistence(self, git_repo, db):
        """测试：创建影子锚点"""
        (git_repo / "f.txt").write_text("content")
        tree_hash = db.get_tree_hash()
        
        # 创建锚点
        commit_hash = db.commit_tree(tree_hash, parent_hashes=None, message="Axon Shadow Commit")
        
        # 更新引用
        ref_name = "refs/quipu/history"
~~~~~