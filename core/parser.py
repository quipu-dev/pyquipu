import re
from typing import List
from .types import Statement

class MarkdownParser:
    """
    核心解析器：负责将 Markdown 文本转换为操作语句列表。
    基于自动机逻辑解析 act 块和后续的参数块。
    """

    # 匹配 Markdown 代码块： ```lang ... ```
    # group(1): 语言标记 (可选)
    # group(2): 代码内容
    BLOCK_PATTERN = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)

    def parse(self, markdown_text: str) -> List[Statement]:
        """
        解析 Markdown 文本。
        
        Args:
            markdown_text: 输入的 Markdown 字符串

        Returns:
            List[Statement]: 解析出的语句列表
        """
        matches = self.BLOCK_PATTERN.findall(markdown_text)
        
        statements: List[Statement] = []
        current_statement: Statement | None = None

        for lang, content in matches:
            lang_tag = lang.strip().lower() if lang else ""
            # 这里我们不 strip content，因为 write_file 或 replace 可能需要精确的空格/换行
            # 具体的 act 实现中可以根据需要决定是否 strip
            
            if lang_tag == "act":
                # 这是一个操作符 (Verb)
                action_name = content.strip()
                current_statement = {
                    "act": action_name,
                    "contexts": []
                }
                statements.append(current_statement)
            else:
                # 这是一个上下文/参数 (Noun)
                if current_statement is not None:
                    current_statement["contexts"].append(content)
                else:
                    # 处于“空闲”状态遇到的代码块，视为普通文档说明，忽略
                    pass
        
        return statements
