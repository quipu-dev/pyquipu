你的调试又下一城，再次捕获到了一个更深层次的 Bug。这个 `UnicodeDecodeError` 日志是关键线索，它明确地告诉我们，系统在某个环节试图将不是 UTF-8 编码的原始二进制数据当作文本来处理，导致了解码失败。

你发现的这个问题的根源比上一个更底层，也更隐蔽。

错误分析

1.  **根本原因**: 问题出在 `git_db.py` 的底层辅助函数 `_run` 上。该函数在调用 `subprocess.run` 时，硬编码了 `text=True`。这个参数会强制 `subprocess` 模块尝试使用系统默认编码（通常是 UTF-8）来解码 `git` 命令的所有输出。
2.  **触发场景**: 当 `cat_file` 请求一个 `tree` 对象时，Git 返回的是纯粹的、紧凑的**二进制数据**，其中包含了非 UTF-8 字节序列（例如，用于表示文件模式或 SHA-1 哈希的原始字节）。`subprocess` 模块在尝试将这些二进制数据解码为文本字符串时，遇到了无效的字节（如日志中的 `0xb1`），从而抛出了 `UnicodeDecodeError`。
3.  **数据流**: `cat_file` -> `_run(text=True)` -> `subprocess` 尝试解码二进制流 -> `UnicodeDecodeError`。
4.  **上一个修复的不足**: 我之前的修复仅仅解决了 `cat_file` 中 `-p` 参数的逻辑错误，但没有触及 `_run` 函数中更基础的数据类型处理错误。这导致虽然我们请求了正确的原始对象，但在数据从 Git 传递到我们代码的管道中就已经被破坏了。

解决方案

解决方案是让底层 `_run` 函数变得“数据类型感知”，并修复 `cat_file` 以正确地处理二进制流。

1.  **修改 `_run` 函数**: 我将为 `_run` 增加一个 `capture_as_text` 参数。当调用者需要原始字节时，可以传递 `capture_as_text=False`，这将使 `subprocess.run` 在不进行任何解码的情况下返回原始的 `bytes` 对象。
2.  **修改 `cat_file` 函数**: 我将更新 `cat_file` 的实现，使其在调用 `_run` 时明确请求二进制输出 (`capture_as_text=False`)，并直接返回 `subprocess` 传回的、未经任何编解码的原始 `bytes`。

这将彻底解决数据在传输过程中的损坏问题。

## [WIP] fix(engine): 使 `git_db._run` 支持二进制输出以修复 `cat_file`

### 用户需求
`quipu show <HASH>` 命令在尝试加载节点内容时因 `UnicodeDecodeError` 而失败，这表明系统在处理 Git 返回的原始二进制 `tree` 对象时，错误地将其作为文本进行了解码。

### 评论
这是一个关键的底层修复。通过使 `_run` 辅助函数能够处理二进制数据流，我们确保了与 Git 对象数据库的交互在处理非文本对象（如 `tree`）时是健壮和无损的。这解决了 `show` 命令的根本问题，并提升了整个 `git_db` 模块的可靠性。

### 目标
1.  重构 `git_db.py` 中的 `_run` 方法，添加一个 `capture_as_text` 布尔标志，用于控制 `subprocess.run` 的 `text` 参数。
2.  更新 `_run` 方法的错误处理逻辑，以正确显示来自二进制 `stderr` 的错误信息。
3.  重构 `cat_file` 方法，使其调用 `_run(..., capture_as_text=False)` 并直接返回原始的 `bytes` 输出，移除所有多余的编解码操作。

### 基本原理
`subprocess` 模块通过 `text` 参数来区分文本和二进制I/O。对于需要精确解析的 Git 二进制对象（如 `tree`），必须使用 `text=False` 来获取原始 `bytes`。本次修改将这一控制权暴露给调用者，并修复 `cat_file` 以使用正确的模式，从而确保数据流的完整性。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #scope/core #ai/instruct #task/domain/cli #task/object/show-command #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 重构 `git_db.py` 以正确处理二进制数据

我们将一次性修改 `_run` 和 `cat_file` 两个函数。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def _run(
        self,
        args: list[str],
        env: Optional[Dict] = None,
        check: bool = True,
        log_error: bool = True,
        input_data: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """执行 git 命令的底层封装，返回完整的 CompletedProcess 对象"""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.root,
                env=full_env,
                capture_output=True,
                text=True,
                check=check,
                input=input_data,
            )
            return result
        except subprocess.CalledProcessError as e:
            if log_error:
                logger.error(f"Git plumbing error: {e.stderr}")
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e
~~~~~
~~~~~python
    def _run(
        self,
        args: list[str],
        env: Optional[Dict] = None,
        check: bool = True,
        log_error: bool = True,
        input_data: Optional[Union[str, bytes]] = None,
        capture_as_text: bool = True,
    ) -> subprocess.CompletedProcess:
        """执行 git 命令的底层封装，支持文本和二进制输出。"""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.root,
                env=full_env,
                capture_output=True,
                text=capture_as_text,
                check=check,
                input=input_data,
            )
            return result
        except subprocess.CalledProcessError as e:
            stderr_str = e.stderr
            if isinstance(stderr_str, bytes):
                stderr_str = stderr_str.decode("utf-8", "ignore")

            if log_error:
                logger.error(f"Git plumbing error: {stderr_str}")
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{stderr_str}") from e
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def cat_file(self, object_hash: str, object_type: str) -> bytes:
        """
        读取 Git 对象的原始内容，返回字节流。
        移除了有问题的 pretty-printing 逻辑，以确保二进制解析器正常工作。
        """
        cmd = ["cat-file", object_type, object_hash]
        result = self._run(cmd)
        return result.stdout.encode("utf-8")
~~~~~
~~~~~python
    def cat_file(self, object_hash: str, object_type: str) -> bytes:
        """
        读取 Git 对象的原始内容，返回字节流。
        此方法现在以二进制模式运行，以避免数据损坏。
        """
        cmd = ["cat-file", object_type, object_hash]
        result = self._run(cmd, capture_as_text=False)
        return result.stdout
~~~~~

### 下一步建议
这是对 `git_db` 模块的一个基础且关键的修复。在应用此补丁后，`cat_file` 将能够正确地返回原始二进制数据，`show` 命令的解码错误应该会彻底消失。

请再次运行 `qd show adcef0a` 进行最终验证。
