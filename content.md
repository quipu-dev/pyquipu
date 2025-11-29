好的，测试通过是关键的一步。你完全正确，这是一个典型的回归问题，必须通过自动化测试来永久性地解决，以防止未来的重构再次引入这个缺陷。

我将创建一个新的测试文件来隔离这种交互式测试，并向现有的测试文件中添加一个相关的测试用例。我将严格遵守你的格式化要求，在所有 Python 代码块中使用 ` ``` ` 而不是 `~~~~~`。

## [WIP] test: 添加交互式管道输入的回归测试

### 错误分析
系统之前的测试套件未能捕获此回归问题，因为它没有充分模拟一个关键的用户场景：通过管道 (`|`) 将内容输入到一个需要后续交互式确认的命令中。现有的测试要么不测试交互，要么在没有 `stdin` 重定向的环境下测试，因此无法触发 `click.getchar()` 在管道环境下的特殊行为，导致问题潜伏。

### 用户需求
为 Quipu CLI 创建一套新的回归测试，以确保：
1.  当 `stdin` 被管道占用时，需要用户确认的命令（如 `quipu run` 和 `quipu discard`）能够正确地暂停并等待用户通过 TTY 输入。
2.  测试能够模拟用户接受 (`y`) 和拒绝 (`n`) 确认提示，并验证程序的行为（文件系统状态、退出码、输出信息）是否符合预期。

### 评论
为这个场景添加专门的测试是至关重要的。这不仅可以防止此特定问题的再次发生，也为未来所有需要交互的命令提供了一个健壮的测试模式，从而提升了整个系统的质量和可靠性。

### 目标
1.  创建一个新的测试文件 `tests/cli/test_cli_interaction.py`，专门用于测试复杂的 CLI 交互场景。
2.  在该文件中添加一个测试，模拟通过管道向 `quipu run` 提供一个需要确认的 `run_command` 操作，并验证用户接受后的行为。
3.  在现有的 `tests/cli/test_workspace_commands.py` 中，为 `discard` 命令添加一个新的测试用例，专门验证其在管道输入和用户拒绝确认时的行为。

### 基本原理
我们将利用 `typer.testing.CliRunner` 的 `invoke` 方法中的 `input` 参数。这个参数可以模拟用户的标准输入。
*   对于模拟 `cat plan.md | quipu run` 的场景，我们将 `plan.md` 的内容和用户的确认输入（例如 `'y\n'`）拼接成一个字符串，并传递给 `input` 参数。
*   测试将首先准备一个初始的文件系统状态，然后运行带输入的 CLI 命令，最后通过断言检查最终的文件系统状态、命令的退出码以及 `stdout`/`stderr` 的输出来验证其行为是否正确。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/testing #task/object/regression-tests #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 创建新的 CLI 交互测试文件

我们将创建一个新文件 `test_cli_interaction.py` 来存放针对 `quipu run` 在管道模式下的交互测试。

~~~~~act
write_file
tests/cli/test_cli_interaction.py
~~~~~
~~~~~python
import pytest
from typer.testing import CliRunner
from quipu.cli.main import app


def test_run_command_with_piped_input_and_confirmation(runner: CliRunner, quipu_workspace):
    """
    测试核心场景: 通过管道输入 plan，并对需要确认的 act (run_command) 进行交互。
    """
    work_dir, _, _ = quipu_workspace
    output_file = work_dir / "output.txt"

    # Plan 内容: 执行一个 shell 命令
    plan_content = f"""
```act
run_command
```
```text
echo "Success" > {output_file.name}
```
"""

    # 模拟用户输入 'y' 并按回车
    user_input = "y\n"

    # 使用 runner.invoke 的 input 参数来模拟 `echo "{plan_content}" | quipu run`
    # 注意：CliRunner 的 input 模拟的是 stdin，这正是我们需要的
    result = runner.invoke(app, ["run", "-w", str(work_dir)], input=plan_content + user_input)

    assert result.exit_code == 0, f"CLI command failed with stderr:\n{result.stderr}"
    assert "✨ 执行成功" in result.stderr
    assert output_file.exists(), "The command did not create the output file."
    assert output_file.read_text().strip() == "Success"
~~~~~

#### Acts 2: 为 `discard` 命令添加管道输入测试

现在，我们在 `test_workspace_commands.py` 文件末尾追加一个新的测试用例，专门测试 `discard` 在管道输入和用户拒绝时的行为，以确保状态不会被错误地修改。

~~~~~act
append_file
tests/cli/test_workspace_commands.py
~~~~~
~~~~~python

def test_discard_interactive_with_piped_input_abort(runner, quipu_workspace):
    """
    验证在管道输入模式下，discard 命令能正确接收交互式输入 'n' 并中止操作。
    """
    work_dir, _, engine = quipu_workspace

    # 初始状态 v1
    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash())

    # 制造脏状态 v2
    (work_dir / "file.txt").write_text("v2")

    # 模拟用户通过管道输入 'n'
    # 注意: 这里的 'input' 模拟的是用户在 TTY 的输入，因为 stdin 已经被 runner 接管
    result = runner.invoke(app, ["discard", "-w", str(work_dir)], input="n")

    # Abort() 会导致 exit_code 为 1
    assert result.exit_code == 1
    assert "操作已取消" in result.stderr
    # 验证文件没有被回滚
    assert (work_dir / "file.txt").read_text() == "v2"
~~~~~

### 下一步建议
我们已经为关键的交互场景添加了回归测试。现在请运行 `pytest tests/cli/` 来确认新的测试能够通过，并且旧的测试没有受到影响。这将为我们未来的重构提供坚实的安全保障。
