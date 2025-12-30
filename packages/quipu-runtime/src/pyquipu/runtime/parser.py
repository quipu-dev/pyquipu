import re
from abc import ABC, abstractmethod
from typing import List, Optional

from pyquipu.interfaces.types import Statement


class BaseParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> List[Statement]:
        pass


class StateBlockParser(BaseParser):
    def __init__(self, fence_char: str):
        self.fence_char = fence_char

    def parse(self, text: str) -> List[Statement]:
        statements: List[Statement] = []
        current_statement: Optional[Statement] = None

        # keepends=True 保留换行符，确保内容原样还原
        lines = text.splitlines(keepends=True)

        in_block = False
        current_fence = ""  # 记录开始时的围栏字符串（不含语言标签）
        current_lang = ""
        block_content: List[str] = []

        for line in lines:
            stripped_line = line.strip()

            if not in_block:
                # --- 状态：寻找块的开始 ---
                # 规则：以 fence_char 开头，至少 3 个字符
                if stripped_line.startswith(self.fence_char * 3):
                    # 分离 fence 和 language tag
                    # 例如: "~~~~ python.old" -> fence="~~~~", lang="python.old"

                    # 计算 fence 长度
                    fence_len = 0
                    for char in stripped_line:
                        if char == self.fence_char:
                            fence_len += 1
                        else:
                            break

                    # 提取元数据
                    fence_str = stripped_line[:fence_len]
                    lang_str = stripped_line[fence_len:].strip()

                    # 切换状态
                    in_block = True
                    current_fence = fence_str
                    current_lang = lang_str.lower()
                    block_content = []
                else:
                    # 普通文本行，忽略
                    pass

            else:
                # --- 状态：在块内 ---
                # 检查是否是结束围栏
                # 规则：去除首尾空白后，必须与开始围栏完全一致
                if stripped_line == current_fence:
                    # 块结束
                    in_block = False

                    # 处理收集到的内容
                    full_content = "".join(block_content)

                    # 如果内容末尾有换行符（通常都有），且它是因为上一行内容自带的，我们保留。
                    # 但如果是空块，或者为了符合直觉，通常不处理。
                    # 在这里我们保持最原始的数据，但在 splitlines 时最后一行通常带有 \n。
                    # 唯独要注意的是：编辑器通常会在闭合 fence 前加一个换行，这个换行在逻辑上属于内容的一部分吗？
                    # 标准 Markdown：是的。
                    # 但为了 patch_file 的方便，如果最后一个字符是换行，通常意味着是块的结束。
                    # 我们这里做一个微调：如果最后一行以 \n 结尾，我们可以选择去掉它，
                    # 使得 ```text\nA\n``` 解析为 "A\n" 而不是 "A\n"。
                    # 这取决于 splitlines 的行为。

                    # 这里采用一个实用策略：strip 掉尾部的一个换行符。
                    if full_content.endswith("\n"):
                        full_content = full_content[:-1]

                    # 根据语言标签分发
                    if current_lang == "act":
                        # 指令块：开始新语句
                        action_name = full_content.strip()
                        new_stmt = {"act": action_name, "contexts": []}
                        statements.append(new_stmt)
                        current_statement = new_stmt
                    else:
                        # 上下文块：追加到当前语句
                        if current_statement is not None:
                            current_statement["contexts"].append(full_content)

                    # 重置状态
                    current_fence = ""
                    current_lang = ""
                    block_content = []

                else:
                    # 收集内容
                    block_content.append(line)

        return statements


class BacktickParser(StateBlockParser):
    def __init__(self):
        super().__init__("`")


class TildeParser(StateBlockParser):
    def __init__(self):
        super().__init__("~")


# --- 解析器注册表 ---

_PARSERS = {
    "backtick": BacktickParser,
    "tilde": TildeParser,
}


def get_parser(name: str) -> BaseParser:
    if name not in _PARSERS:
        raise ValueError(f"未知的解析器: {name}. 可用选项: {list(_PARSERS.keys())}")
    return _PARSERS[name]()


def list_parsers() -> List[str]:
    return list(_PARSERS.keys())


def detect_best_parser(text: str) -> str:
    # 宽松匹配：行首 fence + 任意空白 + act
    pattern = re.compile(r"^([`~]{3,})\s*act\b", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)

    if match:
        fence_str = match.group(1)
        if fence_str.startswith("~"):
            return "tilde"
        return "backtick"

    return "backtick"
