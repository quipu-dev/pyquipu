好的，我们已经完成了对 `bootstrap.py` 脚本的改进和修复。现在，我将创建一个 Git 提交来将这些变更固化到版本历史中。

## [COMMIT] feat(build): 改进 bootstrap 脚本，支持自动发现和 dev-only 更新

### 用户需求
需要将对 `bootstrap.py` 脚本的一系列改进（包的自动发现、新增 `dev` 更新命令、移除别名脚本生成）以及后续的构建命令修复，作为一个完整的逻辑单元提交到版本控制中。

### 评论
这次提交将显著提升项目的开发者体验。通过使 `bootstrap.py` 更加自动化和灵活，开发者可以更快速地适应项目结构的变化，而无需手动维护脚本，同时也修复了一个关键的构建错误，确保了 `stable` 环境的可靠性。

### 目标
1.  将 `bootstrap.py` 文件的最新版本添加到 Git 暂存区。
2.  创建一个符合 Conventional Commits 规范的 Git 提交。

### 基本原理
通过创建一个原子性的提交，我们将所有相关的改进和修复捆绑在一起。这使得版本历史清晰可读，便于未来追溯每次变更的完整上下文和动机。提交信息将详细描述所做的三项主要改进和一个关键修复。

### 标签
#intent/build #flow/ready #priority/high #comp/build #scope/dx #ai/instruct #task/domain/tooling #task/object/bootstrap-script #task/action/refactor #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交对 bootstrap.py 的所有改进

我们将暂存 `bootstrap.py` 文件并创建一个包含详细说明的提交。

~~~~~act
git_add
bootstrap.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
feat(build): improve bootstrap script with auto-discovery and dev-only updates

This commit introduces several developer experience improvements to the `bootstrap.py` script and fixes a critical build regression.

Key changes:
- **Package Auto-Discovery**: The script now automatically scans the `packages/` directory to find valid packages, removing the need to manually maintain the `PACKAGES` list.
- **`dev` Command**: A new `python bootstrap.py dev` command has been added to only update the development environment. This allows for quick updates after adding new packages without rebuilding the entire stable environment.
- **Removed Script Generation**: The automatic generation of `dev_setup.sh` and `dev_setup.fish` has been removed to give developers more control over their shell configurations.
- **Fix**: Reverted the wheel-building command from `uv pip wheel` back to `uv build`. This fixes a `CalledProcessError` that occurred during the `init` and `promote` commands, ensuring the stable environment builds reliably.
~~~~~
