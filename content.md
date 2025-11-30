好的，我将创建一个计划来修复 `ruff` 在 `quipu-cli` 模块中报告的 `F821 Undefined name 'logger'` 错误。

根据你的指示和代码库中的既有模式，这些错误是由于相关文件在调用 `logger.error` 之前忘记了导入 `logging` 模块并实例化 `logger` 对象。我们将通过添加标准的两行代码来修正这个问题，使其与其他命令文件保持一致。

我将忽略所有与测试文件 (`tests/`) 和非 `cli` 核心包 (`quipu-engine`, `quipu-runtime`) 相关的错误。

## [WIP] fix(cli): 修正命令模块中未定义的 logger 引用

### 错误分析
`ruff` 在 `packages/quipu-cli/src/pyquipu/cli/commands/helpers.py` 和 `navigation.py` 中检测到 `F821 Undefined name 'logger'` 错误。这是因为这两个文件中的异常处理块调用了 `logger.error`，但是 `logger` 对象从未在该模块作用域内被定义。

### 用户需求
修复上述 `F821` 错误，使 `ruff check` 不再报告这些问题。

### 评论
这是一个简单的代码一致性修复。在整个 `quipu-cli` 包中，标准做法是在每个模块的顶部获取一个模块级的 logger 实例。遵循这一模式可以确保日志记录的正确性和可维护性。

### 目标
1.  在 `helpers.py` 文件中导入 `logging` 模块并初始化 `logger`。
2.  在 `navigation.py` 文件中导入 `logging` 模块并初始化 `logger`。

### 基本原理
通过在每个文件的顶部添加 `import logging` 和 `logger = logging.getLogger(__name__)`，我们可以解决 `F821` 错误。`logger.error(..., exc_info=True)` 用于记录详细的开发者调试信息（包括堆栈跟踪），而 `bus.error(...)` 用于向最终用户显示简洁、友好的错误消息。两者共同构成了健壮的错误处理策略。

### 标签
#intent/fix #flow/ready #priority/high #comp/cli #scope/dx #ai/instruct #task/domain/cli #task/object/linter-errors #task/action/fix #task/state/begin

---

### Script

#### Acts 1: 为 `helpers.py` 添加 logger 定义

我们将 `import logging` 和 `logger` 的实例化代码添加到 `helpers.py` 的导入区。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/helpers.py
~~~~~
~~~~~python
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional

import typer
from pyquipu.common.messaging import bus
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..factory import create_engine
from ..logger_config import setup_logging
~~~~~
~~~~~python
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional

import typer
from pyquipu.common.messaging import bus
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..factory import create_engine
from ..logger_config import setup_logging

logger = logging.getLogger(__name__)
~~~~~

#### Acts 2: 为 `navigation.py` 添加 logger 定义

同样，我们为 `navigation.py` 添加相同的 logger 定义代码。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~python
from pathlib import Path
from typing import Annotated

import typer
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import _execute_visit, _find_current_node, engine_context
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Annotated

import typer
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import _execute_visit, _find_current_node, engine_context

logger = logging.getLogger(__name__)
~~~~~

### 下一步建议
- **执行计划**: 执行此计划后，可以再次运行 `ruff check .` 来验证 `F821` 错误是否已全部解决。
- **提交变更**: 在验证无误后，我会为你生成一个 `[COMMIT]` 计划来将这些修复提交到版本库中。
