你的调试非常精准，直接命中了问题的核心。`log` 和 `show` 表现不一致，这清晰地指向了它们背后数据读取路径的差异，而你发现的 `🤷 此节点内部无文件内容。` 是关键症状。

### 错误分析

你的诊断是正确的。问题的根源在于我之前对 `git_db.cat_file` 方法的实现存在一个严重的缺陷。

1.  **根本原因**: `git_db.cat_file` 方法会为 `tree` 类型的对象**错误地**添加 `-p` (pretty-print) 标志。这会导致 Git 返回一个人类可读的、格式化的文本列表，而不是 `tree` 对象的原始二进制内容。
2.  **直接后果**: `GitObjectHistoryReader` 中的 `_parse_tree_binary` 函数期望接收原始的二进制数据进行解析。当它收到格式化的文本时，解析完全失败，返回一个空字典。
3.  **症状**: `show` 命令调用的 `get_node_blobs` 方法因此收到了一个空的“文件列表”，从而得出了“此节点内部无文件内容”的错误结论。
4.  **为何 `log` 正常**: `log` 命令的数据加载路径 (`load_all_nodes`) 恰好使用了 `batch_cat_file` 方法。这个批量方法返回的是正确的原始对象内容，因此它能够成功解析 `tree` 对象并构建历史图谱，这就解释了为什么 `log` 能看到节点而 `show` 看不到其内容。

这是一个典型的因底层工具函数行为不一致而导致上层逻辑出现分裂的 Bug。

### 解决方案

我将生成一个计划来修正这个问题。解决方案非常直接：移除 `git_db.cat_file` 中有问题的“智能” pretty-printing 逻辑，使其成为一个行为一致的、只返回指定对象原始内容的底层函数。

## [WIP] fix(engine): 修复 `git_db.cat_file` 以返回原始树对象内容

### 用户需求
`quipu show <HASH>` 命令无法显示节点内容，报告“此节点内部无文件内容”，尽管 `quipu log` 可以看到该节点。需要修复此问题，使 `show` 命令能正确读取并展示节点内的文件。

### 评论
这是一个关键的 Bug 修复。通过修正底层 `git_db` 的行为，我们确保了所有依赖于它的上层数据读取方法都能获得一致且正确的数据格式，从而解决了 `show` 命令的功能性障碍。

### 目标
修改 `packages/quipu-engine/src/quipu/core/git_db.py` 中的 `cat_file` 方法，移除对 `tree` 和 `commit` 对象自动添加 `-p` 标志的逻辑，使其始终返回对象的原始内容。

### 基本原理
`git cat-file <type> <hash>` 命令本身返回的就是对象的原始内容。额外的 `-p` 标志是用于人类可读的展示，不应在需要进行二进制解析的底层函数中默认使用。通过移除这个标志，我们保证了 `_parse_tree_binary` 等解析器能够接收到它们期望的正确数据格式。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #scope/core #ai/instruct #task/domain/cli #task/object/show-command #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 修正 `git_db.cat_file` 的实现

我们将直接修改 `git_db.py` 中 `cat_file` 的实现，使其变得更简单、更可靠。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def checkout_tree(self, tree_hash: str):
        """
        将工作区强制重置为目标 Tree 的状态。
        这是一个底层方法，上层应确保工作区的未提交更改已被处理。
        """
        logger.info(f"Executing hard checkout to tree: {tree_hash[:7]}")

        # 1. 使用 read-tree 更新索引，这是一个安全的操作
        self._run(["read-tree", tree_hash])

        # 2. 从更新后的索引检出文件，-a (all) -f (force)
        self._run(["checkout-index", "-a", "-f"])

        # 3. 清理工作区中多余的文件和目录
        # -d: 目录, -f: 强制
        # 移除了 -x 参数，以尊重 .gitignore 规则
        # -e .quipu: 排除 .quipu 目录，防止自毁
        self._run(["clean", "-df", "-e", ".quipu"])

        logger.info("✅ Workspace reset to target state.")

    def cat_file(self, object_hash: str, object_type: str = "blob") -> bytes:
        """读取 Git 对象的内容，返回字节流。"""
        # 使用 -p (pretty print) for commits/trees, and no flag for blobs
        cmd = ["cat-file"]
        if object_type in ["commit", "tree"]:
            cmd.append("-p")
        else:
            cmd.append(object_type)
        cmd.append(object_hash)

        result = self._run(cmd)
        return result.stdout.encode("utf-8")

    def get_blobs_from_tree(self, tree_hash: str) -> Dict[str, bytes]:
        """解析一个 Tree 对象，并返回其包含的所有 blob 文件的 {filename: content_bytes} 字典。"""
        # 1. 获取 Tree 的内容
~~~~~
~~~~~python
    def checkout_tree(self, tree_hash: str):
        """
        将工作区强制重置为目标 Tree 的状态。
        这是一个底层方法，上层应确保工作区的未提交更改已被处理。
        """
        logger.info(f"Executing hard checkout to tree: {tree_hash[:7]}")

        # 1. 使用 read-tree 更新索引，这是一个安全的操作
        self._run(["read-tree", tree_hash])

        # 2. 从更新后的索引检出文件，-a (all) -f (force)
        self._run(["checkout-index", "-a", "-f"])

        # 3. 清理工作区中多余的文件和目录
        # -d: 目录, -f: 强制
        # 移除了 -x 参数，以尊重 .gitignore 规则
        # -e .quipu: 排除 .quipu 目录，防止自毁
        self._run(["clean", "-df", "-e", ".quipu"])

        logger.info("✅ Workspace reset to target state.")

    def cat_file(self, object_hash: str, object_type: str) -> bytes:
        """
        读取 Git 对象的原始内容，返回字节流。
        移除了有问题的 pretty-printing 逻辑，以确保二进制解析器正常工作。
        """
        cmd = ["cat-file", object_type, object_hash]
        result = self._run(cmd)
        return result.stdout.encode("utf-8")

    def get_blobs_from_tree(self, tree_hash: str) -> Dict[str, bytes]:
        """解析一个 Tree 对象，并返回其包含的所有 blob 文件的 {filename: content_bytes} 字典。"""
        # 1. 获取 Tree 的内容
~~~~~

### 下一步建议
应用此修复后，`show` 命令应该就能正确解析 `tree` 对象并显示其内容了。请再次运行 `qd show adcef0a` 进行验证。
