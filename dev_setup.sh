#!/bin/bash

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# 定义 Python 解释器路径
STABLE_PYTHON="$SCRIPT_DIR/.envs/stable/bin/python"
DEV_PYTHON="$SCRIPT_DIR/.envs/dev/bin/python"
STABLE_BIN="$SCRIPT_DIR/.envs/stable/bin/quipu"
DEV_BIN="$SCRIPT_DIR/.envs/dev/bin/quipu"

# 别名定义

# qx: Quipu Execute (Stable)
# 用于执行 Act，修改源码
alias qx="'$STABLE_BIN'"

# qd: Quipu Dev (Development)
# 用于手动测试，调试
alias qd="'$DEV_BIN'"

# qtest: 运行测试
alias qtest="'$SCRIPT_DIR/.envs/dev/bin/pytest'"

# qpromote: 晋升代码
alias qpromote="'$SCRIPT_DIR/.envs/stable/bin/python' '$SCRIPT_DIR/bootstrap.py' promote"

echo "✅ Quipu 开发环境已激活"
echo "  🔹 qx [...]  -> 稳定版 (用于干活)"
echo "  🔸 qd [...]  -> 开发版 (用于调试)"
echo "  🧪 qtest     -> 运行测试"
echo "  🚀 qpromote  -> 将当前代码快照更新到 qx"