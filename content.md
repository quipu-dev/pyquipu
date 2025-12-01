## [COMMIT] style: 使用 ruff 格式化并检查全库代码

### 错误分析
无（这是一个主动的代码维护和质量保证操作）。

### 用户需求
使用 `ruff` 工具对当前项目的所有代码进行格式化，然后运行 Linter 检查。只有在 Linter 检查通过的情况下，才将所有变更提交到版本控制系统。

### 评论
这是一个标准的、健壮的维护任务。它将代码风格统一和代码质量检查合并为一个原子操作。通过在提交前强制执行 Linter 检查，可以确保进入版本历史的代码不仅格式统一，而且没有明显的语法或逻辑错误，极大地提升了代码库的健康度。

### 目标
1.  在项目根目录下运行 `ruff format .` 来自动修复格式问题。
2.  接着运行 `ruff check .` 来捕获任何剩余的 Linter 错误。
3.  **如果检查失败，则中止操作，不创建提交。**
4.  如果检查通过，则将所有变更的文件添加到 Git 暂存区。
5.  创建一个提交以固化格式化和修正后的变更。

### 基本原理
此计划利用了 `run_command` 指令的执行特性：当被调用的命令返回非零退出码时，它会抛出异常并终止整个计划的执行。我们将 `ruff check .` 放置在 `git_commit` 之前，使其成为一个“质量门禁”。只有当 `ruff check .` 成功（退出码为 0），执行流程才能继续到后面的 `git_add` 和 `git_commit` 步骤。

### 标签
#intent/tune #flow/ready #priority/low
#comp/build #concept/tooling #scope/dx
#ai/instruct
#task/domain/maintenance #task/object/code-style #task/action/format
#task/state/end #task/status/completed

---

### Script

#### Acts 1: 格式化代码

首先，我们运行格式化程序来自动修正所有样式问题。

~~~~~act
run_command
~~~~~
~~~~~command
.envs/dev/bin/ruff format .
~~~~~

#### Acts 2: 检查代码质量 (Linter)

接下来，我们运行 Linter 检查。**如果此命令检测到任何错误并失败，整个计划将在此处中止，不会执行后续的提交操作。**

~~~~~act
run_command
~~~~~
~~~~~command
.envs/dev/bin/ruff check .
~~~~~

#### Acts 3: 暂存并提交变更

只有在上述所有检查都通过后，才会执行以下操作，将所有变更暂存并提交。

~~~~~act
git_add
~~~~~
~~~~~files
.
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~message
style: format code with ruff

Applies standard code formatting across the entire repository using `ruff format .`.
Also ensures all linter checks pass before committing.
~~~~~

### 下一步建议
- **CI 检查**: 确保 CI 流程中包含 `ruff format --check` 和 `ruff check .` 步骤，以防止未来引入未格式化或不合格的代码。
- **Pre-commit**: 考虑配置 `pre-commit` 钩子，在每次提交前自动运行这些检查，为开发者提供更即时的反馈。
