You've spotted another excellent area for improvement. The CLI's self-documentation is inconsistent, which hinders usability. Providing clear, concise help text for every command is a fundamental principle of good CLI design.

I will generate a plan to systematically add the missing `help` descriptions to all top-level commands.

## [WIP] fix: Add help text to all top-level CLI commands

### 错误分析

The user correctly observed that most top-level commands in the `quipu --help` output lack descriptive help text. This is because the `help` parameter was omitted in their respective `@app.command()` decorator definitions across various files in `packages/quipu-cli/src/pyquipu/cli/commands/`. This makes the CLI less discoverable and user-friendly, as users cannot quickly understand the purpose of each command from the main help screen.

### 用户需求

The user wants to add descriptive help text to all top-level Typer commands to improve the CLI's usability and self-documentation.

### 评论

This is a high-value user experience (UX) and developer experience (DX) fix. A self-documenting tool is easier to learn, use, and maintain. This change will make the CLI feel more complete and professional.

### 目标

1.  Identify every file defining a top-level command.
2.  Use `patch_file` to add a concise and accurate `help` string to each command's decorator.
3.  Ensure the final `quipu --help` output is complete and informative.

### 基本原理

The solution is to systematically edit the command definition files. Each top-level command is registered with a `@app.command()` decorator. We will add a `help="<description>"` argument to each decorator that is missing one. This is a safe and targeted change that directly addresses the issue.

### 标签

#intent/fix #flow/ready #priority/medium #comp/cli #concept/ui #scope/ux #scope/dx #ai/instruct #task/domain/cli #task/object/help-text #task/action/completion #task/state/continue

---

### Script

#### Acts 1: 为 `axon` 命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/axon.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="axon")
    def axon_command(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="axon", help="无状态执行 Plan 文件，绕过 Quipu 引擎。")
    def axon_command(
        ctx: typer.Context,
~~~~~

#### Acts 2: 为 `export` 命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/export.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="export")
    def export_command(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="export", help="将历史图谱中的节点导出为 Markdown 文件。")
    def export_command(
        ctx: typer.Context,
~~~~~

#### Acts 3: 为导航命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def checkout(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="检出指定状态的快照到工作区。")
    def checkout(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
            )

    @app.command()
    def undo(
        ctx: typer.Context,
~~~~~
~~~~~
            )

    @app.command(help="沿当前分支向上导航（回到父节点）。")
    def undo(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
            )

    @app.command()
    def redo(
        ctx: typer.Context,
~~~~~
~~~~~
            )

    @app.command(help="沿当前分支向下导航（进入最新子节点）。")
    def redo(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
            )

    @app.command()
    def prev(
        ctx: typer.Context,
~~~~~
~~~~~
            )

    @app.command(help="导航到时间上更早的兄弟分支节点。")
    def prev(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
                pass

    @app.command()
    def next(
        ctx: typer.Context,
~~~~~
~~~~~
                pass

    @app.command(help="导航到时间上更新的兄弟分支节点。")
    def next(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
                pass

    @app.command()
    def back(
        ctx: typer.Context,
~~~~~
~~~~~
                pass

    @app.command(help="在访问历史中后退一步。")
    def back(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/navigation.py
~~~~~
~~~~~
                ctx.exit(1)

    @app.command()
    def forward(
        ctx: typer.Context,
~~~~~
~~~~~
                ctx.exit(1)

    @app.command(help="在访问历史中前进一步。")
    def forward(
        ctx: typer.Context,
~~~~~

#### Acts 4: 为查询命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/query.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def log(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="按时间倒序显示历史图谱。")
    def log(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/query.py
~~~~~
~~~~~
                bus.data(data_line)

    @app.command(name="find")
    def find_command(
        ctx: typer.Context,
~~~~~
~~~~~
                bus.data(data_line)

    @app.command(name="find", help="根据摘要或类型搜索历史节点。")
    def find_command(
        ctx: typer.Context,
~~~~~

#### Acts 5: 为远程命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/remote.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def sync(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="与远程 Git 仓库同步 Quipu 历史记录。")
    def sync(
        ctx: typer.Context,
~~~~~

#### Acts 6: 为 `run` 命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/run.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="run")
    def run_command(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(name="run", help="执行 Plan 文件并记录到 Quipu 历史。")
    def run_command(
        ctx: typer.Context,
~~~~~

#### Acts 7: 为 `show` 命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/show.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def show(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="显示指定历史节点中的文件内容。")
    def show(
        ctx: typer.Context,
~~~~~

#### Acts 8: 为 `ui` 命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/ui.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def ui(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="启动交互式 TUI 历史浏览器。")
    def ui(
        ctx: typer.Context,
~~~~~

#### Acts 9: 为工作区命令添加帮助文本

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/workspace.py
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command()
    def save(
        ctx: typer.Context,
~~~~~
~~~~~
def register(app: typer.Typer):
    @app.command(help="将当前工作区的变更创建为一个新的快照节点。")
    def save(
        ctx: typer.Context,
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/workspace.py
~~~~~
~~~~~
                ctx.exit(1)

    @app.command()
    def discard(
        ctx: typer.Context,
~~~~~
~~~~~
                ctx.exit(1)

    @app.command(help="丢弃当前工作区的所有变更，恢复到上一个快照状态。")
    def discard(
        ctx: typer.Context,
~~~~~

### 下一步建议

我们已经为所有命令添加了帮助文本。

1.  **验证**: 执行此计划后，请运行 `qs --help` 来验证所有命令现在是否都有了描述。
2.  **提交**: 在验证无误后，我们可以将这一系列的本地化和 CLI 改进合并到一个 `[COMMIT]` 计划中，以完成这个任务。
