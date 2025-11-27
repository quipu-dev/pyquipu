这是一个修复 `bootstrap.py` 脚本的计划。

## fix(build): 修复 bootstrap 脚本未包含 quipu-common 的问题

### 错误分析
`bootstrap.py` 脚本用于创建隔离的 `stable` 环境。它通过一个内部定义的包列表来构建 Wheels 并进行安装。在创建 `quipu-common` 包后，未能将这个新包添加到该列表中，导致在安装 `quipu-engine` 时，其对 `quipu-common` 的依赖无法被解析，从而引发 `No solution found` 错误。

### 用户需求
`python bootstrap.py init` 命令必须能够成功执行，正确地构建并安装包括 `quipu-common` 在内的所有本地工作区包。

### 评论
这是一个构建脚本与项目依赖图不同步的典型问题。修复方法很直接：更新构建脚本，使其“知晓”新包的存在。

### 目标
修改 `bootstrap.py` 脚本，将 `packages/quipu-common` 添加到其编译和安装的目标列表中。

### 基本原理
`stable` 环境的安装过程是一个隔离的事务，它依赖于一组预先构建好的 Wheel 文件。为了让依赖解析器 (`uv`) 能够成功，所有本地相互依赖的包都必须被编译成 Wheel，并在同一次 `uv pip install` 命令中提供。

### 标签
#intent/fix #flow/ready #priority/critical #comp/build #scope/dx #ai/instruct #task/domain/sync #task/object/identity-management #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 更新 `bootstrap.py` 中的包列表

我们将 `quipu-common` 添加到待处理的包列表中。为了保持良好的依赖顺序，我们将其放在依赖它的 `engine` 和 `cli` 之前。

~~~~~act
patch_file
bootstrap.py
~~~~~
~~~~~python
PACKAGES = [
    "packages/quipu-interfaces",
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
    "packages/quipu-cli",
]
~~~~~

### 下一步建议
1.  保存对 `bootstrap.py` 的修改。
2.  再次运行 `python bootstrap.py init`。
3.  这次，你应该会看到 `quipu-common` 也被编译成 Wheel，并且 `uv` 安装过程会顺利完成。
