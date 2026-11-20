"""把 HTML 转成可读的纯文本，用于邮件 text/plain 部分。

只依赖标准库，容忍不规范的邮件 HTML；目标是“可读”，不追求严格的渲染语义。
"""

import re
from html.parser import HTMLParser

_SKIP_TAGS = {"style", "script", "head", "title", "template", "noscript"}
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "blockquote",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "table",
    "tr",
}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_HIDDEN_STYLE_MARKERS = (
    "display:none",
    "mso-hide:all",
    "visibility:hidden",
    "max-height:0",
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # 栈记录当前元素是否处于“跳过”子树（style/script/隐藏元素）中
        self._skip_stack: list[bool] = []

    def _is_skipped(self) -> bool:
        return bool(self._skip_stack and self._skip_stack[-1])

    @staticmethod
    def _is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in _SKIP_TAGS:
            return True
        for name, value in attrs:
            if name.lower() == "hidden":
                return True
            if name.lower() == "style" and value:
                compact = value.replace(" ", "").lower()
                if any(marker in compact for marker in _HIDDEN_STYLE_MARKERS):
                    return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS:
            if not self._is_skipped() and tag in {"br", "hr"}:
                self.parts.append("\n")
            return

        skip = self._is_skipped() or self._is_hidden(tag, attrs)
        self._skip_stack.append(skip)
        if skip:
            return

        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <br/>、<img/> 等自闭合标签
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS:
            return
        if self._skip_stack:
            self._skip_stack.pop()
        if self._is_skipped():
            return

        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")
        elif tag == "li":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._is_skipped():
            return
        text = data.replace("\xa0", " ")
        if text:
            self.parts.append(text)


def html_to_text(html: str) -> str:
    """提取 HTML 的可见文字，保留基本段落结构。"""

    if not html or not html.strip():
        return ""

    parser = _TextExtractor()
    parser.feed(html)
    parser.close()

    text = "".join(parser.parts).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
