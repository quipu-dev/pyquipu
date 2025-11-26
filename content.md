# chore: 创建提交

## 用户需求
你已确认之前的重构方案测试通过，并指示我将这些变更创建为一个 Git 提交。

## 评论
这是一个标准的工作流程，用于将已验证的逻辑变更固化到版本历史中。

## 目标
创建一个 Git 提交，清晰地记录本次对摘要生成逻辑的重构。

## 基本原理
使用 `git_add` 将修改过的文件暂存，然后使用 `git_commit` 并附上描述性的提交信息来创建提交。提交信息将直接引用我们上一个计划的核心目标。

## 标签
#intent/tooling #flow/ready #priority/high
#comp/build
#scope/dx
#ai/instruct

---

## Script

### Acts 1: 暂存文件

首先，将两个被修改的文件添加到 Git 暂存区。

~~~~~act
git_add packages/quipu-cli/src/quipu/cli/controller.py packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~

### Acts 2: 执行提交

现在，创建提交。提交信息的主题和正文详细说明了本次重构的目的和实现方式。

~~~~~act
git_commit
~~~~~
~~~~~message
refactor: 调整 Plan 摘要生成逻辑，优先使用文档标题

修改摘要生成逻辑，使其遵循以下优先级顺序：

1.  **最高优先级**：使用 `plan` 内容中的 Markdown 标题 (`# ...`) 作为摘要。
2.  **次高优先级**：如果找不到标题，则回退到从第一个 `act` 指令生成的摘要。
3.  **最终回退**：如果以上都失败，则使用计划内容的第一行文本。

这将摘要生成的决策逻辑集中到 `quipu-cli` 的 `controller.py` 中，同时简化了 `quipu-engine` 的 `writer` 模块。
~~~~~
