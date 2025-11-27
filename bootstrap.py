#!/usr/bin/env python3
import shutil
import subprocess
import sys
import argparse
import tempfile
import os
from pathlib import Path

# 配置
ROOT_DIR = Path(__file__).parent
ENVS_DIR = ROOT_DIR / ".envs"
STABLE_DIR = ENVS_DIR / "stable"
DEV_DIR = ENVS_DIR / "dev"

PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-cli",
]


def check_uv():
    """检查 uv 是否安装"""
    if not shutil.which("uv"):
        print("❌ 错误: 未找到 'uv'。请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)


def create_venv(path: Path):
    """创建虚拟环境"""
    if path.exists():
        print(f"🔄 清理旧环境: {path}")
        shutil.rmtree(path)

    print(f"🔨 创建虚拟环境: {path}")
    subprocess.run(["uv", "venv", str(path)], check=True)


def create_setup_scripts():
    """自动生成 dev_setup.sh 和 dev_setup.fish 文件"""
    sh_content = """#!/bin/sh
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

echo "\n✅ 所有 Quipu Git 引用已成功删除。"
echo "💡 你现在可以重新运行 'quipu history migrate'。 Git 的垃圾回收 (gc) 将在未来自动清理无用的对象。"
"""

    fish_content = """#!/usr/bin/env fish

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
"""

    (ROOT_DIR / "dev_setup.sh").write_text(sh_content)
    (ROOT_DIR / "dev_setup.fish").write_text(fish_content)
    print("✨ 已生成/更新别名设置脚本 (dev_setup.sh, dev_setup.fish)")


def install_packages(env_path: Path, editable: bool):
    """安装包到指定环境"""

    # 1.如果是 Dev 环境：使用 -e 链接模式安装
    if editable:
        print(f"📦 [Dev] 正在以可编辑模式(-e)安装到 {env_path.name}...")
        pip_cmd = ["uv", "pip", "install", "-p", str(env_path), "pytest", "pytest-cov", "ruff", "pytest-timeout"]

        pkg_args = []
        for pkg in PACKAGES:
            pkg_path = ROOT_DIR / pkg
            pkg_args.extend(["-e", str(pkg_path)])

        subprocess.run(pip_cmd + pkg_args, check=True)

    # 2.如果是 Stable 环境：先构建 Wheel，再安装 Wheel
    else:
        print(f"📦 [Stable] 正在构建 Wheel 并安装到 {env_path.name} (完全隔离)...")

        # 创建临时目录存放构建好的 .whl 文件
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 第一步：构建所有包的 Wheel
            # 这会将源码编译成 .whl 文件，彻底切断与源码目录的联系
            for pkg in PACKAGES:
                pkg_src = ROOT_DIR / pkg
                print(f"   ⚙️  编译: {pkg} -> .whl")
                # 使用 uv build 进行构建 (需要 uv >= 0.3)
                # 如果没有 uv build，可以使用: python3 -m build -w <pkg> -o <tmp>
                subprocess.run(
                    ["uv", "build", str(pkg_src), "--out-dir", str(tmp_path)],
                    check=True,
                    capture_output=True,  # 减少噪音，出错会抛出异常
                )

            # 获取所有构建好的 whl 文件路径
            wheels = list(tmp_path.glob("*.whl"))
            if not wheels:
                print("❌ 错误: 未能生成 Wheel 文件")
                sys.exit(1)

            print(f"   📥 安装 {len(wheels)} 个 Wheel 文件...")

            # 第二步：安装 Wheel
            # 安装这些 whl 文件，而不是源码目录
            install_cmd = ["uv", "pip", "install", "-p", str(env_path)] + [str(w) for w in wheels]
            subprocess.run(install_cmd, check=True)


def setup():
    """初始化双环境"""
    ENVS_DIR.mkdir(exist_ok=True)

    # 1. Setup Stable (编译版)
    create_venv(STABLE_DIR)
    install_packages(STABLE_DIR, editable=False)

    # 2. Setup Dev (链接版)
    create_venv(DEV_DIR)
    install_packages(DEV_DIR, editable=True)

    create_setup_scripts()
    print("\n✅ 环境初始化完成！")
    print_usage()


def promote():
    """将当前源码晋升为 Stable 工具"""
    print("🚀 正在晋升 Dev 代码到 Stable 环境...")

    # 重建 Stable
    create_venv(STABLE_DIR)
    install_packages(STABLE_DIR, editable=False)

    # Dev 环境也需要 ruff，所以总是重新安装
    create_venv(DEV_DIR)
    install_packages(DEV_DIR, editable=True)

    create_setup_scripts()
    print("\n✅ 晋升完成！现在的 'qs' 是完全独立的二进制快照。")
    print("   (即使删除 packages/ 目录，qs 依然可以运行)")


def print_usage():
    print("-" * 50)
    print("请运行以下命令激活别名 (根据你的 shell 选择):")
    print("  source dev_setup.sh    # for bash/zsh")
    print("  source dev_setup.fish  # for fish")
    print("-" * 50)
    print("命令说明:")
    print("  qs <args>    -> Stable (独立副本，删除源码不影响)")
    print("  qd <args>    -> Dev    (实时引用，修改源码即刻生效)")
    print("  ruff <args>  -> Dev ruff (用于格式化和检查)")
    print("-" * 50)


def main():
    check_uv()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="初始化所有环境")
    subparsers.add_parser("promote", help="将当前源码重新安装到 Stable 环境")

    args = parser.parse_args()
    if args.command == "init":
        setup()
    elif args.command == "promote":
        promote()
    else:
        if not STABLE_DIR.exists() or not DEV_DIR.exists():
            setup()
        else:
            print_usage()


if __name__ == "__main__":
    main()
