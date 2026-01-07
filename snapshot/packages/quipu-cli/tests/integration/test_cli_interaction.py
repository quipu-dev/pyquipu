from unittest.mock import MagicMock

from pyquipu.cli.main import app
from typer.testing import CliRunner


def test_run_command_with_piped_input_and_confirmation(runner: CliRunner, quipu_workspace, monkeypatch):
    """
    测试核心场景: 通过管道输入 plan，并对需要确认的 act (run_command) 进行交互。
    """
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.run.bus", mock_bus)
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

    result = runner.invoke(app, ["run", "-w", str(work_dir)], input=plan_content + user_input)

    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("run.success")
    assert output_file.exists(), "The command did not create the output file."
    assert output_file.read_text().strip() == "Success"
