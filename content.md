# fix 修复步骤 1.3 运行时层重构的中断问题

## 目标
继续完成步骤 1.3 的重构工作。由于文件重命名（Act 1-3）已经成功执行，本计划将专注于修复代码中的导入路径，以恢复系统功能。

## 基本原理
上一次执行在修改 `core/rt_executor.py` 时失败，原因是该文件并不包含需要修改的引用。这导致后续的引用更新操作（针对 `controller.py` 和测试文件）未被执行。当前系统处于中间状态：文件已改名，但引用仍指向旧名称。
本计划修正了 Act 序列，跳过错误的操作，并完成剩余的引用更新。

## 标签
 #fix #refactor #runtime

---

## Script

### Act 1: 更新 rt_plugin_loader.py 引用

修正 `core/rt_plugin_loader.py` 中对 `executor` 的引用，使其指向新的 `rt_executor`。

~~~~~act
replace core/rt_plugin_loader.py
~~~~~

~~~~~python
from .executor import Executor
~~~~~

~~~~~python
from .rt_executor import Executor
~~~~~

### Act 2: 更新 Controller 引用

修正 `core/controller.py` 中对运行时模块的引用。这是恢复系统运行的关键。

~~~~~act
replace core/controller.py
~~~~~

~~~~~python
from .executor import Executor, ExecutionError
from .intf_exceptions import ExecutionError as CoreExecutionError # Alias to avoid conflict
from .parser import get_parser, detect_best_parser
from .plugin_loader import load_plugins
~~~~~

~~~~~python
from .rt_executor import Executor, ExecutionError
from .intf_exceptions import ExecutionError as CoreExecutionError # Alias to avoid conflict
from .rt_parser import get_parser, detect_best_parser
from .rt_plugin_loader import load_plugins
~~~~~

### Act 3: 更新 main.py 引用

修正 `main.py` 中对 `executor` 和 `plugin_loader` 的引用。

~~~~~act
replace main.py
~~~~~

~~~~~python
from core.plugin_loader import load_plugins
from core.executor import Executor
~~~~~

~~~~~python
from core.rt_plugin_loader import load_plugins
from core.rt_executor import Executor
~~~~~

### Act 4: 更新测试配置 (conftest.py)

修正 `tests/conftest.py` 中对 `Executor` 的引用。

~~~~~act
replace tests/conftest.py
~~~~~

~~~~~python
from core.executor import Executor
~~~~~

~~~~~python
from core.rt_executor import Executor
~~~~~

### Act 5: 更新操作测试 (test_ops.py)

修正 `tests/test_ops.py` 中对解析器和执行器的引用。

~~~~~act
replace tests/test_ops.py
~~~~~

~~~~~python
from core.parser import BacktickParser, TildeParser, get_parser
from core.executor import Executor, ExecutionError
~~~~~

~~~~~python
from core.rt_parser import BacktickParser, TildeParser, get_parser
from core.rt_executor import Executor, ExecutionError
~~~~~

### Act 6: 更新插件测试 (test_plugins.py)

修正 `tests/test_plugins.py` 中对插件加载器和执行器的引用。

~~~~~act
replace tests/test_plugins.py
~~~~~

~~~~~python
from core.executor import Executor
from core.plugin_loader import load_plugins
~~~~~

~~~~~python
from core.rt_executor import Executor
from core.rt_plugin_loader import load_plugins
~~~~~

### Act 7: 更新参数策略测试 (test_arg_strategy.py)

修正 `tests/test_arg_strategy.py` 中对执行器的引用。

~~~~~act
replace tests/test_arg_strategy.py
~~~~~

~~~~~python
from core.executor import Executor
~~~~~

~~~~~python
from core.rt_executor import Executor
~~~~~

### Act 8: 更新自动检测测试 (test_auto_detect.py)

修正 `tests/test_auto_detect.py` 中对解析器的引用。

~~~~~act
replace tests/test_auto_detect.py
~~~~~

~~~~~python
from core.parser import detect_best_parser
~~~~~

~~~~~python
from core.rt_parser import detect_best_parser
~~~~~

### Act 9: 更新检查功能测试 (test_check.py)

修正 `tests/test_check.py` 中对执行器的引用。

~~~~~act
replace tests/test_check.py
~~~~~

~~~~~python
from core.executor import Executor, ExecutionError
~~~~~

~~~~~python
from core.rt_executor import Executor, ExecutionError
~~~~~

### Act 10: 更新 Git 功能测试 (test_git.py)

修正 `tests/test_git.py` 中对执行器的引用。

~~~~~act
replace tests/test_git.py
~~~~~

~~~~~python
from core.executor import Executor
~~~~~

~~~~~python
from core.rt_executor import Executor
~~~~~

### Act 11: 更新读取功能测试 (test_read.py)

修正 `tests/test_read.py` 中对执行器的引用。

~~~~~act
replace tests/test_read.py
~~~~~

~~~~~python
from core.executor import Executor, ExecutionError
~~~~~

~~~~~python
from core.rt_executor import Executor, ExecutionError
~~~~~

### Act 12: 更新 Integration V2 测试

修正 `tests/test_integration_v2.py` 中对 `Executor` 的引用。

~~~~~act
replace tests/test_integration_v2.py
~~~~~

~~~~~python
from core.executor import Executor
~~~~~

~~~~~python
from core.rt_executor import Executor
~~~~~

### Act 13: 验证测试

运行核心运行时测试以确保修复成功。

~~~~~act
run_command
~~~~~

~~~~~bash
pytest tests/test_ops.py tests/test_plugins.py
~~~~~