"""邮件静态附件目录。

用法：把文件放到 backend/mail_attachments/（或 backend/mail_attachments/<报告id>/），
发送邮件时会自动附加到每封邮件，并出现在邮件正文的附件清单里。

- 文件名以 . 开头的隐藏文件会被忽略
- 超过 mail.max_attachment_mb 的文件会被跳过并记录日志
"""

import logging
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

logger = logging.getLogger(__name__)


def attachment_dir() -> Path:
    configured = Path(settings.mail.attachment_dir)
    return configured if configured.is_absolute() else BACKEND_DIR / configured


def collect_attachments(report_id: str | None = None) -> list[tuple[str, bytes]]:
    """返回 [(文件名, 内容)]；包含公共目录与报告专属子目录。"""

    base = attachment_dir()
    if not base.exists():
        return []

    candidates: list[Path] = []
    for folder in (base, base / report_id if report_id else None):
        if folder and folder.is_dir():
            candidates.extend(sorted(p for p in folder.iterdir() if p.is_file()))

    limit = settings.mail.max_attachment_mb * 1024 * 1024
    result: list[tuple[str, bytes]] = []
    seen: set[str] = set()

    for path in candidates:
        name = path.name
        if name.startswith(".") or name in seen:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > limit:
            logger.warning(
                "静态附件超过上限被跳过：%s（%.1fMB > %sMB）",
                path,
                size / 1024 / 1024,
                settings.mail.max_attachment_mb,
            )
            continue
        try:
            result.append((name, path.read_bytes()))
            seen.add(name)
        except OSError as exc:
            logger.warning("读取静态附件失败：%s（%s）", path, exc)

    if result:
        logger.info("本次邮件附带静态附件：%s", [name for name, _ in result])
    return result
