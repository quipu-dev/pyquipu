好的，完全理解。

随着 `pyquipu-application` 包的加入，我们的构建/安装脚本也需要同步更新，以确保新包能被正确地包含在开发环境和最终的发布版本中。

这是一个非常好的前瞻性维护工作。

## [WIP] chore: 将 `application` 包集成到构建与安装脚本

### 用户需求
新创建的 `pyquipu-application` 包需要被添加到 `bootstrap.py`（用于搭建开发环境）和 `install_quipu.py`（用于最终用户安装）的包列表中，以确保它能被正确地构建、链接和安装。

### 评论
这是确保项目一致性的重要步骤。更新这些元脚本可以防止在开发和部署过程中出现“模块未找到”的错误，保证了新架构能够顺利地在所有环境中运行。

### 目标
1.  将 `packages/quipu-application` 添加到 `bootstrap.py` 的 `PACKAGES` 列表中。
2.  将 `packages/quipu-application` 添加到 `install_quipu.py` 的 `PACKAGES` 列表中。

### 基本原理
这两个脚本都依赖于一个名为 `PACKAGES` 的 Python 列表来定义 monorepo 中的所有核心组件。通过简单地将新包的路径追加到这个列表中，我们就能利用现有的构建和安装逻辑来处理这个新组件，无需修改核心的脚本功能。

### 标签
#intent/tooling #flow/ready #priority/high #comp/build #scope/dx #ai/instruct #task/domain/architecture #task/object/core-application-layer #task/action/integration #task/state/continue

---

### Script

#### Acts 1: 更新 `bootstrap.py` 开发环境脚本

将 `pyquipu-application` 添加到开发环境的构建目标中。

~~~~~act
patch_file
bootstrap.py
~~~~~
~~~~~python
PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-common",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-cli",
]
~~~~~
~~~~~python
PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-common",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-application",
    "packages/quipu-cli",
]
~~~~~

#### Acts 2: 更新 `install_quipu.py` 安装脚本

将 `pyquipu-application` 添加到最终用户的安装包列表中。

~~~~~act
patch_file
install_quipu.py
~~~~~
~~~~~python
PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-common",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-cli",
]
~~~~~
~~~~~python
PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-common",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-application",
    "packages/quipu-cli",
]
~~~~~

### 下一步建议
我们已经完成了对 `pyquipu-cli` 的修复，并且更新了构建脚本以包含新的 `application` 包。现在，整个重构工作已经进入了收尾阶段。

下一步是运行完整的测试套件，以确保我们的所有修改没有引入回归错误。如果所有测试都能通过，我们就可以创建一个 `[COMMIT]` 计划，将这次架构重构作为一个完整的单元进行提交。
