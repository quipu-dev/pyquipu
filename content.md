好的，我用最通俗的自然语言来复盘一下刚才发生了什么，以及为什么“看似正确”的修复依然失败。

### 现场还原：为什么会失败？

想象 **Git 索引 (Index)** 是一个“发货清单”，而 **工作区 (Workspace)** 是实际的“仓库货架”。

1.  **初始状态**:
    *   **货架 (工作区)** 上有一件商品 `ci.yml`，但它被弄脏了（你有未提交的修改，或者它被脚本修改了）。
    *   **清单 (索引)** 此时可能也是乱的。

2.  **第一步 (你的修复 - `read-tree <old>`)**:
    *   你强行把 **清单** 撕掉，换成了一张旧的、标准的清单 A (`old_tree`)。
    *   **关键点**: 这一步只换了**清单**。**货架**上的 `ci.yml` 还是脏的！
    *   现在的局面是：清单上写着 `ci.yml (标准版)`，但货架上放着 `ci.yml (脏版)`。

3.  **第二步 (报错点 - `read-tree -m <old> <new>`)**:
    *   这个命令试图计算从 A 到 B 的差异。
    *   Git 非常谨慎。它在计算差异前，会先看一眼货架。
    *   它发现：**“不对啊！清单上说这里是标准版，怎么货架上是脏版？如果我执行合并，这个脏版可能会丢失！”**
    *   于是 Git 抛出错误 `Entry ... not uptodate`，拒绝执行。即使我们的目的是“强制覆盖”，但 `-m` 模式（合并模式）本质上是用来保护数据的，它不接受这种不一致。

### 真正的解决方案：殊途同归

我们在追求“性能优化”时，陷入了过度使用底层命令 (`read-tree -m` + `checkout-index`) 的陷阱。

其实，Git 提供了一个命令，它专门用来做**“带优化的强制切换”**，即：
**`git read-tree --reset -u <new_tree>`**

*   **`--reset`**: 告诉 Git，“闭嘴，我不关心货架上有什么脏东西，也不关心清单对不对，全部以新清单为准。”（解决了报错问题）
*   **`-u` (Update)**: 告诉 Git，“不仅要换清单，还要同步更新货架。”
*   **核心优化**: 这个命令非常智能。它会对比**当前清单**和**新清单**。如果某件商品在两个清单里的哈希值一样，它就**完全不碰**货架上的那件商品（保留其修改时间，不执行 I/O）。**这正是我们梦寐以求的性能优化。**

所以，我们不需要 `old_tree`，也不需要复杂的两步走。我们只需要这一个命令。

## [WIP] fix: 使用 read-tree --reset -u 替代脆弱的差异合并逻辑

### 用户需求
修复 `checkout` 操作在工作区不干净时崩溃的问题。之前的修复尝试（分步重置索引）未能解决 `read-tree -m` 对工作区状态的严格检查导致的 `not uptodate` 错误。

### 目标
1.  彻底抛弃 `read-tree -m <old> <new>` 这种脆弱的合并逻辑。
2.  使用 `git read-tree --reset -u <new_tree>` 作为核心实现。
3.  这个命令同时实现了：
    *   **强制性**: `--reset` 忽略并覆盖本地变更，解决崩溃问题。
    *   **高性能**: `-u` 自动比对索引，跳过未变更文件的 I/O 操作。
4.  保留 `git clean` 以清理未追踪的文件。

### 基本原理
`git read-tree --reset -u` 是 Git 提供的“官方”快速检出路径。它利用当前索引作为缓存，只更新那些在当前索引和目标 Tree 之间确实发生变化的文件。由于它带有 `--reset` 语义，它不会因为工作区的“脏”状态而中止，完全符合 Quipu 时间旅行“强制切换”的定义。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #scope/core #ai/instruct #task/domain/storage #task/object/checkout-performance #task/action/optimization #task/state/end #task/status/completed

---

### Script

#### Acts 1: 重写 `checkout_tree`

我们不仅修复了 bug，还删除了复杂的 `old_tree_hash` 逻辑，使代码更简洁、更健壮。

~~~~~act
patch_file
packages/quipu-engine/src/pyquipu/engine/git_db.py
~~~~~
~~~~~python
    def checkout_tree(self, new_tree_hash: str, old_tree_hash: Optional[str] = None):
        """
        将工作区强制重置为目标 Tree 的状态。
        如果提供了 old_tree_hash，将执行 tree-vs-tree 高效 diff，只更新变更文件。
        否则，回退到全量更新。
        """
        bus.info("engine.git.info.checkoutStarted", short_hash=new_tree_hash[:7])

        # 1. 更新索引。根据是否存在 old_tree_hash 选择不同策略。
        if old_tree_hash and old_tree_hash != new_tree_hash:
            # 快速路径: tree-vs-tree diff, 只更新索引中的差异项
            logger.debug(f"执行 tree-vs-tree 高效检出: {old_tree_hash[:7]} -> {new_tree_hash[:7]}")
            
            # 阶段 1.1: 强制将索引重置到 old_tree 的状态。
            # 这解决了 "Entry not uptodate" 问题，确保合并基础是绝对干净和已知的。
            self._run(["read-tree", old_tree_hash])
            
            # 阶段 1.2: 在干净的索引上执行 diff-merge，将其更新到 new_tree 的状态。
            self._run(["read-tree", "-m", old_tree_hash, new_tree_hash])
        else:
            # 慢速路径 或 原地切换: 将整个新 tree 读入索引
            logger.debug(f"执行全量检出: {new_tree_hash[:7]}")
            self._run(["read-tree", new_tree_hash])

        # 2. 从更新后的索引检出文件，-a (all) -f (force)
        # 此时 checkout-index 只会操作在 read-tree 步骤中被标记为已更改的文件
        self._run(["checkout-index", "-a", "-f"])

        # 3. 清理工作区中多余的文件和目录
        # -d: 目录, -f: 强制
        # 移除了 -x 参数，以尊重 .gitignore 规则
        # -e .quipu: 排除 .quipu 目录，防止自毁
        self._run(["clean", "-df", "-e", ".quipu"])

        bus.success("engine.git.success.checkoutComplete")
~~~~~
~~~~~python
    def checkout_tree(self, new_tree_hash: str, old_tree_hash: Optional[str] = None):
        """
        将工作区强制重置为目标 Tree 的状态。
        使用 read-tree --reset -u 实现高性能的增量更新。
        """
        bus.info("engine.git.info.checkoutStarted", short_hash=new_tree_hash[:7])

        # 1. 高性能检出核心
        # --reset: 类似于 git reset --hard，强制覆盖本地未提交的变更，解决 "not uptodate" 冲突。
        # -u: 更新工作区文件。Git 会自动对比当前索引，只对发生变更的文件执行 I/O (更新 mtime)。
        # 这就是我们要的 "tree-vs-tree" 优化，不需要手动传入 old_tree_hash，因为当前索引就是 old_tree。
        logger.debug(f"执行优化的强制检出: -> {new_tree_hash[:7]}")
        self._run(["read-tree", "--reset", "-u", new_tree_hash])

        # 2. 清理工作区中多余的文件和目录
        # read-tree -u 会删除旧树中有但新树中没有的文件。
        # 但它不会删除 "未追踪 (Untracked)" 的新文件。我们需要用 clean 来处理它们。
        # -d: 目录, -f: 强制
        # -e .quipu: 排除 .quipu 目录，防止自毁
        self._run(["clean", "-df", "-e", ".quipu"])

        bus.success("engine.git.success.checkoutComplete")
~~~~~
