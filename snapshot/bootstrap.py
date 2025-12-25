#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

# 配置
ROOT_DIR = Path(__file__).parent
ENVS_DIR = ROOT_DIR / ".envs"
STABLE_DIR = ENVS_DIR / "stable"
DEV_DIR = ENVS_DIR / "dev"


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
    subprocess.run(["uv", "venv", str(path)], check=True, capture_output=True)


def install_packages(env_path: Path, editable: bool):
    """利用 uv 工作区功能，从根 pyproject.toml 安装包"""
    if editable:
        print(f"📦 [Dev] 正在以可编辑模式安装开发环境到 {env_path.name}...")
        # 安装根包的 [dev] 依赖项，它包含了所有子包和开发工具
        # 使用 -e 确保所有本地包都是可编辑的
        install_cmd = ["uv", "pip", "install", "-p", str(env_path), "-e", f"{ROOT_DIR}[dev]"]
    else:
        print(f"📦 [Stable] 正在安装生产环境到 {env_path.name}...")
        # 直接安装根包，uv 会自动解析工作区内的子包依赖
        install_cmd = ["uv", "pip", "install", "-p", str(env_path), str(ROOT_DIR)]

    # 我们不捕获输出，这样用户可以看到 uv 的进度条
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

    print("\n✅ 环境初始化完成！")
    print_usage()


def promote():
    """将当前源码晋升为 Stable 工具"""
    print("🚀 正在晋升 Dev 代码到 Stable 环境...")

    # 重建 Stable
    create_venv(STABLE_DIR)
    install_packages(STABLE_DIR, editable=False)

    print("\n✅ 晋升完成！现在的 'qs' 是当前代码的完全独立快照。")


def update_dev_env():
    """仅更新开发环境"""
    print("🔄 正在更新 Dev 环境...")
    if not DEV_DIR.exists():
        print("   -> Dev 环境不存在，将创建一个新环境。")
        create_venv(DEV_DIR)
    install_packages(DEV_DIR, editable=True)
    print("\n✅ Dev 环境更新完成。")


def print_usage():
    print("-" * 50)
    print("环境已就绪。请根据你的 shell 配置别名，例如:")
    print("  alias qs='$PWD/.envs/stable/bin/quipu'")
    print("  alias qd='$PWD/.envs/dev/bin/quipu'")
    print("  alias qtest='$PWD/.envs/dev/bin/pytest'")
    print("  alias ruff='$PWD/.envs/dev/bin/ruff'")
    print("-" * 50)
    print("命令说明:")
    print("  qs [...]    -> 稳定版 (用于执行)")
    print("  qd [...]    -> 开发版 (用于调试)")
    print("  qtest       -> 运行测试")
    print("  ruff        -> 格式化与检查")
    print("-" * 50)


def main():
    check_uv()
    parser = argparse.ArgumentParser(description="Quipu 开发环境管理脚本")
    subparsers = parser.add_subparsers(dest="command", help="可用的命令")

    subparsers.add_parser("init", help="初始化所有环境 (stable 和 dev)")
    subparsers.add_parser("promote", help="将当前源码快照更新到 stable 环境")
    subparsers.add_parser("dev", help="仅更新 dev 环境 (例如，在添加新包后)")

    args = parser.parse_args()
    if args.command == "init":
        setup()
    elif args.command == "promote":
        promote()
    elif args.command == "dev":
        update_dev_env()
    else:
        if not STABLE_DIR.exists() or not DEV_DIR.exists():
            print("💡 环境尚未初始化，正在执行首次设置...")
            setup()
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
