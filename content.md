好的，我将根据你的需求，创建一个 `plan.md` 文件。这个计划的目标是生成一个名为 `install_quipu.py` 的新脚本，它借鉴了 `bootstrap.py` 的稳定版安装逻辑，但去除了所有面向开发者的功能（如双环境、`ruff`、`pytest` 等），旨在为最终用户提供一个简单、直接的一键安装体验。

## [WIP] feat: 创建一键式用户安装脚本 install_quipu.py

### 用户需求
需要一个简单的一键式脚本，让用户可以从 `pyquipu` 的源码克隆中，将 Quipu 应用程序安装到一个独立的、隔离的环境中。这个脚本应只关注最终的可用性，不应包含开发者工具（如 `ruff`, `pytest`）或复杂的双环境设置。

### 评论
这是一个关键的用户体验改进。现有的 `bootstrap.py` 脚本是为 Quipu 自身的开发工作流设计的，对普通用户来说过于复杂。提供一个清晰、单一用途的 `install_quipu.py` 将大大降低用户的使用门槛，并为后续的打包和分发工作奠定基础。

### 目标
1.  创建一个新的 `install_quipu.py` 脚本。
2.  该脚本将 Quipu 的所有包构建为独立的 `wheel` 文件，并将其安装到一个专用的虚拟环境中。
3.  安装过程不包含任何开发依赖。
4.  脚本执行完毕后，向用户提供清晰的指令，告知如何将 `quipu` 可执行文件添加到系统的 `PATH` 中。

### 基本原理
我们将复用 `bootstrap.py` 中 `install_packages(..., editable=False)` 的核心逻辑。该逻辑通过 `uv build` 将 `packages/` 目录下的所有源码包编译成标准的 `.whl` 文件。然后，使用 `uv pip install` 将这些编译好的 `wheel` 文件安装到一个在用户主目录下新建的 `.quipu_app/` 虚拟环境中。这种方式确保了安装后的 Quipu 程序与原始的源码目录完全解耦，是一个独立的、稳定的快照。

### 标签
#intent/build #flow/ready #priority/high #comp/build #scope/ux #scope/dx #ai/instruct #task/domain/build #task/object/installer-script #task/action/creation #task/state/begin

---

### Script

#### Acts 1: 创建 `install_quipu.py` 脚本文件

我们将生成 `install_quipu.py` 脚本的完整内容，并将其写入项目根目录。

~~~~~act
write_file
install_quipu.py
~~~~~
~~~~~python
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
~~~~~

### 下一步建议
1.  **增加可执行权限**: 在 `plan.md` 执行成功后，为新创建的 `install_quipu.py` 脚本添加可执行权限，以便用户可以直接运行 (`./install_quipu.py`)。
2.  **更新文档**: 在 `README.md` 中添加关于如何使用此脚本从源码安装 Quipu 的说明。
3.  **测试脚本**: 在一个干净的环境中运行此脚本，验证安装过程是否顺畅，以及安装后的 `quipu` 命令是否能正常工作。
