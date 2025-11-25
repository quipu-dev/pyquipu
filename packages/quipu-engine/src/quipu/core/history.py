import logging
import re
from pathlib import Path
from typing import Dict, Optional, List
import yaml
from quipu.core.models import QuipuNode
from datetime import datetime

logger = logging.getLogger(__name__)

# 放宽对 input_hash 的校验，以兼容损坏或非标准的历史文件名
FILENAME_PATTERN = re.compile(
    r"(.+?)_([0-9a-f]{40})_(\d{14})\.md"
)

def _parse_frontmatter(text: str) -> tuple[Dict, str]:
    if not text.startswith("---"): return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3: return {}, text
    _, frontmatter_str, content = parts
    try:
        meta = yaml.safe_load(frontmatter_str) or {}
        return meta, content.strip()
    except yaml.YAMLError:
        return {}, text

def load_all_history_nodes(history_dir: Path) -> List[QuipuNode]:
    """
    (For UI & Graphing)
    加载所有历史事件，构建完整的父子关系图，并返回所有节点的列表。
    """
    if not history_dir.exists(): return []

    all_nodes: List[QuipuNode] = []
    nodes_by_output: Dict[str, List[QuipuNode]] = {}

    for file_path in history_dir.glob("*.md"):
        match = FILENAME_PATTERN.match(file_path.name)
        if not match:
            logger.warning(f"跳过格式不匹配的历史文件: {file_path.name}")
            continue
        
        input_hash, output_hash, ts_str = match.groups()
        try:
            full_content = file_path.read_text("utf-8")
            meta, body_content = _parse_frontmatter(full_content)
            
            node_type = meta.get("type", "unknown")
            # For legacy nodes, we generate a summary on the fly.
            summary = "No description"
            if node_type == 'plan':
                # Robust heuristic: find the first non-empty, non-fence line inside `act` block
                in_act_block = False
                temp_summary = ""
                for line in body_content.strip().split('\n'):
                    clean_line = line.strip()
                    if clean_line.startswith(('~~~act', '```act')):
                        in_act_block = True
                        continue
                    if in_act_block:
                        if clean_line.startswith(('~~~', '```')):
                            break
                        if clean_line:
                            temp_summary = clean_line
                            break
                summary = temp_summary
                if not summary:
                    # Fallback: find first non-empty line
                    summary = next((line.strip() for line in body_content.strip().split('\n') if line.strip()), "Plan executed")
            elif node_type == 'capture':
                # Prioritize user message from the body
                match = re.search(r"### 💬 备注:\n(.*?)\n\n", body_content, re.DOTALL)
                if match:
                    summary = match.group(1).strip()
                else:
                    summary = "Workspace changes captured"

            node = QuipuNode(
                input_tree=input_hash, output_tree=output_hash,
                timestamp=datetime.strptime(ts_str, "%Y%m%d%H%M%S"),
                filename=file_path, node_type=node_type,
                content=body_content,
                summary=(summary[:75] + '...') if len(summary) > 75 else summary
            )
            all_nodes.append(node)
            nodes_by_output.setdefault(output_hash, []).append(node)
        except Exception as e:
            logger.error(f"加载历史节点失败 {file_path.name}: {e}")

    # 对每个 output_hash 对应的节点列表按时间戳排序
    # 这是构建父子关系所必需的，确保子节点总能找到时间上在其之前的父节点
    for nodes in nodes_by_output.values():
        nodes.sort(key=lambda n: n.timestamp)

    # 构建父子关系
    for node in all_nodes:
        # 寻找潜在的父节点 (其 output_tree 是当前节点的 input_tree)
        potential_parents = nodes_by_output.get(node.input_tree, [])
        # 过滤出时间戳在当前节点之前的父节点
        valid_parents = [p for p in potential_parents if p.timestamp < node.timestamp]
        if valid_parents:
            # 选择时间戳最新的那个作为父节点
            parent_node = max(valid_parents, key=lambda p: p.timestamp)
            node.parent = parent_node
            parent_node.children.append(node)

    # 对每个节点的子节点列表按时间戳排序
    for node in all_nodes:
        node.children.sort(key=lambda n: n.timestamp)
        
    return all_nodes