好的，我们已经回到问题的起点。你的分析非常清晰和准确，直指了问题的核心：我们错误地将一个**控制流问题**（用户取消）用**返回值**来处理，而不是用更健壮的**异常**来处理，这导致了取消信号在调用栈中丢失。

现在，我们将遵循你制定的正确行动计划，一次性地、系统性地修复这个问题。我将生成一个计划，该计划将引入一个新的专用异常，并重构相关的调用链以正确地传递“取消”信号。

## [WIP] fix: 重构异常处理以正确处理管道中的用户取消操作

### 错误分析
系统在处理管道输入 (`|`) 时，无法正确处理需要用户交互的确认操作。根本原因在于多层逻辑的错误叠加：
1.  **错误的交互环境判断**: 最初使用 `sys.stdin.isatty()` 来检测交互环境，这在 `stdin` 被重定向时会错误地返回 `False`。
2.  **崩溃的交互库**: 底层的 `typer.confirm` 在 `stdin` 被重定向时会因无法访问 TTY 而崩溃。
3.  **错误的修复策略**: 我们之前的尝试通过捕获这个崩溃异常并从 `request_confirmation` 返回 `False` 来解决问题。这是一个关键的错误转向，因为它将一个明确的“取消”事件（无论是用户主动选择还是环境不支持）退化成了一个普通的布尔返回值。
4.  **信号丢失**: `act` 函数检查这个 `False` 返回值后，只是简单地 `return`，没有向上层 `Executor` 发出任何信号。`Executor` 因此认为 `act` 执行成功，导致整个流程继续，并错误地创建了历史节点。

### 用户需求
重构系统，使其在任何情况下（包括管道输入）都能正确处理用户取消操作。具体要求是：
1.  程序不应崩溃。
2.  当用户取消或环境不支持交互时，操作应被中止。
3.  操作中止后，不应创建任何新的历史节点。
4.  应向用户显示明确的“操作已取消”消息。

### 评论
这是一个对系统鲁棒性至关重要的修复。通过引入专用的异常来处理控制流，我们遵循了现代软件工程的最佳实践，使代码更清晰、更可预测，并能正确响应用户的意图。

### 目标
1.  在 `quipu-interfaces` 中定义一个新的、专用的 `OperationCancelledError` 异常。
2.  修改 `quipu-cli` 中的 `typer_confirmation_handler`，使其在用户拒绝或无法交互时，**抛出** `OperationCancelledError` 而不是返回 `False`。
3.  修改 `quipu-runtime` 中的 `Executor.request_confirmation`，使其不再处理返回值，而是允许异常向上冒泡。
4.  修改所有调用 `request_confirmation` 的 `act` 函数，移除对返回值的检查。
5.  在 `Executor.execute` 中显式捕获 `OperationCancelledError` 并重新抛出，以防被通用异常块捕获。
6.  在最顶层的 `run_quipu` 控制器中捕获 `OperationCancelledError`，并返回一个表示操作取消的 `QuipuResult`，从而彻底中断执行流程。

### 基本原理
我们将用**异常驱动的控制流**取代**返回值驱动的控制流**。`OperationCancelledError` 将成为一个清晰、不可忽略的信号，在调用栈中向上传播。每一层都知道如何处理这个信号：`act` 函数被中断，`Executor` 允许它通过，最终由顶层 `Application` 捕获并执行优雅的退出逻辑，完全跳过记录历史节点的步骤。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #comp/runtime #comp/interfaces #concept/executor #scope/core #ai/instruct #task/domain/cli #task/object/exception-handling #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 定义专用的 `OperationCancelledError` 异常

首先，我们在接口包中定义这个新的异常类型，使其成为一个标准的、跨模块的信号。

~~~~~act
patch_file
packages/quipu-interfaces/src/quipu/interfaces/exceptions.py
~~~~~
~~~~~python
class ExecutionError(AIFSOpsError):
    """操作执行错误"""

    pass
~~~~~
~~~~~python
class ExecutionError(AIFSOpsError):
    """操作执行错误"""

    pass


class OperationCancelledError(ExecutionError):
    """当用户取消一个操作时引发"""

    pass
~~~~~

#### Acts 2: 修改确认处理器以抛出异常

现在，我们修改 `controller.py` 中的 `typer_confirmation_handler`。这是整个修复的核心。它将负责在用户拒绝或环境不支持时，将事件转化为 `OperationCancelledError` 异常。我们使用 `sys.stdout.isatty()` 作为更可靠的交互环境检测方法。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError as CoreExecutionError
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError as CoreExecutionError, OperationCancelledError
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
            # 处理非交互式环境
            if not sys.stdin.isatty():
                logger.warning("非交互式环境，自动跳过确认。使用 --yolo 参数可自动批准。")
                return False

            return typer.confirm(prompt, default=True)
~~~~~
~~~~~python
            # 改进的交互环境检查
            if not sys.stdout.isatty():
                logger.warning("非交互式环境，操作已取消。")
                raise OperationCancelledError("Cannot confirm in non-interactive environment")

            try:
                confirmed = typer.confirm(prompt, default=True)
                if not confirmed:
                    raise OperationCancelledError("User cancelled the operation.")
                return True
            except Exception as e:
                # 捕获 typer/click 在管道中可能抛出的底层异常
                raise OperationCancelledError(f"Failed to get user confirmation due to TTY error: {e}") from e
~~~~~

#### Acts 3: 简化 Executor 的 `request_confirmation`

`Executor.request_confirmation` 现在变成一个简单的代理，它不再关心返回值，只负责调用处理器并让异常通过。

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/runtime/executor.py
~~~~~
~~~~~python
    def request_confirmation(self, file_path: Path, old_content: str, new_content: str) -> bool:
        """
        生成 diff 并请求用户确认。
        如果 self.yolo 为 True,则自动返回 True。
        如果没有提供 confirmation_handler，则安全地返回 False。
        """
        if self.yolo:
            return True

        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        if not diff:
            logger.info("⚠️  内容无变化")
            return True

        if not self.confirmation_handler:
            logger.warning("无确认处理器，已跳过需要用户确认的操作。")
            return False

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"
        return self.confirmation_handler(diff, prompt)
~~~~~
~~~~~python
    def request_confirmation(self, file_path: Path, old_content: str, new_content: str):
        """
        生成 diff 并请求用户确认。
        如果 self.yolo 为 True, 则直接返回。
        如果用户取消或环境不支持，此方法将抛出 OperationCancelledError。
        """
        if self.yolo:
            return

        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        if not diff:
            logger.info("⚠️  内容无变化")
            return

        if not self.confirmation_handler:
            logger.warning("无确认处理器，已跳过需要用户确认的操作。")
            raise OperationCancelledError("No confirmation handler is configured.")

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"
        # 此调用现在要么成功返回，要么抛出 OperationCancelledError
        self.confirmation_handler(diff, prompt)
~~~~~

#### Acts 4: 更新所有 `act` 函数的调用点

现在我们必须移除所有 `act` 函数中对 `request_confirmation` 返回值的检查。

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/basic.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(target_path, old_content, content):
        logger.warning(f"❌ [Skip] 用户取消写入: {raw_path}")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(target_path, old_content, content)
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/basic.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(target_path, content, new_content):
        logger.warning(f"❌ [Skip] 用户取消替换: {raw_path}")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(target_path, content, new_content)
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/basic.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(target_path, old_content, new_content):
        logger.warning(f"❌ [Skip] 用户取消追加: {raw_path}")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(target_path, old_content, new_content)
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/git.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(ctx.root_dir / ".git", "Staged Changes", f"Commit Message: {message}"):
        logger.warning("❌ [Skip] 用户取消提交")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(ctx.root_dir / ".git", "Staged Changes", f"Commit Message: {message}")
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/refactor.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(src_path, f"Source Exists", msg):
        logger.warning("❌ [Skip] 用户取消移动")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(src_path, f"Source Exists", msg)
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/refactor.py
~~~~~
~~~~~python
    if not ctx.request_confirmation(target_path, "EXISTING CONTENT", warning):
        logger.warning("❌ [Skip] 用户取消删除")
        return
~~~~~
~~~~~python
    ctx.request_confirmation(target_path, "EXISTING CONTENT", warning)
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/acts/shell.py
~~~~~
~~~~~python
    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {ctx.root_dir})"
    if not ctx.request_confirmation(ctx.root_dir, "System State", warning_msg):
        logger.warning(f"❌ [Skip] 用户取消执行命令: {command}")
        return
~~~~~
~~~~~python
    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {ctx.root_dir})"
    ctx.request_confirmation(ctx.root_dir, "System State", warning_msg)
~~~~~

#### Acts 5: 调整 `Executor` 的异常处理

`Executor` 需要确保 `OperationCancelledError` 不被通用的 `except Exception` 块捕获和包装，而是直接传递给上层。

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/runtime/executor.py
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError, OperationCancelledError
~~~~~

~~~~~act
patch_file
packages/quipu-runtime/src/quipu/runtime/executor.py
~~~~~
~~~~~python
            try:
                logger.info(
                    f"Executing operation [{i + 1}/{len(statements)}]: {act_name} (Mode: {arg_mode}, Args: {len(final_args)})"
                )
                # 传递上下文对象，而不是 executor 实例
                func(ctx, final_args)
            except Exception as e:
                logger.error(f"Execution failed for '{act_name}': {e}")
                raise ExecutionError(f"An error occurred while executing '{act_name}': {e}") from e
~~~~~
~~~~~python
            try:
                logger.info(
                    f"Executing operation [{i + 1}/{len(statements)}]: {act_name} (Mode: {arg_mode}, Args: {len(final_args)})"
                )
                # 传递上下文对象，而不是 executor 实例
                func(ctx, final_args)
            except OperationCancelledError:
                # 显式地重新抛出，以确保它能被上层捕获
                raise
            except Exception as e:
                logger.error(f"Execution failed for '{act_name}': {e}")
                raise ExecutionError(f"An error occurred while executing '{act_name}': {e}") from e
~~~~~

#### Acts 6: 在顶层控制器中捕获并处理取消事件

最后，在 `run_quipu` 函数中捕获 `OperationCancelledError`，并返回一个明确表示“取消”的 `QuipuResult`，从而终止整个流程。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError as CoreExecutionError, OperationCancelledError
from quipu.runtime.executor import Executor
~~~~~
~~~~~python
from quipu.interfaces.exceptions import ExecutionError as CoreExecutionError, OperationCancelledError
from quipu.runtime.executor import Executor
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
    try:
        app = QuipuApplication(work_dir=work_dir, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except CoreExecutionError as e:
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)

    except Exception as e:
~~~~~
~~~~~python
    try:
        app = QuipuApplication(work_dir=work_dir, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except OperationCancelledError as e:
        logger.info(f"🚫 操作已取消: {e}")
        return QuipuResult(success=False, exit_code=2, message=f"🚫 操作已取消: {e}", error=e)

    except CoreExecutionError as e:
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)

    except Exception as e:
~~~~~

### 下一步建议
我们已经完成了对整个异常处理和控制流的重构。现在，最关键的步骤是进行验证。
1.  **手动测试**: 请重新运行你最初发现问题的管道命令 `echo '...' | qd run -`。预期的行为是：程序会提示“非交互式环境，操作已取消”，然后优雅地退出，**不会**创建任何新的历史节点。
2.  **更新单元测试**: 建议为 `Executor` 和 `QuipuApplication` 添加新的单元测试，专门模拟 `confirmation_handler` 抛出 `OperationCancelledError` 的情况，并断言程序的最终返回结果和状态是正确的。
