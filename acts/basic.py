import os
from pathlib import Path
from typing import List
from core.executor import Executor, ExecutionError

def register_basic_acts(executor: Executor):
    """注册基础文件系统操作"""
    executor.register("write_file", _write_file)
    executor.register("replace", _replace)

def _write_file(executor: Executor, args: List[str]):
    """
    Act: write_file
    Args: [path, content]
    """
    if len(args) < 2:
        raise ExecutionError("write_file 需要至少两个参数: [path, content]")
    
    # 参数提取
    raw_path = args[0]
    content = args[1]
    
    target_path = executor.resolve_path(raw_path)
    
    # 确保父目录存在
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ [Write] 文件已写入: {target_path.relative_to(executor.root_dir)}")

def _replace(executor: Executor, args: List[str]):
    """
    Act: replace
    Args: [path, old_string, new_string]
    """
    if len(args) < 3:
        raise ExecutionError("replace 需要至少三个参数: [path, old_string, new_string]")
    
    raw_path = args[0]
    old_str = args[1]
    new_str = args[2]
    
    target_path = executor.resolve_path(raw_path)
    
    if not target_path.exists():
        raise ExecutionError(f"文件未找到: {raw_path}")
    
    with open(target_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if old_str not in content:
        # 这是一个常见错误，提示用户检查上下文
        raise ExecutionError(f"在文件 {raw_path} 中未找到指定的旧文本。\n请确保 Markdown 块中的空格和换行完全匹配。")
    
    # 执行替换 (默认只替换第一个匹配项，以防误伤)
    new_content = content.replace(old_str, new_str, 1)
    
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print(f"✅ [Replace] 文件内容已更新: {target_path.relative_to(executor.root_dir)}")
