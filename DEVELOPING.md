# Quipu 开发指南 (The Quipu Bootstrap Workflow)

本文档介绍了如何在一个“依靠 Quipu 构建 Quipu”的自举环境中安全、高效地工作。

## 核心概念：双环境旁路 (Dual-Environment Bypass)

为了解决“修改工具本身会导致工具崩溃”的死锁问题，我们维护了两个隔离的环境：

1.  **🔵 Stable 环境 (`qx`)**:
    *   **角色**: 医生/生产者。
    *   **本质**: 上一次成功构建的代码的**静态快照**。
    *   **用途**: **你的生产力工具**。用它来生成代码、重构文件、执行 Act。它不会受你正在编辑的源码中的语法错误影响。
2.  **🟢 Dev 环境 (`qd`)**:
    *   **角色**: 病人/被测对象。
    *   **本质**: 当前源码的**动态链接** (`pip install -e`)。
    *   **用途**: **你的测试对象**。用它来跑测试、手动调试、验证新功能。它实时反映源码的修改。

---

## 快速开始

### 1. 初始化环境

首次克隆项目后，在根目录执行：

```bash
# 1. 安装 uv (如果尚未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 构建双环境
python3 bootstrap.py init

# 3. 激活别名 (建议加入 .bashrc 或 .zshrc)
source dev_setup.sh
```

对于 fish：

```
# 激活别名 (建议加入 .config/fish/config.fish)
source dev_setup.fish
```

### 2. 常用命令速查

| 别名 | 完整命令 | 用途 |
| :--- | :--- | :--- |
| **`qx`** | `.envs/stable/bin/quipu` | **执行工具**。用这个来跑 `Plan.md` 修改代码。 |
| **`qd`** | `.envs/dev/bin/quipu` | **调试对象**。用这个来手动测试新功能（配合沙盒）。 |
| **`qtest`** | `.envs/dev/bin/pytest` | **运行测试**。运行项目的单元/集成测试。 |
| **`qpromote`** | `python bootstrap.py promote` | **晋升**。将当前的 Dev 源码打包刷新到 Stable 环境。 |

---

## 标准开发循环 (The Loop)

### 场景 A：常规功能开发

1.  **编写计划**: 创建 `feat_xxx.md`。
2.  **执行修改**: 使用 **Stable** 环境执行计划。
    ```bash
    qx run feat_xxx.md
    ```
3.  **验证**: 使用 **Dev** 环境运行测试。
    ```bash
    qtest tests/test_new_feat.py
    ```
4.  **晋升**: 测试通过后，刷新工具链，使新功能在 `qx` 中可用。
    ```bash
    qpromote
    ```

### 场景 B：核心重构 (高风险)

当你修改 `Engine` 或 `Runtime` 核心逻辑时，可能会破坏 `.quipu` 数据结构。

1.  **执行修改**: `qx run refactor_core.md`
2.  **单元测试**: `qtest`
3.  **沙盒验证**: **严禁**直接运行 `qd run`，这会破坏项目根目录的 `.quipu`。请运行：
    ```bash
    python3 verify_sandbox.py
    ```
    该脚本会在 `sandbox/` 目录中隔离运行 `qd`，确保新逻辑能正常工作且不污染环境。
4.  **晋升**: `qpromote`

---

## 故障排除

### Q: 我把代码改坏了，`qd` 报错，但我需要用 Quipu 来修复它。
**A**: 这正是双环境存在的意义！`qx` 是独立的静态副本，它**没有坏**。你可以继续使用 `qx run fix_bug.md` 来修复源代码。

### Q: 我不小心执行了 `qpromote`，把坏掉的代码同步到了 `qx`，现在两个都坏了！
**A**:
1.  **Git 回滚**: 使用 `git checkout` 或使用 `axon ui` 恢复源码到上一个好状态。
2.  **再次晋升**: 运行 `qpromote`。这会将回滚后的好代码重新安装到 `qx`。

### Q: `qtest` 找不到我新加的包？
**A**: 如果你添加了新的 `packages/` 子目录，需要重新运行 `python3 bootstrap.py init` 来注册新的 Editable Install。
