Of course. This is the perfect final step to capitalize on the monorepo setup we just created.

The `install_quipu.py` script currently performs a complex, manual build-and-install process. It reinvents the wheel (pun intended) of what a modern package manager like `uv` is designed to do automatically with a well-configured workspace.

Now that our root `pyproject.toml` declaratively defines the entire application via its `dependencies` list, we can radically simplify the installation script. The entire multi-step process of building each package individually can be replaced with a single `uv pip install .` command pointed at the project root.

I will generate a plan to refactor `install_quipu.py` to leverage our new, robust setup.

## [WIP] chore(build): Simplify install script to use workspace resolver

### 用户需求
重构 `install_quipu.py` 脚本，使其不再手动构建每个子包，而是直接利用 `uv` 的工作区解析能力，通过一条 `uv pip install .` 命令来完成整个应用的安装。

### 评论
这是一个重要的维护性改进。通过将复杂的、命令式的构建逻辑（`for pkg in PACKAGES...`）替换为单一的、声明式的安装命令，我们：
1.  **降低了维护成本**：未来新增或删除包时，只需更新根 `pyproject.toml` 的 `dependencies` 列表，无需再修改安装脚本。
2.  **提高了可靠性**：我们依赖 `uv` 官方的、经过充分测试的依赖解析和安装逻辑，而不是我们自己编写的临时脚本。
3.  **遵循了 DRY 原则**：项目的依赖关系现在只定义在一个地方——根 `pyproject.toml`。

### 目标
1.  修改 `install_quipu.py` 文件。
2.  重写 `install_quipu_stable` 函数，将其中的手动 `uv build` 循环和 `uv pip install *.whl` 命令，替换为单个 `uv pip install <project_root>` 命令。

### 基本原理
我们已经将项目配置为一个“伞形包”，其 `[project].dependencies` 列出了所有生产所需的 `pyquipu-*` 子包。当 `uv pip install .` 在项目根目录运行时，`uv` 的工作区解析器会自动识别这是一个工作区，并安装根包及其在工作区中声明的所有依赖项。这使得安装脚本的逻辑可以被极大地简化。

### 标签
#intent/tooling #flow/ready #priority/medium #comp/build #scope/dx #ai/instruct #task/domain/build #task/object/install-script #task/action/refactor #task/state/end #task/status/completed

---
### Script

#### Acts 1: 简化安装脚本的实现

我们将用一个更简单、更健壮的实现来替换 `install_quipu_stable` 函数的整个主体。

~~~~~act
patch_file
install_quipu.py
~~~~~
~~~~~python.old
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
~~~~~
~~~~~python.new
def install_quipu_stable(env_path: Path):
    """利用 uv 工作区功能直接安装整个 Quipu 应用"""
    print("📦 正在安装 Quipu...")

    # uv 会自动识别工作区，并解析根 pyproject.toml 中的所有依赖项
    install_cmd = ["uv", "pip", "install", "-p", str(env_path), str(ROOT_DIR)]

    # 我们不捕获输出，这样用户可以看到 uv 的进度条
    subprocess.run(install_cmd, check=True)
~~~~~

### 下一步建议
请执行此计划。
完成后，你可以通过运行 `python install_quipu.py` 来验证其功能。它应该能在一个干净的 `~/.quipu_app` 目录中成功安装完整的 Quipu CLI 工具，并且过程比之前更快、输出更清晰。
