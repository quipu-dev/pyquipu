#!/usr/bin/env fish

# 获取脚本所在目录的绝对路径
set SCRIPT_DIR (dirname (status --current-filename))

# 定义 Python 解释器路径
set STABLE_PYTHON "$SCRIPT_DIR/.envs/stable/bin/python"
set DEV_PYTHON "$SCRIPT_DIR/.envs/dev/bin/python"
set STABLE_BIN "$SCRIPT_DIR/.envs/stable/bin/quipu"
set DEV_BIN "$SCRIPT_DIR/.envs/dev/bin/quipu"

# 别名定义

# qs: Quipu Execute (Stable)
# 用于执行 Act，修改源码
alias qs "$STABLE_BIN"

# qd: Quipu Dev (Development)
# 用于手动测试，调试
alias qd "$DEV_BIN"

# qtest: 运行测试
alias qtest "$SCRIPT_DIR/.envs/dev/bin/pytest"

# ruff: 代码格式化与检查
alias ruff "$SCRIPT_DIR/.envs/dev/bin/ruff"

# qpromote: 晋升代码
alias qpromote "$STABLE_PYTHON $SCRIPT_DIR/bootstrap.py promote"

echo "✅ Quipu 开发环境已激活"
echo "  🔹 qs [...]  -> 稳定版 (用于干活)"
echo "  🔸 qd [...]  -> 开发版 (用于调试)"
echo "  🧪 qtest     -> 运行测试"
echo "  💅 ruff      -> 代码格式化与检查"
echo "  🚀 qpromote  -> 将当前代码快照更新到 qs"
