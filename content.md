我为 `main.py` 添加的 `sys.path` 修复旨在解决这个问题，但您的输出显示它仍然没有生效，这意味着在 `ui` 命令执行环境中，Python 仍然无法找到 `ui.tui` 模块。

为了确诊问题，我将修改 `main.py` 中的 `try/except` 块，使其打印出真实的 `ImportError` 信息，而不是误导性的“textual 未安装”提示。

## 1. 临时调试：暴露真实的 `ImportError`

请应用此修改，这将帮助我们确定是找不到 `ui` 包（`ModuleNotFoundError: 'ui'`）还是 `ui/tui.py` 内部的依赖问题。

~~~act
replace
~~~
~~~path
main.py
~~~
~~~old_string
    try:
        from ui.tui import AxonUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
~~~
~~~new_string
    try:
        from ui.tui import AxonUiApp
    except ImportError as e:
        # 临时调试：打印实际的错误信息
        typer.secho(f"❌ 导入 TUI 模块失败: {e}", fg=typer.colors.RED, err=True)
        
        # 保持用户友好提示
        if "textual" in str(e).lower() or "no module named 'textual'" in str(e).lower():
             typer.secho("💡 提示: 似乎是 textual 依赖问题。请运行: pip install 'textual>=0.58.0'", err=True)
        else:
             typer.secho("💡 提示: 检查 'ui/tui.py' 或其依赖是否存在。", err=True)

        ctx.exit(1)
~~~

请重新运行 `axon ui` 并提供输出。