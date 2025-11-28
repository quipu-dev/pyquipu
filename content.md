好的，我看到了新的测试错误。这是一个在测试代码本身引入的简单 `NameError`，因为我在 `test_view_model.py` 中添加 `get_node_blobs` 方法时，忘记导入 `Dict` 类型提示。

这个问题会阻止 `pytest` 收集所有依赖该文件的测试，因此我们看到了 `3 errors during collection`。修复它很简单。

## [WIP] fix(tests): 修复因缺失类型导入导致的测试集合失败

### 错误分析
在 `tests/cli/test_view_model.py` 文件中，我为 `MockHistoryReader` 类添加了 `get_node_blobs` 方法，并为其返回类型添加了 `Dict[str, bytes]` 的类型提示。但是我忘记了从 `typing` 模块导入 `Dict`，导致 Python 在解析该文件时抛出 `NameError: name 'Dict' is not defined`。

由于 `test_tui_logic.py` 和 `test_tui_reachability.py` 都从 `test_view_model.py` 导入了 `MockHistoryReader`，这个错误连锁导致了多个测试文件的收集失败。

### 用户需求
修复 `test_view_model.py` 中的 `NameError`，使 `pytest` 能够成功收集并运行所有测试。

### 评论
这是一个简单的疏漏，修复起来很快。解决这个问题后，我们之前为解决 `TypeError` 和 `AssertionError` 所做的修复才能真正被测试到。

### 目标
在 `tests/cli/test_view_model.py` 的 `typing` 导入语句中，添加 `Dict`。

### 基本原理
通过在文件顶部正确导入所有使用到的类型，可以解决 `NameError`，恢复测试套件的正常运行。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/test-suite #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 在 `test_view_model.py` 中导入 `Dict` 类型

我们将修改 `typing` 导入行，加入 `Dict`。

~~~~~act
patch_file
tests/cli/test_view_model.py
~~~~~
~~~~~python
import pytest
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Any

from quipu.core.models import QuipuNode
~~~~~
~~~~~python
import pytest
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Any, Dict

from quipu.core.models import QuipuNode
~~~~~

### 下一步建议
这个修复应该已经解决了所有的测试收集错误。请重新运行测试。现在我们应该能够看到之前修复的 `AssertionError` 和 `KeyError` 是否也已成功解决，理想情况下，所有测试都应该通过。
