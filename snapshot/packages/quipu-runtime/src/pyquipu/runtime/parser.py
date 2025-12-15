import re
from abc import ABC, abstractmethod
from typing import List

from pyquipu.interfaces.types import Statement


class BaseParser(ABC):
    """所有解析器的抽象基类"""

    @abstractmethod
    def parse(self, text: str) -> List[Statement]:
        """
        将文本解析为语句列表。
        必须由子类实现。
        """
        pass


class RegexBlockParser(BaseParser):
    """
    支持变长围栏（Variable Length Fence）的解析器。
    逻辑：
    1. 扫描所有符合 `^([`~]{3,})(\\w*)$` 格式的行（作为代码块头）。
    2. 记录该头的 fence 字符串（如 `~~~~`）。
    3. 向后寻找第一个**完全匹配**该 fence 且独占一行的字符串作为结尾。
    """

    def __init__(self, fence_char: str):
        self.fence_char = fence_char
        # 匹配：行首 + 3个及以上字符 + 可选语言标记 + 行尾
        # capture group 1: fence (e.g. "~~~~")
        # capture group 2: lang (e.g. "python")
        self.start_pattern = re.compile(rf"^({re.escape(fence_char)}{{3,}})(\w*(?:\.\w+)*)\s*$", re.MULTILINE)

    def parse(self, text: str) -> List[Statement]:
        statements: List[Statement] = []
        current_statement: Statement | None = None

        cursor = 0
        text_len = len(text)

        while cursor < text_len:
            # 1. 寻找下一个块的开始
            match = self.start_pattern.search(text, cursor)
            if not match:
                break  # 没有更多代码块了

            fence = match.group(1)
            lang = match.group(2).strip().lower()

            # 内容开始位置：匹配行的末尾 + 1 (换行符)
            content_start = match.end() + 1

            # 2. 寻找匹配的结束 fence
            # 结束 fence 必须位于行首，且与开始 fence 完全一致，且该行除空白外无其他内容
            # re.escape(fence) 确保如 `+++` 这样的特殊字符也被正确处理
            end_pattern = re.compile(rf"^{re.escape(fence)}\s*$", re.MULTILINE)

            end_match = end_pattern.search(text, content_start)

            if not end_match:
                # 如果找不到闭合，说明这是一个未闭合的块，直接跳过或报错
                # 这里选择跳过，继续从 content_start 开始找（虽然不太可能找到）
                # 或者更安全的做法是：把剩下的全部当做内容（不推荐），或者报错。
                # 这里简单处理：跳过当前头，继续搜
                cursor = match.end()
                continue

            # 提取内容
            content_end = end_match.start()
            # content_end 通常包含前一个换行符，保留它以维持原始内容格式
            # 但为了规整，通常 Markdown 解析器会把紧贴 fence 的换行符去掉
            # 这里我们取 content_start 到 content_end
            # 注意：end_match.start() 是 fence 行的开头。
            # 如果上一行有换行符，它会被包含在 content 里。

            raw_content = text[content_start:content_end]

            # 如果 raw_content 以换行符结尾（通常是的），且我们想模拟标准行为，
            # 可以根据需求 strip。目前逻辑是保留原始数据，但在 act 处理时 strip。
            # 实际上，为了让 replace 精确匹配，我们最好只去掉最后一个换行符（如果存在）。
            if raw_content.endswith("\n"):
                raw_content = raw_content[:-1]

            # --- 处理逻辑 ---
            if lang == "act":
                action_name = raw_content.strip()
                current_statement = {"act": action_name, "contexts": []}
                statements.append(current_statement)

            else:
                # 将非 act 的块作为上下文添加到当前语句
                if current_statement is not None:
                    current_statement["contexts"].append(raw_content)

            # 移动游标到结束块之后
            cursor = end_match.end()

        return statements


class BacktickParser(RegexBlockParser):
    """标准 Markdown 解析器 (```) - 相当于 '绿幕'"""

    def __init__(self):
        super().__init__("`")


class TildeParser(RegexBlockParser):
    """波浪号解析器 (~~~) - 相当于 '蓝幕'"""

    def __init__(self):
        super().__init__("~")


# --- 解析器注册表 ---

_PARSERS = {
    "backtick": BacktickParser,
    "tilde": TildeParser,
    # 可以在这里扩展更多，例如 XML 风格的 parser
}


def get_parser(name: str) -> BaseParser:
    """工厂函数：根据名称获取解析器实例"""
    if name not in _PARSERS:
        raise ValueError(f"未知的解析器: {name}. 可用选项: {list(_PARSERS.keys())}")
    return _PARSERS[name]()


def list_parsers() -> List[str]:
    return list(_PARSERS.keys())


def detect_best_parser(text: str) -> str:
    """
    扫描文本，根据第一个出现的 act 块特征自动决定使用哪种解析器。
    策略：搜索第一个 ` ```act ` 或 ` ~~~act `，返回对应的解析器名称。
    支持变长围栏检测 (如 ` ````act `)。
    """
    # 匹配行首的 fence，后跟 act (忽略大小写)
    # group(1) 是 fence 字符
    pattern = re.compile(r"^([`~]{3,})act\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)

    if match:
        fence_str = match.group(1)
        # 检查 fence 由什么字符组成
        if fence_str.startswith("~"):
            return "tilde"
        # 默认为 backtick
        return "backtick"

    # 如果没找到明确的 act 块，默认返回 backtick
    return "backtick"
