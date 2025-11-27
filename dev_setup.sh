#!/bin/sh
set -e

# 检查当前目录是否为 Git 仓库
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "错误: 当前目录不是一个 Git 仓库。"
    exit 1
fi

echo "🔍 正在查找所有 Quipu Git 引用 (refs/quipu/*)..."

# 查找所有在 refs/quipu/ 命名空间下的引用
QUIPU_REFS=$(git for-each-ref --format='%(refname)' refs/quipu/)

if [ -z "$QUIPU_REFS" ]; then
    echo "✅ 未找到任何 Quipu 引用，无需清理。"
    exit 0
fi

echo "🗑️  即将删除以下 Quipu 引用:"
echo "$QUIPU_REFS"
echo ""

# 使用 xargs 安全地删除所有找到的引用
# -r: 如果输入为空，则不执行命令
# -n 1: 每次处理一个参数
echo "$QUIPU_REFS" | xargs -r -n 1 git update-ref -d

echo "
✅ 所有 Quipu Git 引用已成功删除。"
echo "💡 你现在可以重新运行 'quipu history migrate'。 Git 的垃圾回收 (gc) 将在未来自动清理无用的对象。"
