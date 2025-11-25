# refactor: 将核心模块物理拆分为独立的包

## 目标
根据重构手册的阶段 2 规划，将 `core/` 目录以及根目录下的相关文件，物理迁移到 `packages/` 目录下，形成 `quipu-interfaces`、`quipu-engine`、`quipu-runtime` 和 `quipu-cli` 四个独立的 Python 包。

## 基本原理
这是“星座模型”架构的核心步骤。通过将不同职责的代码物理隔离到独立的包中，我们强制执行了模块间的依赖关系，消除了循环引用的可能性，并为每个组件的独立发布和测试奠定了基础。文件名中的前缀 (如 `intf_`, `eng_`) 在迁移后被移除，恢复了它们在各自包内的标准命名。

## 标签
完成核心模块的重构。 #refactor #core #packages

---

## Script

### Act 1: 迁移接口包 (quipu-interfaces)

将所有 `intf_` 前缀的接口定义文件移动到 `quipu-interfaces` 包中，并移除前缀。

~~~~~act
move_file core/intf_exceptions.py packages/quipu-interfaces/src/quipu/core/exceptions.py
~~~~~

~~~~~act
move_file core/intf_models.py packages/quipu-interfaces/src/quipu/core/models.py
~~~~~

~~~~~act
move_file core/intf_result.py packages/quipu-interfaces/src/quipu/core/result.py
~~~~~

~~~~~act
move_file core/intf_types.py packages/quipu-interfaces/src/quipu/core/types.py
~~~~~

### Act 2: 迁移引擎包 (quipu-engine)

将所有 `eng_` 前缀的状态与历史引擎文件移动到 `quipu-engine` 包中，并移除前缀。

~~~~~act
move_file core/eng_config.py packages/quipu-engine/src/quipu/core/config.py
~~~~~

~~~~~act
move_file core/eng_git_db.py packages/quipu-engine/src/quipu/core/git_db.py
~~~~~

~~~~~act
move_file core/eng_history.py packages/quipu-engine/src/quipu/core/history.py
~~~~~

~~~~~act
move_file core/eng_state_machine.py packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~

### Act 3: 迁移运行时包 (quipu-runtime)

将所有 `rt_` 前缀的解析与执行文件移动到 `quipu-runtime` 包中，并移除前缀。

~~~~~act
move_file core/rt_executor.py packages/quipu-runtime/src/quipu/core/executor.py
~~~~~

~~~~~act
move_file core/rt_parser.py packages/quipu-runtime/src/quipu/core/parser.py
~~~~~

~~~~~act
move_file core/rt_plugin_loader.py packages/quipu-runtime/src/quipu/core/plugin_loader.py
~~~~~

### Act 4: 迁移 CLI 包 (quipu-cli)

将控制器、主入口及相关配置文件移动到 `quipu-cli` 包中。

~~~~~act
move_file core/cli_controller.py packages/quipu-cli/src/quipu/cli/controller.py
~~~~~

~~~~~act
move_file main.py packages/quipu-cli/src/quipu/cli/main.py
~~~~~

~~~~~act
move_file config.py packages/quipu-cli/src/quipu/cli/config.py
~~~~~

~~~~~act
move_file logger_config.py packages/quipu-cli/src/quipu/cli/logger_config.py
~~~~~