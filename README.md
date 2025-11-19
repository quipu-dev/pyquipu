# Axon

> **The Effector for AI Agents.**

Axon 是一个基于 Markdown 块流（Block Stream）的文件系统操作执行器。它旨在作为 AI 模型的“轴突”，将 AI 生成的思维链（Chain of Thought）或指令转化为实际的文件系统副作用。

## 🧠 核心理念

AI 模型擅长生成结构化的 Markdown，但在直接操作文件系统时往往缺乏精确的工具。Axon 定义了一种极简的“动词-名词”协议：

1.  **Act (动词)**: 定义要执行的操作（如写入、替换）。
2.  **Context (名词)**: 提供操作所需的参数（如路径、代码内容）。

这种设计使得 AI 可以像写文档一样编写可执行的脚本，同时保持人类可读性。

## ⚡️ 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用方法

创建一个包含指令的 Markdown 文件（例如 `plan.md`）：

`````markdown
我将为你创建一个 Python 脚本。

```act
write_file
```

```path
src/hello.py
```

```python
def main():
    print("Hello from Axon!")

if __name__ == "__main__":
    main()
```

然后，我要修改打印的内容：

```act
replace
```

```path
src/hello.py
```

```python
    print("Hello from Axon!")
```

```python
    print("Hello World!")
```
`````

运行 Axon 执行该计划：

```bash
python main.py run plan.md
```

或者指定工作区（防止误伤系统文件）：

```bash
python main.py run plan.md --work-dir ./my_project
```

## 🛠️ 支持的操作 (Acts)

目前 Axon 内置了以下原子操作：

### `write_file`
将内容写入指定文件。如果文件不存在会自动创建，如果存在则覆盖。

*   **参数 1**: 文件相对路径
*   **参数 2**: 文件内容

### `replace`
在文件中进行精确文本替换。这比行号更安全，比正则表达式更易于 AI 生成。

*   **参数 1**: 文件相对路径
*   **参数 2**: 要被替换的**旧文本**（必须完全匹配，包括缩进）
*   **参数 3**: 新文本

## 🛡️ 安全机制

Axon 内置了路径逃逸检查。所有的文件操作都被限制在指定的 `--work-dir`（默认为当前目录）中。任何尝试访问父目录（`../`）的操作都会被拦截并报错。

## 🧪 开发与测试

本项目使用 `pytest` 进行测试。

```bash
# 运行所有测试
pytest

# 运行特定模块
pytest tests/test_ops.py
```

## 📂 项目结构

*   `acts/`: 具体操作的实现（可扩展）。
*   `core/`: 解析器与执行器核心逻辑。
*   `commands/`: CLI 接口实现。
*   `tests/`: 单元测试。

---
