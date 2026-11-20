"""报告级附件与旧全局附件的选择逻辑。"""

from app.core.config import settings
from app.services.attachments import collect_attachments
from app.services.report_uploads import has_uploaded_attachments


def _prepare_dirs(tmp_path, monkeypatch):
    legacy = tmp_path / "mail_attachments"
    legacy.mkdir()
    (legacy / "global.pdf").write_bytes(b"global")
    report_legacy = legacy / "report-1"
    report_legacy.mkdir()
    (report_legacy / "legacy-report.pdf").write_bytes(b"legacy-report")

    uploads = tmp_path / "report_uploads"
    monkeypatch.setattr(settings.mail, "attachment_dir", str(legacy))
    monkeypatch.setattr(settings.mail, "upload_dir", str(uploads))
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 20)
    return legacy, uploads


def test_uploaded_attachments_replace_legacy(tmp_path, monkeypatch):
    legacy, uploads = _prepare_dirs(tmp_path, monkeypatch)
    report_id = "a" * 32
    report_dir = uploads / report_id
    report_dir.mkdir(parents=True)
    (report_dir / "uploaded.pdf").write_bytes(b"uploaded")
    # 旧逻辑里 32 位报告 id 对应的子目录
    legacy_report = legacy / report_id
    legacy_report.mkdir()
    (legacy_report / "legacy-report.pdf").write_bytes(b"legacy-report")

    assert has_uploaded_attachments(report_id) is True
    assert [name for name, _ in collect_attachments(report_id)] == ["uploaded.pdf"]

    # 删光上传附件后回退旧逻辑（公共目录 + 报告子目录）
    (report_dir / "uploaded.pdf").unlink()
    assert [name for name, _ in collect_attachments(report_id)] == [
        "global.pdf",
        "legacy-report.pdf",
    ]


def test_hidden_only_upload_falls_back_to_legacy(tmp_path, monkeypatch):
    _legacy, uploads = _prepare_dirs(tmp_path, monkeypatch)
    report_id = "b" * 32
    report_dir = uploads / report_id
    report_dir.mkdir(parents=True)
    (report_dir / ".hidden.pdf").write_bytes(b"hidden")

    assert has_uploaded_attachments(report_id) is False
    assert "global.pdf" in [name for name, _ in collect_attachments(report_id)]


def test_oversized_upload_does_not_fall_back(tmp_path, monkeypatch):
    _legacy, uploads = _prepare_dirs(tmp_path, monkeypatch)
    report_id = "c" * 32
    report_dir = uploads / report_id
    report_dir.mkdir(parents=True)
    (report_dir / "big.pdf").write_bytes(b"x")

    monkeypatch.setattr(settings.mail, "max_attachment_mb", 0)
    # “已上传”在大小过滤之前判断：只返回空列表，不回退旧附件
    assert has_uploaded_attachments(report_id) is True
    assert collect_attachments(report_id) == []


def test_none_report_reads_global_root_only(tmp_path, monkeypatch):
    _prepare_dirs(tmp_path, monkeypatch)
    assert [name for name, _ in collect_attachments(None)] == ["global.pdf"]


def test_global_root_shadows_report_subdir(tmp_path, monkeypatch):
    legacy, _uploads = _prepare_dirs(tmp_path, monkeypatch)
    (legacy / "same.pdf").write_bytes(b"root")
    (legacy / "report-1" / "same.pdf").write_bytes(b"sub")

    result = dict(collect_attachments("report-1"))
    assert result["same.pdf"] == b"root"
