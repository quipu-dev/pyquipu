# chore: 为持久化忽略规则功能创建提交

## 目标
将最近实现和测试的“持久化本地忽略规则”功能提交到版本历史中。

## 基本原理
我们已经成功实现了利用 `.git/info/exclude` 来保护本地开发环境文件的功能，并为其编写了相应的单元测试。现在，我们将这些变更暂存并创建一个规范的 Git 提交。

## 标签
#chore #git

---

## Script

### Act 1: 暂存所有相关变更

将 `quipu-engine` 的代码修改和新增的测试用例添加到暂存区。

~~~~~act
git_add .
~~~~~

### Act 2: 创建 Git 提交

使用标准的 Conventional Commits 格式创建一条清晰的提交信息，以记录本次功能的添加。

~~~~~act
git_commit
~~~~~

~~~~~text
feat(core): 实现持久化忽略规则以保护本地环境

修复了 `quipu checkout` 或 `quipu discard` 命令可能会误删被 `.gitignore` 忽略的本地开发环境文件（如 `.envs/`, `.idea/`, `o.md` 等）的问题。

根本原因在于 `git clean` 命令会受到不同历史版本中 `.gitignore` 文件的影响。

此提交通过引入一个基于 Git 标准特性 `.git/info/exclude` 的新机制来解决该问题：

1.  在 `.quipu/config.yml` 中新增 `sync.persistent_ignores` 配置项，并提供了一组常用默认值。
2.  `Engine` 在初始化时会自动读取此配置，并将其同步到一个在 `.git/info/exclude` 文件中由 Quipu 管理的代码块。
3.  由于 `.git/info/exclude` 文件独立于项目历史，因此其中定义的规则能在所有 `checkout` 操作中持久生效，从而为本地环境文件提供了可靠的保护。

此方案将项目级的忽略规则 (`.gitignore`) 与开发者本地的忽略规则 (`.git/info/exclude`) 进行了有效分离。
~~~~~