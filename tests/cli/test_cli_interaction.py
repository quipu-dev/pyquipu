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