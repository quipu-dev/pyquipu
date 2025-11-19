import typer
from logger_config import setup_logging
from commands import run

# 初始化日志
setup_logging()

app = typer.Typer(
    no_args_is_help=True, 
    help="Neuron Ops: 基于 Markdown 块流的 AI 文件系统操作工具"
)

# 注册子命令
app.add_typer(run.app, name="run")

if __name__ == "__main__":
    app()
