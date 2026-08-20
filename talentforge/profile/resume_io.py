"""简历格式转接器：将常见格式统一抽取为纯文本。

按扩展名分派：.txt/.md 直读；.pdf 用 pypdf 纯文本抽取（仅文本层，
扫描件/图片型 PDF 需 OCR，属后续增强，不在本模块）；.docx 用 python-docx。
未知扩展名报 UnsupportedResumeFormatError。

原则（用户裁决）：机器读的简历永远先过用户眼睛才进画像——
本模块只负责"抽取"，不负责"信任"；校对环节在调用方。
"""
from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES: tuple[str, ...] = (".txt", ".md", ".pdf", ".docx")


class UnsupportedResumeFormatError(ValueError):
    """简历格式不受支持。"""


def extract_resume_text(path: str | Path) -> str:
    """从简历文件抽取纯文本，按扩展名分派。

    Args:
        path: 简历文件路径。

    Returns:
        纯文本内容。

    Raises:
        FileNotFoundError: 文件不存在。
        UnsupportedResumeFormatError: 扩展名不受支持。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"简历文件不存在: {p}")
    suffix = p.suffix.lower()
    if suffix in {".txt", ".md"}:
        return p.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return _extract_pdf(p)
    if suffix == ".docx":
        return _extract_docx(p)
    raise UnsupportedResumeFormatError(
        f"不支持的简历格式: {suffix}（支持: {'/'.join(SUPPORTED_SUFFIXES)}）"
    )


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paras)
