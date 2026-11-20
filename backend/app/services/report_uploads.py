"""报告级邮件附件：管理端上传，存于 backend/data/report_uploads/<report_id>/。

与服务器上人工维护的 mail_attachments/ 完全隔离：
- 只有这里保存的文件才能通过管理端删除；
- 旧目录继续作为“报告未上传附件”时的全局回退。
"""

import logging
import os
import re
import shutil
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import BACKEND_DIR, settings

logger = logging.getLogger(__name__)

REPORT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_NAME_LENGTH = 200
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UploadError(ValueError):
    """可直接展示给管理端的中文错误。"""


class UploadTooLargeError(UploadError):
    """附件或模板超过大小上限。"""


def upload_dir() -> Path:
    configured = Path(settings.mail.upload_dir)
    return configured if configured.is_absolute() else BACKEND_DIR / configured


def report_upload_dir(report_id: str) -> Path:
    if not REPORT_ID_RE.fullmatch(report_id or ""):
        raise UploadError("报告 ID 无效")
    return upload_dir() / report_id


def sanitize_filename(raw: str) -> str:
    """只接受单个文件名，拒绝路径分隔符、隐藏文件与系统保留名。"""

    if not raw or not raw.strip():
        raise UploadError("附件文件名不能为空")
    if "/" in raw or "\\" in raw:
        raise UploadError("附件文件名不能包含路径分隔符")

    name = raw.strip()
    if not name or name in {".", ".."} or name.startswith("."):
        raise UploadError("附件文件名无效")
    if _CONTROL_RE.search(name):
        raise UploadError("附件文件名包含非法字符")
    if len(name) > _MAX_NAME_LENGTH:
        raise UploadError(f"附件文件名不能超过 {_MAX_NAME_LENGTH} 个字符")
    if name.split(".", 1)[0].upper() in _RESERVED_NAMES:
        raise UploadError("附件文件名不能使用系统保留名称")
    return name


def validate_attachment_extension(name: str) -> None:
    allowed = {ext.lower() for ext in settings.mail.allowed_attachment_extensions}
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        joined = "、".join(sorted(allowed))
        raise UploadError(f"不支持该附件类型，允许的类型：{joined}")


def _visible_files(folder: Path) -> list[Path]:
    """列出非隐藏普通文件，跳过目录与符号链接。"""

    if not folder.is_dir():
        return []
    result: list[Path] = []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        logger.warning("读取报告附件目录失败：%s", folder, exc_info=True)
        return []
    for path in entries:
        if not path.is_file() or path.is_symlink() or path.name.startswith("."):
            continue
        result.append(path)
    return result


def has_uploaded_attachments(report_id: str | None) -> bool:
    """是否存在上传附件；在大小过滤之前判断，超大文件也算“已上传”。"""

    if not report_id or not REPORT_ID_RE.fullmatch(report_id):
        return False
    return bool(_visible_files(report_upload_dir(report_id)))


def collect_uploaded_attachments(report_id: str) -> list[tuple[str, bytes]]:
    folder = report_upload_dir(report_id)
    limit = settings.mail.max_attachment_mb * 1024 * 1024
    result: list[tuple[str, bytes]] = []
    for path in _visible_files(folder):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > limit:
            logger.warning(
                "报告附件超过上限被跳过：report_id=%s name=%s size=%s",
                report_id,
                path.name,
                size,
            )
            continue
        try:
            result.append((path.name, path.read_bytes()))
        except OSError as exc:
            logger.warning("读取报告附件失败：%s（%s）", path.name, exc)
    return result


def list_uploaded_attachments(report_id: str) -> list[dict]:
    folder = report_upload_dir(report_id)
    items: list[dict] = []
    for path in _visible_files(folder):
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, UTC),
            }
        )
    return items


def _safe_target(folder: Path, name: str) -> Path:
    root = folder.resolve()
    raw_target = root / name
    if raw_target.is_symlink():
        raise UploadError("附件路径无效")
    target = raw_target.resolve()
    if target.parent != root or not target.is_relative_to(root):
        raise UploadError("附件路径无效")
    return target


def _write_payloads(report_id: str, prepared: list[tuple[str, bytes]]) -> list[str]:
    """把已校验的 (文件名, 内容) 原子写入报告目录；同名覆盖。"""

    if not prepared:
        return []

    folder = report_upload_dir(report_id)
    folder.mkdir(parents=True, exist_ok=True, mode=0o750)

    staged: list[tuple[Path, Path]] = []
    try:
        # 先把所有内容写进同目录临时文件，再逐个原子替换
        for name, content in prepared:
            target = _safe_target(folder, name)
            temp = folder / f".{name}.{uuid.uuid4().hex}.tmp"
            temp.write_bytes(content)
            staged.append((temp, target))
        for temp, target in staged:
            os.replace(temp, target)
    except OSError as exc:
        logger.exception("保存报告附件失败 report_id=%s", report_id)
        raise UploadError("附件保存失败，请稍后重试") from exc
    finally:
        for temp, _target in staged:
            with suppress(OSError):
                if temp.exists():
                    temp.unlink()

    return [name for name, _content in prepared]


async def save_uploaded_attachments(
    report_id: str, files: list[UploadFile]
) -> list[str]:
    """先整体校验再落盘；同名文件覆盖。"""

    if not files:
        raise UploadError("请选择要上传的附件")
    if len(files) > settings.mail.max_upload_files:
        raise UploadError(f"单次最多上传 {settings.mail.max_upload_files} 个附件")

    per_file_limit = settings.mail.max_attachment_mb * 1024 * 1024
    total_limit = settings.mail.max_total_attachment_mb * 1024 * 1024
    prepared: list[tuple[str, bytes]] = []
    total = 0

    for upload in files:
        name = sanitize_filename(upload.filename or "")
        validate_attachment_extension(name)
        content = await upload.read(per_file_limit + 1)
        if len(content) > per_file_limit:
            raise UploadTooLargeError(
                f"附件 {name} 超过 {settings.mail.max_attachment_mb}MB 上限"
            )
        if not content:
            raise UploadError(f"附件 {name} 为空")
        total += len(content)
        if total > total_limit:
            raise UploadTooLargeError(
                f"本次上传附件总大小超过 {settings.mail.max_total_attachment_mb}MB 上限"
            )
        prepared.append((name, content))

    return _write_payloads(report_id, prepared)


def save_attachment_payloads(
    report_id: str, files: list[tuple[str, bytes]]
) -> list[str]:
    """导入旧全局附件：不套用上传后缀/数量/总大小限制，只做文件名安全校验。"""

    prepared: list[tuple[str, bytes]] = []
    for raw_name, content in files:
        try:
            name = sanitize_filename(raw_name)
        except UploadError as exc:
            logger.warning("导入附件文件名无效，跳过：%r（%s）", raw_name, exc)
            continue
        if not content:
            continue
        prepared.append((name, content))
    return _write_payloads(report_id, prepared)


def delete_uploaded_attachment(report_id: str, filename: str) -> bool:
    name = sanitize_filename(filename)
    folder = report_upload_dir(report_id)
    target = _safe_target(folder, name)
    if not target.exists() or not target.is_file() or target.is_symlink():
        return False
    try:
        target.unlink()
    except OSError as exc:
        logger.exception("删除报告附件失败 report_id=%s name=%s", report_id, name)
        raise UploadError("删除附件失败，请稍后重试") from exc
    return True


def remove_report_upload_dir(report_id: str) -> int:
    """删除报告的全部上传附件目录，返回删除前的文件数。"""

    folder = report_upload_dir(report_id)
    count = len(list_uploaded_attachments(report_id))
    if folder.is_dir():
        try:
            shutil.rmtree(folder)
        except OSError:
            logger.exception("删除报告附件目录失败 report_id=%s", report_id)
    return count
