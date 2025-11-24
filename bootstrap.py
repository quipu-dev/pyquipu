#!/usr/bin/env python3
import shutil
import subprocess
import sys
import argparse
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

def install_packages(env_path: Path, editable: bool):
    """安装包到指定环境"""
    pip_cmd = ["uv", "pip", "install", "-p", str(env_path)]
    
    # 安装测试依赖 (pytest 等) 到 dev 环境
    if editable:
        pip_cmd.extend(["pytest", "pytest-cov"])

    # 构建包路径列表
    args = []
    for pkg in PACKAGES:
        pkg_path = ROOT_DIR / pkg
        if editable:
            args.append("-e")
        args.append(str(pkg_path))
    
    print(f"📦 安装依赖到 {env_path.name} (Editable={editable})...")
    subprocess.run(pip_cmd + args, check=True)

def setup():
    """初始化双环境"""
    ENVS_DIR.mkdir(exist_ok=True)
    
    # 1. Setup Stable (Static Snapshot)
    create_venv(STABLE_DIR)
    install_packages(STABLE_DIR, editable=False)
    
    # 2. Setup Dev (Dynamic Link)
    create_venv(DEV_DIR)
    install_packages(DEV_DIR, editable=True)
    
    print("\n✅ 环境初始化完成！")
    print_usage()

def promote():
    """将当前源码晋升为 Stable 工具"""
    print("🚀 正在晋升 Dev 代码到 Stable 环境...")
    
    # 1. 简单的自测 (可选，这里先跳过，由用户自觉保证)
    
    # 2. 重建 Stable
    create_venv(STABLE_DIR)
    install_packages(STABLE_DIR, editable=False)
    
    print("\n✅ 晋升完成！现在的 'qx' 已经是最新代码的快照。")

def print_usage():
    print("-" * 50)
    print("请运行以下命令激活别名:")
    print("  source dev_setup.sh")
    print("-" * 50)
    print("命令说明:")
    print("  qx <args>   -> 使用 Stable 版 Quipu (工具)")
    print("  qd <args>   -> 使用 Dev 版 Quipu (被测对象)")
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
        # 默认行为
        if not STABLE_DIR.exists() or not DEV_DIR.exists():
            setup()
        else:
            print_usage()

if __name__ == "__main__":
    main()