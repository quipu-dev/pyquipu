from . import basic, check, git, memory, read, refactor, shell


def register_core_acts(executor):
    """注册所有核心 Acts"""
    basic.register(executor)
    check.register(executor)
    git.register(executor)
    memory.register(executor)
    read.register(executor)
    refactor.register(executor)
    shell.register(executor)
