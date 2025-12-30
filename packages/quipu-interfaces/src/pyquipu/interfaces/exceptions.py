class AIFSOpsError(Exception):
    pass


class ParseError(AIFSOpsError):
    pass


class ExecutionError(AIFSOpsError):
    pass


class OperationCancelledError(ExecutionError):
    pass
