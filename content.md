# docs-rename 自动化文档术语迁移

## 目标
将 `docs/` 目录及 `README.md` 中过时的术语 "Axon" 批量替换为 "Quipu"。

## 基本原理
采用脚本处理文本替换可确保全局一致性，避免人工编辑遗漏。此操作作为文档更新的第一阶段，为后续的架构描述更新 (Phase 2) 准备基础语料。脚本仅使用 Python 标准库，无需额外依赖。

## 标签
 #docs #chore #migration

---

## Script

### Act 1: 环境验证

验证目标路径是否存在。

~~~~~act
check_files_exist
~~~~~

~~~~~text
docs
README.md
~~~~~

### Act 2: 部署迁移脚本

创建一个临时 Python 脚本，遍历 `docs/` 目录和 `README.md`，执行大小写敏感的术语替换。

~~~~~act
write_file
~~~~~

~~~~~path
migrate_docs_temp.py
~~~~~

~~~~~python
import os
from pathlib import Path

TARGETS = [Path("docs"), Path("README.md"), Path("TODO.md")]
REPLACEMENTS = {
    "Axon": "Quipu",
    "axon": "quipu",
    ".axon": ".quipu"
}

def migrate_file(file_path: Path):
    try:
        content = file_path.read_text(encoding="utf-8")
        new_content = content
        
        for old, new in REPLACEMENTS.items():
            new_content = new_content.replace(old, new)
            
        if content != new_content:
            file_path.write_text(new_content, encoding="utf-8")
            print(f"✅ Updated: {file_path}")
        else:
            print(f"➖ Skipped: {file_path}")
            
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")

def main():
    print("🚀 Starting Documentation Migration (Axon -> Quipu)...")
    
    for target in TARGETS:
        if not target.exists():
            print(f"⚠️ Target not found: {target}")
            continue
            
        if target.is_file():
            migrate_file(target)
        elif target.is_dir():
            for root, _, files in os.walk(target):
                for file in files:
                    if file.endswith(".md"):
                        migrate_file(Path(root) / file)

    print("🏁 Migration Completed.")

if __name__ == "__main__":
    main()
~~~~~

### Act 3: 执行迁移

运行脚本进行批量替换。

~~~~~act
run_command
~~~~~

~~~~~bash
python3 migrate_docs_temp.py
~~~~~

### Act 4: 清理现场

删除临时的迁移脚本。

~~~~~act
delete_file
~~~~~

~~~~~path
migrate_docs_temp.py
~~~~~