# test 为读取器补充 F-O-R-K 历史场景测试

## 用户需求
经过检查，现有测试覆盖了线性历史和数据损坏的场景，但遗漏了对 **分叉 (Forked) 历史** 的验证。在协作场景中，历史记录可能会出现分叉，`GitObjectHistoryReader` 必须能够正确地将它们全部加载并链接到共同的父节点上。

## 目标
在 `tests/test_storage_reader.py` 中补充一个 `test_load_forked_history` 测试用例，以确保系统的健壮性。

## 基本原理
测试将模拟一个 `A -> B` 和 `A -> C` 的分叉结构。这需要手动操作 Git 的 `refs/quipu/history` 引用来实现。

## 标签
#comp/tests #comp/engine #concept/history #scope/core

---

## Script

### Acts 1: 补充 F-O-R-K 历史测试用例

将新的测试用例追加到 `tests/test_storage_reader.py`。

~~~~~act
append_file tests/test_storage_reader.py
~~~~~

~~~~~python

    def test_load_forked_history(self, reader_setup):
        """测试：正确加载分叉的历史 A -> B and A -> C"""
        reader, writer, git_db, repo = reader_setup
        
        # 1. Create base node A
        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        (repo/"base").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", h0, hash_a, "Plan A", start_time=1000)
        commit_a = subprocess.check_output(
            ["git", "rev-parse", "refs/quipu/history"], cwd=git_db.root
        ).decode().strip()
        time.sleep(0.1)

        # 2. Create branch B (child of A)
        (repo/"file_b").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Plan B", start_time=2000)
        time.sleep(0.1)

        # 3. Create branch C (also child of A)
        # To do this, we reset the history ref back to commit_a
        git_db.update_ref("refs/quipu/history", commit_a)
        
        (repo/"file_c").touch()
        (repo/"file_b").unlink() # Make state distinct
        hash_c = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_c, "Plan C", start_time=3000)

        # Now, `git log refs/quipu/history` would show two branches from A.
        nodes = reader.load_all_nodes()
        
        assert len(nodes) == 3
        
        nodes_by_content = {n.content.strip(): n for n in nodes}
        node_a = nodes_by_content["Plan A"]
        node_b = nodes_by_content["Plan B"]
        node_c = nodes_by_content["Plan C"]
        
        # Verify parent-child links
        assert node_a.parent is None
        assert node_b.parent == node_a
        assert node_c.parent == node_a
        
        # Verify children list on the parent
        assert len(node_a.children) == 2
        # Children should be sorted by timestamp
        child_contents = [child.content.strip() for child in node_a.children]
        assert child_contents == ["Plan B", "Plan C"]
~~~~~