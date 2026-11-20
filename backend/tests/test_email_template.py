"""邮件模板一致性：纯文本正文必须与 HTML 正文逐字一致。"""

import re
from html import unescape

from app.services.email_template import (
    DEFAULT_SUBJECT,
    TEMPLATE_DIR,
    default_subject,
    render_report_email_text,
)
from app.services.html_text import html_to_text

# HTML 正文区块的注释标记（见 email_report.html）
_BODY_START = "<!-- 正文 -->"
_BODY_END = "<!-- 页脚 -->"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

_SIGNATURE = "清华四川能源互联网研究院-电动交通与车网互动研究咨询团队"


def _html_body_text() -> str:
    """取出 HTML 模板正文区块的可见文字。"""
    raw = (TEMPLATE_DIR / "email_report.html").read_text(encoding="utf-8")
    region = raw[raw.index(_BODY_START) : raw.index(_BODY_END)]
    return unescape(_TAG.sub("", _COMMENT.sub("", region)))


def test_plain_text_body_matches_html_body():
    """两边正文只应有排版差异（标签/空白），文字必须完全一致。"""
    assert _WHITESPACE.sub("", render_report_email_text()) == _WHITESPACE.sub("", _html_body_text())


def test_plain_text_keeps_paragraph_breaks():
    """纯文本要保留空行分段，客户端里换行依旧可读。"""
    text = render_report_email_text()
    assert "\n\n" in text
    assert text.startswith("各位专家、行业同仁：")
    assert text.rstrip().endswith(_SIGNATURE)
    assert "微信（18280144300）" in text


def test_default_subject_follows_report_title():
    assert default_subject("2026 年度专家信息收集") == "【报告分享】2026 年度专家信息收集"
    assert default_subject("") == DEFAULT_SUBJECT
    assert default_subject(None) == DEFAULT_SUBJECT
    assert len(default_subject("长" * 512)) == 255


def test_html_to_text_paragraphs():
    assert html_to_text("<p>第一段</p><p>第二段</p>") == "第一段\n\n第二段"


def test_html_to_text_line_break_and_entities():
    html = "<p>A&amp;B&nbsp;（&middot;）<br>下一行</p>"
    assert html_to_text(html) == "A&B （·）\n下一行"


def test_html_to_text_skips_style_script_and_hidden():
    html = (
        "<style>p{color:red}</style>"
        "<script>bad()</script>"
        '<div style="display:none;max-height:0">预览文字</div>'
        "<p>正文</p>"
    )
    assert html_to_text(html) == "正文"


def test_html_to_text_empty_input():
    assert html_to_text("") == ""
    assert html_to_text("   ") == ""
