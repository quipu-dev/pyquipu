Of course. This `bootstrap.py` script suffers from the exact same problem as the old `install_quipu.py`: it contains complex, imperative logic that manually replicates the job of the package manager.

Now that we have a powerful, declarative `pyproject.toml` at the root of our workspace, we can simplify this script dramatically, making it more robust and easier to maintain.

## [WIP] chore(build): Refactor bootstrap.py to leverage workspace root

### 用户需求
重构 `bootstrap.py` 脚本，使其完全依赖根 `pyproject.toml` 文件作为依赖关系的唯一真实来源，从而简化其实现并消除冗余的包发现逻辑。

### 评论
这是我们 monorepo 配置优化的最后一公里。通过这次重构，我们将彻底消除项目中所有手动的、易错的包安装逻辑。`bootstrap.py` 将不再需要知道 `packages/` 目录下有哪些包，或者开发依赖具体是什么——所有这些信息都已在 `pyproject.toml` 中声明。这使得整个开发环境的搭建流程完全由单一的配置文件驱动，极大地提升了项目的可维护性和一致性。

### 目标
1.  修改 `bootstrap.py` 文件。
2.  移除不再需要的 `find_packages` 函数和全局 `PACKAGES` 变量。
3.  重写 `install_packages` 函数：
    *   对于 **stable** 环境，使用 `uv pip install .` 命令。
    *   对于 **dev** 环境，使用 `uv pip install ".[dev]"` 命令。

### 基本原理
我们利用 `uv` 对工作区的原生支持，将复杂的安装逻辑委托给它：
-   `uv pip install .`: `uv` 读取根 `pyproject.toml`，并安装 `[project].dependencies` 中列出的所有生产包。由于未使用 `-e`，它会构建 wheels 并进行安装，这正是 "stable" 环境所需要的。
-   `uv pip install ".[dev]"`: `uv` 读取根 `pyproject.toml`，并安装 `[project].dependencies` 中的所有包，**以及** `[project.optional-dependencies].dev` 中定义的所有开发工具和本地包。配合 `-e` 标志（如果需要的话，但 `uv` 在工作区内默认行为类似可编辑模式），这完美地构建了我们的 "dev" 环境。

### 标签
#intent/tooling #flow/ready #priority/high #comp/build #scope/dx #ai/instruct #task/domain/build #task/object/bootstrap-script #task/action/refactor #task/state/end #task/status/completed

---
### Script

#### Acts 1: 简化 bootstrap.py

我们将用一个极其简洁的版本替换掉 `find_packages` 和 `install_packages` 这两个函数。

~~~~~act
patch_file
bootstrap.py
~~~~~
~~~~~python.old
def find_packages(root: Path) -> List[Path]:
    """自动发现 packages 目录下的所有包"""
    packages_dir = root / "packages"
    found = []
    if not packages_dir.is_dir():
        return []
    for pkg_path in packages_dir.iterdir():
        if pkg_path.is_dir() and (pkg_path / "pyproject.toml").exists():
            found.append(pkg_path)
    print(f"🔍 自动发现 {len(found)} 个包: {[p.name for p in found]}")
    return found


PACKAGES = find_packages(ROOT_DIR)


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
    """安装包到指定环境"""
    if not PACKAGES:
        print("⚠️  警告: 未在 packages/ 目录下发现任何包，跳过安装。")
        return

    # 1.如果是 Dev 环境：使用 -e 链接模式安装
    if editable:
        print(f"📦 [Dev] 正在以可编辑模式(-e)安装到 {env_path.name}...")
        pip_cmd = ["uv", "pip", "install", "-p", str(env_path), "pytest", "pytest-cov", "ruff", "pytest-timeout"]

        pkg_args = []
        for pkg_path in PACKAGES:
            pkg_args.extend(["-e", str(pkg_path)])

        subprocess.run(pip_cmd + pkg_args, check=True)

    # 2.如果是 Stable 环境：先构建 Wheel，再安装 Wheel
    else:
        print(f"📦 [Stable] 正在构建 Wheel 并安装到 {env_path.name} (完全隔离)...")

        # 创建临时目录存放构建好的 .whl 文件
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 第一步：构建所有包的 Wheel
            for pkg_src in PACKAGES:
                print(f"   ⚙️  编译: {pkg_src.name} -> .whl")
                subprocess.run(
                    ["uv", "build", str(pkg_src), "--out-dir", str(tmp_path)],
                    check=True,
                    capture_output=True,
                )

            wheels = list(tmp_path.glob("*.whl"))
            if not wheels:
                print("❌ 错误: 未能生成 Wheel 文件")
                sys.exit(1)

            print(f"   📥 安装 {len(wheels)} 个 Wheel 文件...")

            # 第二步：安装 Wheel
            install_cmd = ["uv", "pip", "install", "-p", str(env_path)] + [str(w) for w in wheels]
            subprocess.run(install_cmd, check=True, capture_output=True)
~~~~~
~~~~~python.new
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
~~~~~

### 下一步建议
请执行此计划。
完成后，你可以运行 `python bootstrap.py init` 来彻底重建你的开发和稳定环境。整个过程将由 `uv` 的工作区解析器驱动，更加快速和可靠。
