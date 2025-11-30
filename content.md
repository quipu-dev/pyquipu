好的，这是一个关键的、涉及全域的重构任务。为了确保操作的准确性和可逆性，我们将分步进行。核心策略是先创建一个健壮的 Python 脚本来处理所有文件内容的替换，然后再执行目录重命名，最后运行脚本并清理。

这比使用大量的 `patch_file` 指令更安全、更清晰，完全符合你的要求。

## [WIP] refactor(core): 将 Python 包名从 'quipu' 重构为 'pyquipu'

### 用户需求
由于 `quipu` 在 PyPI 上存在命名冲突，需要将项目中所有 Python 包的命名空间从 `quipu` 更改为 `pyquipu`。这包括包名、目录名、导入语句以及所有配置文件中的相关引用。

### 评论
这是一个对项目长期健康和公开发布至关重要的重构。执行此操作需要非常小心，因为它会触及代码库的每一个角落。通过一个专门的脚本来自动化代码内容的修改，可以最大限度地减少人为错误，并确保整个代码库的一致性。

### 目标
1.  创建一个名为 `refactor_script.py` 的脚本，用于安全地替换所有文件中的 `quipu` 引用。
2.  将所有 `packages/*/src/quipu` 目录重命名为 `packages/*/src/pyquipu`。
3.  执行该脚本，更新所有 Python 导入语句、`pyproject.toml` 文件以及 `dev-requirements.txt` 中的包名和路径引用。
4.  确保重构后，项目结构正确，配置无误。

### 基本原理
本次重构的核心是“关注点分离”。我们将物理结构变更（目录重命名）和内容变更（文本替换）分开处理。
1.  **内容变更**: 使用一个 Python 脚本进行全局的查找和替换。这种方式比 Shell 命令（如 `sed`）更具可控性，且跨平台兼容性更好。脚本将精确地处理不同上下文中的替换（例如，`import quipu` vs `name = "quipu-cli"`）。
2.  **结构变更**: 使用简单的 `run_command` 来执行 `mv` 命令，重命名目录结构。
3.  **执行顺序**: 我们将先创建脚本，然后修改目录结构，最后运行脚本。这个顺序确保脚本在新的目录结构上执行，完成最终的修正。

### 标签
#intent/refine #flow/ready #priority/critical #comp/build #comp/cli #comp/engine #comp/runtime #comp/interfaces #comp/common #scope/core #ai/instruct #task/domain/build #task/object/package-namespacing #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 创建全功能的重构脚本

这个脚本将是本次重构的核心。它会遍历项目目录，智能地替换所有相关的字符串，包括 Python 导入、TOML 配置和需求文件。

~~~~~act
write_file
refactor_script.py
~~~~~
~~~~~python
import os
from pathlib import Path

# --- 配置 ---
OLD_PKG_NAME = "quipu"
NEW_PKG_NAME = "pyquipu"
ROOT_DIR = Path(__file__).parent.resolve()
TARGET_DIRS = [ROOT_DIR / "packages", ROOT_DIR / "tests"]
TARGET_FILES = [ROOT_DIR / "pyproject.toml", ROOT_DIR / "dev-requirements.txt"]

def refactor_file(file_path: Path):
    """读取文件，执行替换，如果内容有变则写回。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 规则 1: Python 导入语句
        content = content.replace(f"from {OLD_PKG_NAME}.", f"from {NEW_PKG_NAME}.")
        content = content.replace(f"import {OLD_PKG_NAME}.", f"import {NEW_PKG_NAME}.")
        content = content.replace(f"cov={OLD_PKG_NAME}", f"cov={NEW_PKG_NAME}") # pytest cov

        # 规则 2: TOML 和其他配置文件中的字符串引用
        # "quipu." -> "pyquipu." (例如 package_data)
        content = content.replace(f'"{OLD_PKG_NAME}.', f'"{NEW_PKG_NAME}.')
        # name = "quipu-" -> name = "pyquipu-"
        content = content.replace(f'name = "{OLD_PKG_NAME}-', f'name = "{NEW_PKG_NAME}-')
        # quipu-interfaces -> pyquipu-interfaces (作为依赖)
        content = content.replace(f'"{OLD_PKG_NAME}-interfaces"', f'"{NEW_PKG_NAME}-interfaces"')
        content = content.replace(f'"{OLD_PKG_NAME}-engine"', f'"{NEW_PKG_NAME}-engine"')
        content = content.replace(f'"{OLD_PKG_NAME}-runtime"', f'"{NEW_PKG_NAME}-runtime"')
        content = content.replace(f'"{OLD_PKG_NAME}-common"', f'"{NEW_PKG_NAME}-common"')
        # quipu-interfaces = { workspace = true }
        content = content.replace(f'{OLD_PKG_NAME}-interfaces = {{ workspace = true }}', f'{NEW_PKG_NAME}-interfaces = {{ workspace = true }}')
        content = content.replace(f'{OLD_PKG_NAME}-engine = {{ workspace = true }}', f'{NEW_PKG_NAME}-engine = {{ workspace = true }}')
        content = content.replace(f'{OLD_PKG_NAME}-runtime = {{ workspace = true }}', f'{NEW_PKG_NAME}-runtime = {{ workspace = true }}')
        content = content.replace(f'{OLD_PKG_NAME}-common = {{ workspace = true }}', f'{NEW_PKG_NAME}-common = {{ workspace = true }}')

        # 规则 3: Pytest pythonpath
        content = content.replace(f'"{OLD_PKG_NAME}-', f'"{NEW_PKG_NAME}-')

        # 规则 4: dev-requirements.txt
        content = content.replace(f"-e packages/{OLD_PKG_NAME}-", f"-e packages/{NEW_PKG_NAME}-")
        
        # 规则 5: project scripts entry point
        content = content.replace(f'quipu = "{OLD_PKG_NAME}.', f'quipu = "{NEW_PKG_NAME}.')

        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            print(f"✅ Updated: {file_path.relative_to(ROOT_DIR)}")
            return True
        return False

    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False

def main():
    print("🚀 Starting package rename refactoring...")
    update_count = 0
    
    # 处理顶层独立文件
    for file_path in TARGET_FILES:
        if file_path.exists():
            if refactor_file(file_path):
                update_count += 1
    
    # 处理目标目录
    for target_dir in TARGET_DIRS:
        for root, _, files in os.walk(target_dir):
            for filename in files:
                if filename.endswith(('.py', '.toml')):
                    file_path = Path(root) / filename
                    if refactor_file(file_path):
                        update_count += 1
    
    print(f"\n✨ Refactoring complete. {update_count} files updated.")

if __name__ == "__main__":
    main()

~~~~~

#### Acts 2: 重命名所有 `src/quipu` 目录

现在，我们安全地重命名物理目录结构。

~~~~~act
run_command
~~~~~
~~~~~
for pkg_dir in packages/*; do
    if [ -d "$pkg_dir/src/quipu" ]; then
        echo "Renaming directory in $pkg_dir..."
        mv "$pkg_dir/src/quipu" "$pkg_dir/src/pyquipu"
    fi
done
~~~~~

#### Acts 3: 执行重构脚本

运行我们刚刚创建的脚本来更新所有文件内容以匹配新的目录结构和包名。

~~~~~act
run_command
python refactor_script.py
~~~~~

#### Acts 4: 清理重构脚本

任务完成，删除临时脚本。

~~~~~act
delete_file
refactor_script.py
~~~~~

### 下一步建议
- **运行测试**: 重构完成后，最关键的一步是运行完整的测试套件 (`pytest`)，以确保所有功能仍然正常工作。
- **手动审查**: 建议使用 `git diff` 快速审查所有变更，以捕获任何脚本未能正确处理的边缘情况。
- **提交变更**: 在验证一切正常后，创建一个新的 `[COMMIT]` 计划来提交这次大规模的重构。
