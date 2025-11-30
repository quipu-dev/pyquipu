import click
import typer
from typing import List, Optional

from pyquipu.common.messaging import bus


def prompt_for_confirmation(prompt: str, diff_lines: Optional[List[str]] = None, default: bool = False) -> bool:
    """
    一个健壮、统一的 CLI 确认提示器。

    它能处理可选的 diff 显示、无需回车的单字符输入，
    并在非交互式环境中优雅地降级。

    Args:
        prompt: 显示给用户的主消息。
        diff_lines: 在提示前显示的可选 diff 字符串列表。
        default: 当用户直接按回车键时的默认返回值。

    Returns:
        如果用户确认则返回 True，否则返回 False。
    """
    if diff_lines:
        bus.info("prompt.ui.diffHeader")
        for line in diff_lines:
            if line.startswith("+"):
                typer.secho(line.strip("\n"), fg=typer.colors.GREEN, err=True)
            elif line.startswith("-"):
                typer.secho(line.strip("\n"), fg=typer.colors.RED, err=True)
            elif line.startswith("^"):
                typer.secho(line.strip("\n"), fg=typer.colors.BLUE, err=True)
            else:
                typer.echo(line.strip("\n"), err=True)
        typer.echo("", err=True)

    prompt_suffix = bus.get("prompt.suffix.yesDefault") if default else bus.get("prompt.suffix.noDefault")
    typer.secho(prompt + prompt_suffix, nl=False, err=True)

    try:
        # click.getchar() 会智能地尝试从 /dev/tty 读取
        char = click.getchar(echo=False)
        click.echo(char, err=True)  # 手动回显到 stderr
    except (OSError, EOFError):
        # 在完全没有 tty 的环境中 (例如 CI runner)，会抛出异常
        bus.info("prompt.info.nonInteractive")
        return False  # 非交互式环境应安全失败

    if not char or char == "\r" or char == "\n":
        return default

    if char.lower() == "y":
        return True
    if char.lower() == "n":
        return False

    return default
