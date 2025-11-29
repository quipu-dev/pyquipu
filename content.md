## [COMMIT] style: 使用 ruff 格式化全库代码

### 错误分析
无（这是一个主动的代码维护操作）。

### 用户需求
使用 `ruff` 工具对当前项目的所有代码进行格式化，并将变更提交到版本控制系统。

### 评论
这是一个标准的维护任务。保持代码风格的一致性对于项目的长期可维护性至关重要。将格式化操作作为一个独立的提交进行，可以避免污染包含逻辑变更的提交。

### 目标
1.  在项目根目录下运行 `ruff format .`。
2.  将所有变更的文件添加到 Git 暂存区。
3.  创建一个提交以固化格式化变更。

### 基本原理
`ruff` 是项目中配置的 Python 代码格式化工具（在 `pyproject.toml` 中定义）。通过 `run_command` 调用它不仅速度快，而且能确保应用的是项目定义的配置。

### 标签
#intent/tune #flow/ready #priority/low
#comp/build #concept/tooling #scope/dx
#ai/instruct
#task/domain/maintenance #task/object/code-style #task/action/format
#task/state/end #task/status/completed

---

### Script

#### Acts 1: 执行格式化并提交

首先运行 ruff 进行格式化，然后将变更加入暂存区并提交。

~~~~~act
run_command
~~~~~
~~~~~command
.envs/dev/bin/ruff format .
~~~~~

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
~~~~~

### 下一步建议
- **CI 检查**: 确保 CI 流程中包含 `ruff format --check` 步骤，以防止未来引入未格式化的代码。
- **Pre-commit**: 考虑配置 `pre-commit` 钩子，在每次提交前自动运行此检查。
