#!/usr/bin/env python3
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- 配置 ---
# 项目根目录
ROOT_DIR = Path(__file__).parent.resolve()
# 默认安装目标目录
INSTALL_DIR = Path.home() / ".quipu_app"
# Quipu 的核心包
PACKAGES = [
    "packages/quipu-interfaces",
    "packages/quipu-common",
    "packages/quipu-engine",
    "packages/quipu-runtime",
    "packages/quipu-cli",
]


def check_uv():
    """检查 uv 是否已安装"""
    if not shutil.which("uv"):
        print("❌ 错误: 未找到 'uv' 命令。")
        print("   请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)
    print("✅ uv 环境检查通过。")


def create_venv(path: Path):
    """在指定路径创建或重建一个干净的虚拟环境"""
    if path.exists():
        print(f"🔄 检测到旧的安装目录，正在清理: {path}")
        shutil.rmtree(path)

    print(f"🔨 正在创建新的虚拟环境: {path}")
    subprocess.run(["uv", "venv", str(path)], check=True, capture_output=True)


def install_quipu_stable(env_path: Path):
    """利用 uv 工作区功能直接安装整个 Quipu 应用"""
    print("📦 正在安装 Quipu...")

    # uv 会自动识别工作区，并解析根 pyproject.toml 中的所有依赖项
    install_cmd = ["uv", "pip", "install", "-p", str(env_path), str(ROOT_DIR)]

    # 我们不捕获输出，这样用户可以看到 uv 的进度条
    subprocess.run(install_cmd, check=True)


def print_post_install_instructions(env_path: Path):
    """打印安装完成后的指引"""
    bin_path = env_path / "bin"
    quipu_executable = bin_path / "quipu"

    print("\n" + "=" * 60)
    print("🎉 Quipu 安装成功！")
    print("=" * 60)
    print(f"\n可执行文件位于: {quipu_executable}")
    print("\n下一步, 请将此目录添加到你的 shell 的 PATH 环境变量中。")
    print("这样你就可以在任何地方直接运行 'quipu' 命令了。")
    print("\n请将以下这行命令添加到你的 shell 配置文件中 (例如 ~/.bashrc, ~/.zshrc, 或 ~/.config/fish/config.fish):")
    print("\n" + "-" * 20 + " (复制并粘贴此行) " + "-" * 20)
    print(f'export PATH="{bin_path}:$PATH"')
    print("-" * 62)
    print("\n添加后，请重启你的终端或运行 `source <你的配置文件>` 使其生效。")
    print("然后，通过运行 `quipu --help` 来验证安装。")
    print("\n感谢使用 Quipu！")


def main():
    """主执行函数"""
    print("--- Quipu 一键安装程序 ---")

    check_uv()
    create_venv(INSTALL_DIR)
    install_quipu_stable(INSTALL_DIR)
    print_post_install_instructions(INSTALL_DIR)


if __name__ == "__main__":
    main()
