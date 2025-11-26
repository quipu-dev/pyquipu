# fix: 修复因缺少类型导入导致的 NameError

## 用户需求
在执行上一步的重构后，运行 `pytest` 测试套件时，系统在收集测试用例阶段就因 `NameError: name 'Optional' is not defined` 而崩溃。这个错误发生在 `packages/quipu-engine/src/quipu/core/sqlite_storage.py` 文件中，是由于新添加的 `find_nodes` 方法使用了 `Optional` 类型提示，但没有在文件顶部导入它。

需要修复这个导入错误，以使测试套件能够正常运行。

## 评论
这是一个简单的疏忽，是在上一次重构中引入的典型 Bug。通过快速修复这个导入问题，我们可以恢复开发流程的正常状态，并验证上一步重构的正确性。

## 目标
1.  在 `sqlite_storage.py` 文件中，从 `typing` 模块导入 `Optional`。
2.  确保 `pytest` 能够成功收集并运行所有测试用例。

## 基本原理
Python 的类型提示系统要求所有用作提示的类型在使用前都必须被定义或导入。`Optional` 是 `typing` 标准库的一部分，因此只需在文件顶部的导入语句中添加它即可解决 `NameError`。

## 标签
#intent/fix #flow/ready #priority/critical
#comp/engine #scope/core #dx
#ai/instruct
#task/domain/storage #task/object/sqlite-backend #task/action/integration
#task/state/continue #task/status/active

---

## Script

### Acts 1: 修复 `sqlite_storage.py` 中的导入错误

我们将定位到 `sqlite_storage.py` 文件，并在 `typing` 的导入语句中添加 `Optional`。

~~~~~act
replace packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
import json
import logging
from typing import Any, List, Dict
from datetime import datetime
from pathlib import Path
~~~~~
~~~~~python
import json
import logging
from typing import Any, List, Dict, Optional
from datetime import datetime
from pathlib import Path
~~~~~
