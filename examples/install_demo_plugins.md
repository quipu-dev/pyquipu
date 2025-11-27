# 🔌 Quipu 插件安装演示

此脚本将在当前工作区的 `.axon/acts` 目录下安装一个演示插件，并生成一个测试脚本。

## 1. 创建插件目录和说明文件

首先，我们初始化插件目录。

~~~act
write_file
~~~

~~~path
README.md
~~~

~~~~~~~content
# 本地插件目录

此目录下的 `.py` 文件会被 Quipu 自动加载。
你可以在这里编写项目专用的指令。

## 编写规范

每个 Python 文件必须包含一个 `register` 函数：

```python
from core.executor import Executor

def register(executor: Executor):
    # 注册指令名称、处理函数和参数模式
    executor.register("my_command", _my_func, arg_mode="hybrid")

def _my_func(executor: Executor, args: list):
    print("Hello from plugin!")
```

## 2. 部署演示插件代码

我们将创建一个名为 `demo_utils.py` 的插件，包含两个指令：
1. `greet`: 简单的问候指令。
2. `stamp_file`: 在文件末尾打上时间戳（实用功能演示）。

~~~act
write_file
~~~

~~~path
.axon/acts/demo_utils.py
~~~

~~~python
import logging
import time
from typing import List
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register(executor: Executor):
    """注册演示插件"""
    # 注册一个简单的打印指令
    executor.register("greet", _greet, arg_mode="hybrid")
    # 注册一个文件操作指令
    executor.register("stamp_file", _stamp_file, arg_mode="hybrid")

def _greet(executor: Executor, args: List[str]):
    """
    Act: greet
    Args: [name]
    """
    name = "User"
    if args:
        name = " ".join(args)
    
    logger.info(f"👋 [DemoPlugin] Hello, {name}! Welcome to Quipu.")

def _stamp_file(executor: Executor, args: List[str]):
    """
    Act: stamp_file
    Args: [path]
    Description: Appends a timestamp to a file.
    """
    if not args:
        raise ExecutionError("stamp_file 需要文件路径参数")
        
    raw_path = args[0]
    target_path = executor.resolve_path(raw_path)
    
    if not target_path.exists():
        raise ExecutionError(f"文件不存在: {raw_path}")
        
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    append_content = f"\n\n# Stamped by Quipu at {timestamp}\n"
    
    # 这里演示如何复用 executor 的确认机制
    # 模拟读取旧内容
    old_content = target_path.read_text(encoding='utf-8')
    new_content = old_content + append_content
    
    if not executor.request_confirmation(target_path, old_content, new_content):
        logger.warning("❌ 用户取消了打标签操作")
        return
        
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(append_content)
        
    logger.info(f"✅ 已在 {target_path.name} 打上时间戳")
~~~

## 3. 创建测试脚本

最后，我们生成一个 `run_demo.md` 文件，让用户可以立即尝试这些新插件。

~~~act
write_file
~~~

~~~path
run_demo.md
~~~

~~~~~~markdown
# 测试自定义插件

这是由 `examples/install_demo_plugins.md` 生成的测试脚本。
如果插件加载成功，下面的指令应该能正常执行。

## 测试 1: Greet 指令

~~~act
greet Quipu Developer
~~~

## 测试 2: Stamp File 指令

首先创建一个临时文件：

~~~act
write_file temp_log.txt
~~~
~~~text
Initial content.
~~~

然后调用我们的自定义插件打时间戳：

~~~act
stamp_file temp_log.txt
~~~

完成后清理（可选）：
~~~act
delete_file temp_log.txt
~~~

---

## 🎉 完成

脚本执行完毕。现在你可以运行以下命令来测试新安装的插件：

```bash
axon run_demo.md
```
~~~~~~
~~~~~~~
