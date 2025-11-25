# chore 提交双环境旁路开发基础设施

## 目标
将已完成并验证通过的双环境开发基础设施相关文件提交到版本控制。

## 基本原理
通过 `git add` 和 `git commit` 命令，将本次重构工作固化为一个原子提交。提交信息应清晰地阐述本次变更的目的和内容，即引入了 `qx` (Stable) 和 `qd` (Dev) 的双环境工作流，以解决自举开发中的死锁问题。

## 标签
 #chore #infra #workflow

---

## Script

### Act 1: 暂存所有变更

将新创建的 `bootstrap.py`, `dev_setup.sh`, `verify_sandbox.py`, `DEVELOPING.md` 以及修改后的 `.gitignore` 和 `pyproject.toml` 文件暂存。

~~~~~act
git_add .
~~~~~

### Act 2: 提交变更

创建一次提交，记录本次对开发工作流的重大改进。

~~~~~act
git_commit
~~~~~

~~~~~text
chore(dev): 建立双环境旁路开发工作流

引入基于 uv 的双虚拟环境系统，以解决自举开发过程中的“工具-对象同一性”问题。

- **Stable 环境 (`qx`)**: 作为静态快照工具，用于执行 `Plan.md`，保证开发过程的稳定性。
- **Dev 环境 (`qd`)**: 作为源码的动态链接，用于运行测试和在沙盒中验证新功能。

- 添加 `bootstrap.py` 用于自动化环境的创建和晋升 (`qpromote`)。
- 添加 `dev_setup.sh` 与 `dev_setup.fish` 用于激活 `qx` 和 `qd` 别名。
- 添加 `verify_sandbox.py` 用于安全地集成测试 Dev 环境。
- 更新 `pyproject.toml` 文件以支持 `uv` 的 Workspace 依赖解析。
~~~~~