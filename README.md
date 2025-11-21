# Axon

> **The Effector for AI Agents.**

Axon 是一个 Markdown 原生的执行器，它诞生于一个关键的观察：通过 API 访问的 AI 模型，其能力和稳定性常常不如其经过优化的 Web 界面。Axon 正是为了弥补这一鸿沟而生，它将一个简单的 Markdown 文件转变为一份**可执行文档 (Executable Document)**。

这意味着你的 `plan.md` 不再仅仅是一个静态的计划，而是一个可复现、可版本控制的脚本。你可以把它看作是 Jupyter Notebook 的一个轻量级替代品，但它更专注于文件系统的操作与编排。通过这种方式，Axon 为 AI 提供了一个可靠的“效应器（Effector）”，将高层级的策略思想，转化为具体、可验证、且稳定执行的文件修改。

## 🧠 核心理念

AI 模型擅长生成结构化的 Markdown，但在直接操作文件系统时往往缺乏精确的工具。Axon 定义了一种极简的“动词-名词”协议：

1.  **Act (动词)**: 定义要执行的操作（如写入、替换）。
2.  **Context (名词)**: 提供操作所需的参数（如路径、代码内容）。

这种设计使得 AI 可以像写文档一样编写可执行的脚本，同时保持人类可读性。

### 🧩 参数传递机制 (ArgMode)

为了平衡灵活性与安全性，Axon 引入了 **ArgMode** 协议，支持三种参数解析模式：

#### 1. 混合模式 (Hybrid) - *默认*
*   **逻辑**: `Args = [行内参数...] + [块参数...]`
*   **行为**: 贪婪合并。既读取行内写的内容，也读取后续跟随的代码块。
*   **适用**: `write_file`, `replace`, `append_file` 等大多数操作。
*   **示例**:
    ```markdown
    ~~~act
    replace README.md
    ~~~
    ~~~old
    foo
    ~~~
    ~~~new
    bar
    ~~~
    ```
    解析结果: `["README.md", "foo", "bar"]`

#### 2. 互斥模式 (Exclusive)
*   **逻辑**: **优先**使用行内参数。若存在行内参数，则**忽略**后续的代码块；若无行内参数，则读取后续代码块。
*   **行为**: 互斥选择 (Exclusive OR)。行内参数与块参数互不兼容。
*   **适用**: `git_add`, `check_files_exist`, `run_command`, `delete_file`, `search_files`。
*   **场景 A (行内简写)**:
    ```markdown
    ~~~act
    git_add file1.py file2.py
    ~~~
    ```
    解析结果: `["file1.py", "file2.py"]` (后续如果有块，会被视为无关文本而被忽略)
*   **场景 B (块列表)**:
    ```markdown
    ~~~act
    git_add
    ~~~
    ~~~list
    file1.py
    file2.py
    ~~~
    ```
    解析结果: `["file1.py\nfile2.py"]`

#### 3. 仅块模式 (Block Only)
*   **逻辑**: `Args = [块参数...]`
*   **行为**: 严格模式。**强制忽略**任何行内参数（除了命令本身）。
*   **适用**: `git_commit`, `log_thought`。
*   **目的**: 防止 AI 在行内胡乱添加不规范的参数（如 `git_commit -m "msg"`），强制要求复杂文本（如提交信息）放在规范的 Block 中以确保解析稳定性。

## ⚡️ 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用方法

创建一个包含指令的 Markdown 文件（例如 `plan.md`）：

````markdown
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
````

运行 Axon 执行该计划：

```bash
# 默认会有 Diff 预览和确认提示
python main.py plan.md

# 使用 YOLO 模式 (You Only Look Once) 跳过确认
python main.py plan.md -y
```

或者指定工作区（防止误伤系统文件）：

```bash
python main.py plan.md --work-dir ./my_project
```

### 🎭 智能幕布 (Smart Parsers)

Axon 支持 **Act 嗅探 (Act-Sniffing)** 技术。你不需要手动指定解析器。

*   如果你的指令块使用 ` ```act `，Axon 会使用反引号解析器（绿幕）。
*   如果你的指令块使用 ` ~~~act `，Axon 会自动切换到波浪号解析器（蓝幕）。
*   Axon 还支持**变长围栏**，例如 ` ````act `，以处理多层嵌套的代码块。

示例（蓝幕模式）：

````markdown
~~~act
write_file
~~~
~~~path
guide.md
~~~
~~~markdown
Here is a code block:
```python
print("nested")
```
~~~
````

## 🛠️ 支持的操作 (Acts)

目前 Axon 内置了以下原子操作：

### 基础操作 (`acts/basic.py`)

#### `write_file`
将内容写入指定文件。如果文件不存在会自动创建，如果存在则覆盖。
*   **参数**: `[path, content]`

#### `replace`
在文件中进行精确文本替换。这比行号更安全，比正则表达式更易于 AI 生成。
*   **参数**: `[path, old_string, new_string]`

#### `append_file`
向文件末尾追加内容。
*   **参数**: `[path, content]`

### Git 操作 (`acts/git.py`)

#### `git_init`
初始化 Git 仓库。
*   **参数**: `[]` (无)

#### `git_add`
添加文件到暂存区。
*   **参数**: `[files]` (空格分隔的文件列表，或 ".")
*   **注意**: 此命令禁用混合模式。如果在 `act` 块中指定了参数（如 `git_add .`），随后的 Block 将被视为普通文本而非参数。

#### `git_commit`
提交暂存区的更改。
*   **参数**: `[message]`

#### `git_status`
打印当前 Git 状态日志。
*   **参数**: `[]` (无)

### 检查操作 (`acts/check.py`)

#### `check_files_exist`
检查当前工作区是否存在指定的一组文件（按行分隔）。如果缺少文件则报错终止。
*   **参数**: `[file_list]`
*   **注意**: 此命令禁用混合模式。如果在 `act` 行内提供了参数，后续的代码块将被忽略。

#### `check_cwd_match`
检查当前实际的工作区绝对路径是否与预期的路径匹配。防止在错误的机器或目录下执行。
*   **参数**: `[expected_abs_path]`

### 控制流

#### `end`
强制结束当前语句的解析。用于在参数之间插入大量非参数文本，或明确截断参数列表。

## 🛡️ 安全机制

1.  **路径逃逸检查**: 所有的文件操作都被限制在指定的 `--work-dir`（默认为当前目录）中。任何尝试访问父目录（`../`）的操作都会被拦截。
2.  **交互式确认**: 默认情况下，Axon 会显示文件变更的 Diff，并要求用户确认。使用 `-y` 参数可跳过此步骤。

## 🧪 开发与测试

本项目使用 `pytest` 进行测试。

```bash
# 运行所有测试
pytest
```

## 📂 项目结构

*   `acts/`: 具体操作的实现（Basic, Check）。
*   `core/`: 解析器与执行器核心逻辑。
*   `tests/`: 单元测试。
*   `main.py`: CLI 入口。

### 扩展操作 (Shell/Read/Refactor/Memory)

#### 系统命令 (`acts/shell.py`)
*   `run_command`: 执行 Shell 命令。`[command]`

#### 读取与检索 (`acts/read.py`)
*   `read_file`: 读取并打印文件内容。`[path]`
*   `list_files`: 列出目录内容。默认扁平显示，使用 `--tree` 递归。`[path] [--tree]`
*   `search_files`: 搜索内容（优先使用 `rg`，回退使用 Python）。`[pattern, path(opt)]`

#### 重构操作 (`acts/refactor.py`)
*   `move_file`: 移动或重命名。`[src, dest]`
*   `delete_file`: 删除文件或目录。`[path]`

#### 记忆 (`acts/memory.py`)
*   `log_thought`: 记录思维日志到 `.axon/memory.md`。`[content]`

### 🚀 高级用法：管道与重定向

Axon 支持标准的 Unix 管道操作，这使得它可以轻松集成到其他工具链中（例如直接接收 LLM 的 API 输出）。

```bash
# 从管道读取
echo "..." | axon

# 文件重定向
axon < generated_plan.md

# 结合 LLM 工具 (示例)
llm "Refactor main.py to use classes" | axon -y
```
