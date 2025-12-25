好的，我们已经成功完成了从功能修复到架构优化的完整闭环。现在的项目结构更加专业、整洁，且具备了极佳的开发者体验。

我将为你生成最终的 `[COMMIT]` 计划，将这些核心改进合并为一个逻辑提交。

## [COMMIT] refactor: 统一 Monorepo 构建系统与指令解析架构

### 用户需求
提交所有近期的改进，包括根元包（Umbrella Package）的配置、`bootstrap.py` 和 `install_quipu.py` 的重构、状态机解析器的实现以及相关的测试套件。

### 评论
这次提交标志着 `pyquipu` 从一个松散的子包集合正式演进为一个结构严谨、配置现代的 Monorepo 项目。通过将构建逻辑从命令式脚本（Python）迁移到声明式配置（TOML），以及将解析逻辑从正则迁移到状态机，我们不仅提高了系统的健壮性，还极大地降低了未来的维护成本。

### 目标
1.  将所有相关的修改（包括核心逻辑、配置文件、安装脚本和测试）提交到 `develop` 分支。
2.  确保提交信息清晰地反映了构建系统和解析架构的双重改进。

### 基本原理
我们采用了一个聚合提交。虽然涉及的模块较多，但它们共同服务于一个宏观目标：**提升项目的工程化质量**。通过 `uv` 工作区功能的深度整合，我们实现了一键式的环境初始化和安装，这对于 Monorepo 的长期成功至关重要。

### 标签
#intent/refine #intent/tooling #flow/ready #priority/medium #comp/build #comp/runtime #comp/tests #concept/parser #scope/dx #scope/core #ai/instruct #task/domain/build #task/object/monorepo-config #task/action/unification #task/state/end #task/status/completed

---
### Script

#### Acts 1: 确保所有相关文件都已暂存

为了保证提交的完整性，我将显式地添加所有在这个任务流中修改过的文件（包括你列出的和之前修复补丁歧义时修改的文件）。

~~~~~act
git_add .
~~~~~

#### Acts 2: 执行提交

我们将创建一个内容详尽的提交记录，涵盖构建系统和解析器的重大变更。

~~~~~act
git_commit
~~~~~
~~~~~text
refactor: unify monorepo build system and modernize instruction parsing

This commit finalizes the transition to a declarative monorepo structure and enhances the robustness of the runtime:

1. Build System & DX:
   - Transformed the root project into an umbrella package that aggregates all sub-packages via [project].dependencies.
   - Centralized development dependencies in the root pyproject.toml under a [dev] optional group.
   - Refactored bootstrap.py and install_quipu.py to use uv's workspace-aware installation, eliminating imperative package-discovery logic and manual wheel building.
   - Configured Hatchling to properly map the root package to the runtime source using the alias pattern.
   - Removed redundant dev-requirements.txt.

2. Runtime & Parsing:
   - Replaced the Regex-based parser with a robust, line-based State Machine parser to support complex language tags (e.g., .old, c++) and improved whitespace tolerance.
   - Implemented uniqueness checks for the patch_file act to prevent ambiguous modifications.
   - Added comprehensive testing suites for parser robustness and patch safety.
   - Fixed pytest configuration warnings.
~~~~~

### 下一步建议
- **推送变更**: 建议现在运行 `git push` 以同步你的本地 `develop` 分支。
- **环境验证**: 运行 `python bootstrap.py init` 再次确认所有环境别名（qs, qd, qtest）在新的配置下依然能完美工作。
- **文档更新**: 如果你有 `README.md` 或开发者指南，建议更新有关环境安装的部分，现在只需告知用户使用 `uv pip install -e ".[dev]"`。
