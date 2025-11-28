好的，审查完成。

你的判断是正确的，除了 `log` 和 `find` 命令外，其他几个命令的输出行为也存在不一致的情况，特别是 `axon --list-acts` 和 `run --list-acts`。它们将本应作为数据的指令列表错误地输出到了 `stderr`。

我将生成一个计划来修正这个问题，以确保整个 CLI 工具集在输出流的使用上保持一致性和可预测性。

## [WIP] fix: 统一 --list-acts 等命令的输出流

### 错误分析
在对 `log` 和 `find` 命令的输出流进行修复后，审查发现 `axon --list-acts` 和 `run --list-acts` 这两个功能相似的命令仍然存在同样的问题：它们将作为核心数据的可用指令列表完全输出到了标准错误 (`stderr`)。

这同样破坏了 Unix 管道的可用性，用户无法通过 `quipu axon --list-acts | grep ...` 这样的命令来筛选和查找特定的指令。

### 用户需求
修改 `quipu axon` 和 `quipu run` 命令在处理 `--list-acts` 选项时的行为，使其：
1.  将标题、警告等元信息继续输出到 `stderr`。
2.  将核心的指令列表数据（指令名称和说明）输出到 `stdout`。

### 评论
这是一个重要的代码一致性修复。通过将所有数据输出命令的行为统一，我们确保了 Quipu CLI 作为一个整体，其行为是可预测且符合开发者直觉的，这对于提升工具的可靠性和开发者体验 (DX) 至关重要。

### 目标
1.  定位 `axon.py` 和 `run.py` 中处理 `--list-acts` 的代码块。
2.  移除在打印指令名称和描述的 `typer.secho` 和 `typer.echo` 调用中的 `err=True` 参数。
3.  确保打印标题的调用仍然保留 `err=True`。

### 基本原理
我们将沿用上一次修复 `query.py` 的成功模式。通过选择性地使用 `typer` 库的 `err=True` 参数，我们可以精确地控制每一行输出的目标流。对于指令列表这种核心数据，我们将其默认输出到 `stdout`，而对于“标题”这类辅助信息，则明确地将其定向到 `stderr`。

### 标签
#intent/fix #flow/ready #priority/low #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/cli #task/object/output-streams #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 修正 `axon.py` 的输出逻辑

我们将修改 `axon.py` 中 `--list-acts` 的处理代码，将指令列表的输出重定向到 `stdout`。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/axon.py
~~~~~
~~~~~python
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True, err=True)
                typer.echo(f"{indented_doc}\n", err=True)
            ctx.exit(0)
~~~~~
~~~~~python
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True)
                typer.echo(f"{indented_doc}\n")
            ctx.exit(0)
~~~~~

#### Acts 2: 修正 `run.py` 的输出逻辑

同样地，我们修正 `run.py` 中 `--list-acts` 的代码，使其行为与 `axon` 命令保持一致。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/run.py
~~~~~
~~~~~python
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True, err=True)
                typer.echo(f"{indented_doc}\n", err=True)
            ctx.exit(0)
~~~~~
~~~~~python
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True)
                typer.echo(f"{indented_doc}\n")
            ctx.exit(0)
~~~~~

### 下一步建议
我们已经修复了代码，现在应该将这些改动提交。如果你同意，我将生成一个包含 `git add` 和 `git commit` 的 `[COMMIT]` 计划来结束这个“输出流重构”的宏观任务。
