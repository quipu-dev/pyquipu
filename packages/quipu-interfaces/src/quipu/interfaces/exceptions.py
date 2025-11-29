class AIFSOpsError(Exception):
    """基础异常类"""

    pass


class ParseError(AIFSOpsError):
    """Markdown 解析错误"""

    pass


class ExecutionError(AIFSOpsError):
    """操作执行错误"""

    pass


class OperationCancelledError(ExecutionError):
    """当用户取消一个操作时引发"""

    pass
