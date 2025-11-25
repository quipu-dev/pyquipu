# fix-test: 修正导航测试中创世节点的命名规范

## 用户需求
`test_cli_back_forward_flow` 测试用例失败，原因是测试夹具创建了一个文件名不符合 `history.py` 解析器规范的创世历史节点，导致 `checkout` 操作无法找到目标节点。

## 评论
这是一个数据一致性的问题。历史节点的创建方 (测试夹具) 和读取方 (解析器) 对创世节点的 `input_tree` 格式有不同的理解。修复这个问题可以保证系统内部规范的统一。

## 目标
修改 `tests/test_navigation.py` 中的 `cli_workspace` 夹具，使其使用 `_` * 40 作为创世节点的 `input_tree`，以生成符合解析器规范的文件名。

## 基本原理
`history.py` 中的 `FILENAME_PATTERN` 正则表达式是历史文件命名的权威标准。所有生成历史文件的代码，包括测试代码，都必须遵守此标准。

## 标签
#fix #test #engine

---

## Script

### Acts 1: 修正测试夹具

将 `tests/test_navigation.py` 中创建创世节点时使用的 `input_tree` 从 `"root"` 修改为 `_` * 40。

~~~~~act
replace
~~~~~

~~~~~path
tests/test_navigation.py
~~~~~

~~~~~python
        # Create some history nodes for checkout
        engine = Engine(ws)
        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("root", hash_a, "State A")

        (ws / "b.txt").write_text("B")
~~~~~

~~~~~python
        # Create some history nodes for checkout
        engine = Engine(ws)
        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("_" * 40, hash_a, "State A")

        (ws / "b.txt").write_text("B")
~~~~~