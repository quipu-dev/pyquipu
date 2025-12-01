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
    "packages/quipu-application",
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
    """构建所有 Quipu 包的 Wheel 文件，并将其安装到指定环境"""
    print("📦 正在构建并安装 Quipu (稳定版)...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 步骤 1: 将所有源码包构建为 .whl 文件
        print("   -> 阶段 1/2: 编译源码包...")
        for pkg in PACKAGES:
            pkg_src_path = ROOT_DIR / pkg
            if not pkg_src_path.exists():
                print(f"❌ 错误: 找不到源码包目录 {pkg_src_path}")
                sys.exit(1)

            print(f"      - 正在编译 {pkg}...")
            subprocess.run(
                ["uv", "build", str(pkg_src_path), "--out-dir", str(tmp_path)],
                check=True,
                capture_output=True,
            )

        wheels = list(tmp_path.glob("*.whl"))
        if not wheels:
            print("❌ 错误: 未能生成任何 Wheel 文件，构建失败。")
            sys.exit(1)

        # 步骤 2: 将构建好的 .whl 文件安装到虚拟环境中
        print(f"   -> 阶段 2/2: 正在将 {len(wheels)} 个组件安装到环境中...")
        install_cmd = ["uv", "pip", "install", "-p", str(env_path)] + [str(w) for w in wheels]
        subprocess.run(install_cmd, check=True, capture_output=True)


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
