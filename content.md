好的，这是一个严重的性能问题。我将修改 `capture` 功能，限制生成的文件变更摘要的长度，以避免在面对大量文件变更时（如 Linux 内核编译后）产生数兆字节的节点文件。

## fix: 限制 `capture` 节点中文件变更摘要的长度

### 错误分析
`quipu ui` 命令在启动时，如果检测到工作区为 "DIRTY" 状态，会触发 `capture_drift` 流程来记录当前状态。此流程会调用 `git diff-tree --stat` 来生成文件变更摘要。在大型代码库（如 Linux 内核）中，一次编译可能会导致数万个文件变更，`--stat` 的输出会变得极其巨大（用户报告为 5.5MB），这导致生成的 `capture` 节点内容过大，严重影响性能和可用性。

### 用户需求
用户要求 `capture` 功能不应提取完整的文件变更列表，以避免产生巨大的节点文件。

### 评论
这是一个严重的设计疏忽。`capture` 节点中的摘要应当是“摘要”，而不是“详单”。限制其输出长度是合理的，可以显著提升在大型项目中的用户体验。

### 目标
修改 `GitDB.get_diff_stat` 方法，为 `git diff-tree --stat` 命令添加输出行数限制。

### 基本原理
利用 `git diff-tree` 命令的 `--stat` 选项的扩展语法 `--stat=,,<count>`，将输出限制在一个合理的行数内（例如 30 行）。Git 会自动在末尾添加一个“... and N more files”的摘要行，这正是我们所需要的功能。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #scope/ux #ai/instruct #task/domain/performance #task/object/capture-node #task/action/optimization #task/state/begin

---

### Script

#### Acts 1: 限制 diff-stat 输出

修改 `git_db.py` 中的 `get_diff_stat` 方法，为 `git diff-tree` 命令添加行数限制。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        """
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()
~~~~~
~~~~~python
    def get_diff_stat(self, old_tree: str, new_tree: str, count=30) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        默认限制输出为最多 30 行，以避免在有大量文件变更时生成过大的摘要。
        """
        # 使用 --stat=<width>,<name-width>,<count> 格式
        # 我们不关心 width，所以留空，只设置 count
        result = self._run(["diff-tree", f"--stat=,,{count}", old_tree, new_tree])
        return result.stdout.strip()
~~~~~

### 下一步建议
执行此计划后，可以再次尝试在 Linux 内核仓库中运行 `qs ui > o.md`，确认生成的文件大小已恢复正常。
