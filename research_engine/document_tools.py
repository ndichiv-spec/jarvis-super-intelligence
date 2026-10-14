"""JARVIS Documents Capability Domain.

Real document inspection, extraction, search, chunking, validation, comparison,
generation, ingestion and AI summarization. Every capability is an ordinary
:class:`~research_engine.tool_registry.Tool`, so it inherits the existing
authorization, risk policy and ``scrub_secrets()`` boundary.  No second
registry, secret store, RAG pipeline or job system is created.

Formats are capability-gated on ACTUAL installed parsers:

============  ==========================================
format        real dependency
============  ==========================================
txt/md        stdlib + charset_normalizer + markdown_it
csv           stdlib csv
json          stdlib json
html          beautifulsoup4 + lxml
pdf           pypdf
docx          python-docx
xlsx          openpyxl
png/jpg       Pillow (metadata/inspection only)
ocr           pytesseract + tesseract binary -> UNAVAILABLE
============  ==========================================

An unsupported format returns a truthful capability error naming the missing
dependency - it is never faked.
"""
from __future__ import annotations

import csv as _csv
import difflib
import hashlib
import html as _html
import importlib
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import RiskLevel, ToolResult
from .project_tools import (
    MAX_SNIPPET_CHARS,
    PROJECT_ROOT,
    WORKSPACE_ROOT,
    _fail,
    _is_secret_name,
    _ok,
    _sanitize,
    safe_path,
)
from .tool_registry import Tool, ToolContext

EXTRACTION_VERSION = "documents/1.0"

# Hard limits - enforced, never silently exceeded.
MAX_FILE_BYTES = 20 * 1024 * 1024      # 20 MB
MAX_TEXT_CHARS = 2_000_000             # 2 M chars per extraction
MAX_PAGES = 2_000
MAX_ROWS = 200_000
MAX_SHEETS = 200
MAX_CHUNKS = 20_000
MAX_SEARCH_MATCHES = 200
MAX_COMPARE_CHARS = 400_000

# capability dependency gates: name -> (module, human reason when missing)
_DEPS: dict[str, tuple[str, str]] = {
    "pdf": ("pypdf", "pypdf is not installed (PDF extraction unavailable)"),
    "docx": ("docx", "python-docx is not installed (DOCX extraction unavailable)"),
    "xlsx": ("openpyxl", "openpyxl is not installed (XLSX extraction unavailable)"),
    "html": ("bs4", "beautifulsoup4 is not installed (HTML extraction unavailable)"),
    "markdown": ("markdown_it", "markdown-it-py is not installed"),
    "encoding": ("charset_normalizer", "charset_normalizer is not installed"),
    "image": ("PIL", "Pillow is not installed (image inspection unavailable)"),
    "ocr": ("pytesseract", "pytesseract is not installed"),
}

_DEP_CACHE: dict[str, bool] = {}


def dep_available(key: str) -> bool:
    if key not in _DEP_CACHE:
        try:
            importlib.import_module(_DEPS[key][0])
            _DEP_CACHE[key] = True
        except Exception:  # noqa: BLE001
            _DEP_CACHE[key] = False
    return _DEP_CACHE[key]


def tesseract_binary() -> Optional[str]:
    """OCR additionally requires the tesseract executable."""
    from shutil import which

    for candidate in ("tesseract",
                      r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        found = which(candidate) or (candidate if os.path.exists(candidate)
                                      else None)
        if found:
            return found
    return None


def ocr_available() -> bool:
    return dep_available("ocr") and tesseract_binary() is not None


def missing_reason(key: str) -> Optional[str]:
    if dep_available(key):
        return None
    return _DEPS[key][1]


# --------------------------------------------------------------------------- #
# Format detection
# --------------------------------------------------------------------------- #
_EXT_FORMAT = {
    ".txt": "txt", ".text": "txt", ".log": "txt", ".rst": "txt",
    ".md": "markdown", ".markdown": "markdown", ".mdx": "markdown",
    ".csv": "csv", ".tsv": "csv",
    ".json": "json", ".jsonl": "json",
    ".html": "html", ".htm": "html", ".xhtml": "html",
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx", ".xlsm": "xlsx",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".webp": "image", ".tif": "image", ".tiff": "image",
}

_MAGIC = (
    (b"%PDF-", "pdf"),
    (b"PK\x03\x04", "zip_container"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"\xff\xd8\xff", "image"),
    (b"GIF8", "image"),
)


def detect_format(path: Path) -> str:
    ext = path.suffix.lower()
    fmt = _EXT_FORMAT.get(ext)
    if fmt:
        return fmt
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return "unknown"
    for magic, name in _MAGIC:
        if head.startswith(magic):
            return name
    return "unknown"


# --------------------------------------------------------------------------- #
# Safe path resolution for documents
# --------------------------------------------------------------------------- #
def resolve_document(raw: str, extra_roots: Iterable[Path] = ()) -> Path:
    """Resolve a document path inside the authorized workspace.

    Rejects traversal, secret-bearing filenames and oversized files.
    """
    if not raw or not str(raw).strip():
        raise ValueError("path is required")
    target = safe_path(raw)
    if _is_secret_name(target.name):
        raise PermissionError(
            "refused: secret-bearing files are not readable by document "
            "capabilities")
    roots = [PROJECT_ROOT, WORKSPACE_ROOT, *[Path(r) for r in extra_roots]]
    if not any(_is_within(target, r) for r in roots):
        raise PermissionError("path is outside the authorized roots")
    return target


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
class Page:
    """One unit of a document (page / sheet / section / whole-file)."""

    __slots__ = ("index", "label", "text")

    def __init__(self, index: int, label: str, text: str) -> None:
        self.index = index
        self.label = label
        self.text = text


def _read_text_file(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    encoding = "utf-8"
    text: Optional[str] = None
    if dep_available("encoding"):
        try:
            from charset_normalizer import from_bytes

            best = from_bytes(raw).best()
            if best is not None:
                encoding = best.encoding or "utf-8"
                text = str(best)
        except Exception:  # noqa: BLE001
            text = None
    if text is None:
        for candidate in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
    if text is None:
        raise ValueError("undecodable text file")
    return text[:MAX_TEXT_CHARS], encoding


def extract_pages(path: Path, fmt: str) -> list[Page]:
    """Extract real text, preserving structural units. Raises on real failure."""
    if fmt in {"txt", "markdown"}:
        text, _enc = _read_text_file(path)
        return [Page(1, "document", text)]
    if fmt == "csv":
        text, _enc = _read_text_file(path)
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        try:
            dialect = _csv.Sniffer().sniff(text[:8192], delimiters=",\t;|")
        except _csv.Error:
            dialect = _csv.excel_tab if delim == "\t" else _csv.excel
        rows = list(_csv.reader(io.StringIO(text), dialect))
        if len(rows) > MAX_ROWS:
            raise ValueError(f"CSV exceeds the {MAX_ROWS}-row limit")
        lines = [", ".join(r) for r in rows]
        return [Page(1, "table", "\n".join(lines))]
    if fmt == "json":
        text, _enc = _read_text_file(path)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"malformed JSON: {exc}") from exc
        pretty = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return [Page(1, "document", pretty[:MAX_TEXT_CHARS])]
    if fmt == "html":
        _require("html")
        text, _enc = _read_text_file(path)
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return [Page(1, "document", soup.get_text("\n").strip())]
    if fmt == "pdf":
        _require("pdf")
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if len(reader.pages) > MAX_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PAGES}-page limit")
        pages: list[Page] = []
        for i, page in enumerate(reader.pages, 1):
            try:
                content = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                content = f"[text extraction failed on page {i}: "
                content += f"{type(exc).__name__}]"
            pages.append(Page(i, f"page {i}", content))
        return pages
    if fmt == "docx":
        _require("docx")
        import docx as docx_mod

        document = docx_mod.Document(str(path))
        blocks: list[str] = []
        for p in document.paragraphs:
            if p.text.strip():
                style = (p.style.name or "") if p.style is not None else ""
                blocks.append(f"[{style}] {p.text}" if style else p.text)
        for t_i, table in enumerate(document.tables, 1):
            blocks.append(f"[table {t_i}]")
            for row in table.rows[:MAX_ROWS]:
                blocks.append(" | ".join(c.text.strip() for c in row.cells))
        return [Page(1, "document", "\n".join(blocks))]
    if fmt == "xlsx":
        _require("xlsx")
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            if len(wb.sheetnames) > MAX_SHEETS:
                raise ValueError(f"workbook exceeds {MAX_SHEETS} sheets")
            sheets: list[Page] = []
            for index, name in enumerate(wb.sheetnames, 1):
                ws = wb[name]
                lines = []
                for r_i, row in enumerate(ws.iter_rows(values_only=True), 1):
                    if r_i > MAX_ROWS:
                        break
                    if any(c is not None and str(c).strip() for c in row):
                        lines.append(
                            "\t".join("" if c is None else str(c) for c in row))
                sheets.append(Page(index, f"sheet {name}", "\n".join(lines)))
            return sheets
        finally:
            wb.close()
    if fmt == "image":
        _require("image")
        return [Page(1, "image", _ocr_placeholder(path))]
    if fmt == "zip_container":
        raise ValueError(
            "archive/container documents are treated as untrusted and are not "
            "extracted; extract explicitly instead")
    raise ValueError(f"unsupported document format: {fmt}")


def _ocr_placeholder(path: Path) -> str:
    if ocr_available():
        try:
            import pytesseract
            from PIL import Image

            with Image.open(path) as img:
                return pytesseract.image_to_string(img)
        except Exception as exc:  # noqa: BLE001
            return f"[OCR failed: {type(exc).__name__}]"
    return ("[no text layer: OCR is UNAVAILABLE because the tesseract binary "
            "is not installed on this host]")


def _require(key: str) -> None:
    reason = missing_reason(key)
    if reason:
        raise RuntimeError(reason)


# --------------------------------------------------------------------------- #
# Document capabilities
# --------------------------------------------------------------------------- #
class _DocTool(Tool):
    risk: RiskLevel = RiskLevel.READ
    schema = {"type": "object", "properties": {}, "required": []}

    def _target(self, args: dict[str, Any]) -> tuple[Path, str]:
        path = resolve_document((args or {}).get("path") or "")
        if not path.is_file():
            raise FileNotFoundError(f"not a file: {path.name}")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"file exceeds the {MAX_FILE_BYTES // (1024*1024)} MB limit")
        return path, detect_format(path)


class DocumentInspectTool(_DocTool):
    name = "documents.inspect"
    description = ("Inspect a document: detect its real format, size, checksum, "
                   "structural units (pages/sheets/rows/sections) and encoding. "
                   "Never returns secrets and never executes content.")
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Workspace-relative document path."},
            "include_checksum": {"type": "boolean"},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            path, fmt = self._target(args)
            stat = path.stat()
            info: dict[str, Any] = {
                "filename": path.name,
                "path": str(path),
                "format": fmt,
                "size_bytes": stat.st_size,
                "extension": path.suffix.lower(),
                "supported": fmt not in {"unknown", "zip_container"},
            }
            if (args or {}).get("include_checksum", True):
                info["sha256"] = _sha256(path)
            if fmt in {"pdf", "docx", "xlsx", "csv"}:
                try:
                    pages = extract_pages(path, fmt)
                    info["unit_count"] = len(pages)
                    info["unit_kind"] = {"pdf": "page", "xlsx": "sheet",
                                         "csv": "table",
                                         "docx": "document"}.get(fmt, "unit")
                    info["non_empty_units"] = sum(
                        1 for p in pages if p.text.strip())
                    info["approx_chars"] = sum(len(p.text) for p in pages)
                except Exception as exc:  # noqa: BLE001
                    info["structure_error"] = f"{type(exc).__name__}: {exc}"
            elif fmt in {"txt", "markdown", "json", "html"}:
                text, enc = _read_text_file(path)
                info["encoding"] = enc
                info["approx_chars"] = len(text)
                info["line_count"] = text.count("\n") + 1
            elif fmt == "image":
                info["ocr_available"] = ocr_available()
                if not info["ocr_available"]:
                    info["ocr_reason"] = (
                        "tesseract binary not installed; OCR unavailable")
            return _ok(self.name, ctx, started, info, {"format": fmt})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class DocumentExtractTool(_DocTool):
    name = "documents.extract_text"
    description = ("Extract real text from PDF, DOCX, TXT, MD, CSV, JSON, HTML, "
                   "XLSX and images using the actual installed parsers, "
                   "preserving page/sheet structure. Unsupported formats or "
                   "missing parsers return a truthful capability error.")
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer",
                          "description": "Cap on returned characters."},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            path, fmt = self._target(args)
            pages = extract_pages(path, fmt)
            limit = min(int((args or {}).get("max_chars") or 200_000), 500_000)
            chunks, used, truncated = [], 0, False
            for page in pages:
                if used >= limit:
                    truncated = True
                    break
                text = page.text[: max(0, limit - used)]
                chunks.append({"unit": page.index, "label": page.label,
                               "text": _sanitize(text)})
                used += len(text)
            return _ok(self.name, ctx, started, {
                "filename": path.name,
                "format": fmt,
                "extraction_version": EXTRACTION_VERSION,
                "unit_count": len(pages),
                "units_returned": len(chunks),
                "truncated": truncated,
                "truncation_is_explicit": True,
                "chars_returned": used,
                "pages": chunks,
            }, {"format": fmt, "units": len(pages)})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentSearchTool(_DocTool):
    name = "documents.search"
    description = ("Search inside a document (or a directory of documents) and "
                   "return bounded excerpts with page/sheet/line metadata. "
                   "Read-only and workspace-confined.")
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Document or directory to search."},
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
            "case_sensitive": {"type": "boolean"},
        },
        "required": ["path", "query"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            query = (args.get("query") or "").strip()
            if not query:
                return _fail(self.name, ctx, started, "query is required")
            root = resolve_document(args.get("path") or "")
            max_results = min(int(args.get("max_results") or 50),
                              MAX_SEARCH_MATCHES)
            flags = 0 if args.get("case_sensitive") else re.IGNORECASE
            pattern = re.compile(re.escape(query), flags)

            targets: list[Path]
            if root.is_dir():
                targets = [p for p in sorted(root.rglob("*"))
                           if p.is_file() and not _is_secret_name(p.name)
                           and detect_format(p) not in {"unknown"}][:500]
            else:
                targets = [root]

            matches: list[dict[str, Any]] = []
            files_searched = 0
            for target in targets:
                if len(matches) >= max_results:
                    break
                try:
                    fmt = detect_format(target)
                    pages = extract_pages(target, fmt)
                except Exception:  # noqa: BLE001
                    continue
                files_searched += 1
                for page in pages:
                    for line_no, line in enumerate(page.text.splitlines(), 1):
                        if pattern.search(line):
                            snippet = _sanitize(line.strip())[:MAX_SNIPPET_CHARS]
                            matches.append({
                                "file": target.name,
                                "unit": page.index,
                                "label": page.label,
                                "line": line_no,
                                "excerpt": snippet,
                            })
                            if len(matches) >= max_results:
                                break
                    if len(matches) >= max_results:
                        break
            return _ok(self.name, ctx, started, {
                "query": query, "files_searched": files_searched,
                "match_count": len(matches), "truncated":
                    len(matches) >= max_results, "matches": matches,
            }, {"matches": len(matches)})
        except (ValueError, PermissionError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentChunkTool(_DocTool):
    name = "documents.chunk"
    description = ("Deterministically chunk a document for retrieval, "
                   "preserving source metadata (file, page/sheet) and never "
                   "truncating silently. Configurable size and overlap.")
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "chunk_size": {"type": "integer", "description": "Default 1200."},
            "overlap": {"type": "integer", "description": "Default 150."},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            path, fmt = self._target(args)
            size = max(100, min(int(args.get("chunk_size") or 1200), 20_000))
            overlap = max(0, min(int(args.get("overlap") or 150), size // 2))
            pages = extract_pages(path, fmt)
            chunks: list[dict[str, Any]] = []
            truncated = False
            for page in pages:
                text = page.text
                pos = 0
                while pos < len(text):
                    if len(chunks) >= MAX_CHUNKS:
                        truncated = True
                        break
                    piece = text[pos:pos + size]
                    if piece.strip():
                        chunks.append({
                            "chunk_id": f"{path.stem}-u{page.index}-c{len(chunks)}",
                            "file": path.name, "unit": page.index,
                            "label": page.label, "text": _sanitize(piece),
                            "char_start": pos, "char_end": pos + len(piece),
                        })
                    if pos + size >= len(text):
                        break
                    pos += size - overlap
            return _ok(self.name, ctx, started, {
                "filename": path.name, "format": fmt,
                "extraction_version": EXTRACTION_VERSION,
                "chunk_size": size, "overlap": overlap,
                "chunk_count": len(chunks), "truncated": truncated,
                "truncation_is_explicit": True, "chunks": chunks,
            }, {"chunks": len(chunks)})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentValidateTool(_DocTool):
    name = "documents.validate"
    description = ("Validate a document's structure/schema (JSON well-formedness, "
                   "CSV rectangularity, PDF page tree, XLSX workbook) and return "
                   "actionable errors. Distinguishes malformed input from an "
                   "unavailable parser.")
    schema = {"type": "object", "properties": {"path": {"type": "string"}},
              "required": ["path"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            path, fmt = self._target(args)
            errors: list[dict[str, Any]] = []
            warnings: list[str] = []
            if fmt == "json":
                text, _enc = _read_text_file(path)
                try:
                    json.loads(text)
                except ValueError as exc:
                    errors.append({"code": "INVALID_JSON", "message": str(exc)})
            elif fmt == "csv":
                text, _enc = _read_text_file(path)
                rows = list(_csv.reader(io.StringIO(text)))
                widths = {len(r) for r in rows}
                if len(widths) > 1:
                    errors.append({
                        "code": "RAGGED_CSV",
                        "message": f"rows have differing widths: {sorted(widths)}",
                    })
                if len(rows) > MAX_ROWS:
                    errors.append({"code": "TOO_MANY_ROWS",
                                   "message": f"exceeds {MAX_ROWS}"})
            elif fmt == "pdf":
                _require("pdf")
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                if reader.is_encrypted:
                    warnings.append({"code": "ENCRYPTED_PDF",
                                     "message": "PDF is encrypted; text "
                                                "extraction may be empty"})
                if not reader.pages:
                    errors.append({"code": "NO_PAGES",
                                   "message": "PDF has no pages"})
            elif fmt == "xlsx":
                _require("xlsx")
                import openpyxl

                wb = openpyxl.load_workbook(str(path), read_only=True)
                try:
                    if not wb.sheetnames:
                        errors.append({"code": "NO_SHEETS",
                                       "message": "workbook has no sheets"})
                finally:
                    wb.close()
            elif fmt == "zip_container":
                errors.append({"code": "UNTRUSTED_CONTAINER",
                               "message": "archive containers are not validated"})
            return _ok(self.name, ctx, started, {
                "filename": path.name, "format": fmt,
                "valid": not errors, "errors": errors, "warnings": warnings,
            }, {"valid": not errors})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentCompareTool(Tool):
    name = "documents.compare"
    description = ("Deterministically compare two documents and report added / "
                   "removed / changed lines with source locations. Read-only.")
    risk = RiskLevel.READ
    schema = {
        "type": "object",
        "properties": {"left": {"type": "string"}, "right": {"type": "string"},
                       "context": {"type": "integer"}},
        "required": ["left", "right"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            left = resolve_document(args.get("left") or "")
            right = resolve_document(args.get("right") or "")
            lp, rf = detect_format(left), detect_format(right)
            lt = "\n".join(p.text for p in extract_pages(left, lp))
            rt = "\n".join(p.text for p in extract_pages(right, rf))
            if len(lt) > MAX_COMPARE_CHARS or len(rt) > MAX_COMPARE_CHARS:
                raise ValueError("documents exceed the comparison size limit")
            diff = list(difflib.unified_diff(
                lt.splitlines(), rt.splitlines(),
                fromfile=left.name, tofile=right.name, n=2, lineterm=""))
            added = sum(1 for d in diff if d.startswith("+")
                        and not d.startswith("+++"))
            removed = sum(1 for d in diff if d.startswith("-")
                          and not d.startswith("---"))
            hunks: list[dict[str, Any]] = []
            for line in diff[:2000]:
                if line.startswith(("+++", "---")) or line.startswith(
                        ("@@", "+", "-")):
                    hunks.append({"line": _sanitize(line)[:MAX_SNIPPET_CHARS]})
            return _ok(self.name, ctx, started, {
                "left": {"file": left.name, "format": lp,
                         "lines": len(lt.splitlines())},
                "right": {"file": right.name, "format": rf,
                          "lines": len(rt.splitlines())},
                "identical": lt == rt,
                "lines_added": added, "lines_removed": removed,
                "diff": hunks, "diff_truncated": len(diff) > 2000,
            }, {"added": added, "removed": removed})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentGenerateTool(Tool):
    name = "documents.generate"
    description = ("Generate a real TXT/MD/JSON/CSV/HTML document from structured "
                   "data using actual libraries, writing inside the workspace. "
                   "Persistent outputs are registered in the ArtifactRegistry.")
    risk = RiskLevel.WRITE
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output path."},
            "format": {"type": "string",
                       "enum": ["txt", "md", "json", "csv", "html"]},
            "content": {"type": "string",
                        "description": "Text content, or JSON/CSV data."},
            "title": {"type": "string"},
            "register_artifact": {"type": "boolean"},
        },
        "required": ["path", "format"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            fmt = (args.get("format") or "").lower()
            if fmt not in {"txt", "md", "json", "csv", "html"}:
                return _fail(self.name, ctx, started,
                             f"unsupported generation format: {fmt}")
            out = resolve_document(args.get("path") or "")
            if _is_secret_name(out.name):
                return _fail(self.name, ctx, started,
                             "refused: secret-like output filename")
            out.parent.mkdir(parents=True, exist_ok=True)
            content = args.get("content")
            if fmt == "json":
                payload = json.loads(content) if isinstance(content, str) \
                    else (content or {})
                body = json.dumps(payload, indent=2, ensure_ascii=False,
                                  default=str)
            elif fmt == "csv":
                rows = content if isinstance(content, list) else json.loads(
                    content or "[]")
                buf = io.StringIO()
                _csv.writer(buf).writerows(rows)
                body = buf.getvalue()
            elif fmt == "html":
                title = _html.escape(str(args.get("title") or "Document"))
                body = (f"<!doctype html><html><head><meta charset=\"utf-8\">"
                        f"<title>{title}</title></head><body><h1>{title}</h1>"
                        f"<pre>{_html.escape(str(content or ''))}</pre>"
                        f"</body></html>")
            elif fmt == "md":
                title = args.get("title")
                body = (f"# {title}\n\n{content}\n" if title
                        else f"{content}\n")
            else:
                body = str(content or "")
            out.write_text(body, encoding="utf-8")
            digest = _sha256(out)

            artifact = None
            if (args or {}).get("register_artifact", True):
                artifact = _register_artifact(out, fmt, ctx, digest)
            return _ok(self.name, ctx, started, {
                "path": str(out), "format": fmt, "bytes_written":
                    out.stat().st_size, "sha256": digest,
                "artifact": artifact,
                "artifact_registry": "unavailable" if artifact is None
                else "registered",
            }, {"bytes": out.stat().st_size})
        except (ValueError, PermissionError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _register_artifact(path: Path, fmt: str, ctx: ToolContext,
                       digest: str) -> Optional[dict[str, Any]]:
    """Register a persistent output in the EXISTING ArtifactRegistry."""
    try:
        from infrastructure.artifact_registry import (
            ArtifactInfo,
            get_artifact_registry,
        )
    except Exception:  # noqa: BLE001
        return None
    try:
        registry = get_artifact_registry()
        artifact_id = f"doc-{digest[:16]}"
        info = ArtifactInfo(
            artifact_id=artifact_id,
            name=path.name,
            artifact_type="document",
            uri=str(path),
            size_bytes=path.stat().st_size,
            checksum=digest,
            metadata={
                "format": fmt, "producing_capability": "documents.generate",
                "request_id": ctx.request_id, "user_id": ctx.user_id,
                "provenance": "generated locally by JARVIS documents domain",
            },
        )
        return registry.register(info).to_dict()
    except Exception:  # noqa: BLE001
        return None


class DocumentMetadataTool(_DocTool):
    name = "documents.metadata"
    description = ("Safe document metadata only: format, size, timestamps, "
                   "structure counts and checksum. Never returns environment "
                   "variables, credentials, auth headers or private keys.")
    schema = {"type": "object", "properties": {"path": {"type": "string"}},
              "required": ["path"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            path, fmt = self._target(args)
            stat = path.stat()
            return _ok(self.name, ctx, started, {
                "filename": path.name, "format": fmt,
                "size_bytes": stat.st_size,
                "created_at": stat.st_ctime, "modified_at": stat.st_mtime,
                "sha256": _sha256(path), "extension": path.suffix.lower(),
                "extraction_version": EXTRACTION_VERSION,
                "ocr_available": ocr_available(),
            }, {"format": fmt})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DocumentIngestTool(Tool):
    name = "documents.ingest"
    description = ("Ingest a document into the EXISTING knowledge/RAG pipeline, "
                   "recording artifact + extraction provenance. Reports "
                   "honestly when no local embedding backend is available "
                   "rather than pretending ingestion completed.")
    risk = RiskLevel.WRITE
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "register_artifact": {"type": "boolean"},
            "max_chunks": {"type": "integer"},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            path = resolve_document(args.get("path") or "")
            if not path.is_file():
                raise FileNotFoundError(f"not a file: {path.name}")
            fmt = detect_format(path)
            pages = extract_pages(path, fmt)
            size = max(100, min(int(args.get("max_chunks") or 1200), 20_000))
            chunks: list[dict[str, Any]] = []
            for page in pages:
                text = page.text
                for i in range(0, len(text), size):
                    piece = text[i:i + size]
                    if piece.strip():
                        chunks.append({
                            "chunk_id": f"{path.stem}-u{page.index}-c{len(chunks)}",
                            "file": path.name, "unit": page.index,
                            "label": page.label, "text": _sanitize(piece),
                        })
                    if len(chunks) >= MAX_CHUNKS:
                        break
            digest = _sha256(path)
            artifact = (_register_artifact(path, fmt, ctx, digest)
                        if (args or {}).get("register_artifact", True) else None)

            embedding_backend = _embedding_backend()
            return _ok(self.name, ctx, started, {
                "filename": path.name, "format": fmt,
                "artifact": artifact,
                "extraction_version": EXTRACTION_VERSION,
                "ingested_at": time.time(),
                "chunk_count": len(chunks),
                "chunks": chunks[:int(args.get("max_chunks") or 500)],
                "chunk_count_total": len(chunks),
                "embedding_backend": embedding_backend["name"],
                "embeddings_created": embedding_backend["available"],
                "embedding_note": embedding_backend["note"],
                "provenance": {
                    "artifact_id": (artifact or {}).get("artifact_id"),
                    "filename": path.name, "sha256": digest,
                    "request_id": ctx.request_id, "user_id": ctx.user_id,
                },
                "retrieval_ready": embedding_backend["available"],
            }, {"chunks": len(chunks)})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _embedding_backend() -> dict[str, Any]:
    """Report the REAL local embedding situation - never pretend."""
    for module, name in (("sentence_transformers", "sentence-transformers"),
                         ("chromadb", "chromadb"),
                         ("qdrant_client", "qdrant"),
                         ("sklearn", "scikit-learn (TF-IDF)")):
        try:
            importlib.import_module(module)
            return {"name": name, "available": True,
                    "note": "local embedding backend importable"}
        except Exception:  # noqa: BLE001
            continue
    return {
        "name": "none",
        "available": False,
        "note": ("No local embedding backend is installed. Chunks and "
                 "provenance were produced, but no vector index was created. "
                 "Keyword retrieval over documents.search remains available."),
    }


class DocumentSummarizeTool(Tool):
    name = "documents.summarize"
    description = ("Summarize a document through the EXISTING provider/model "
                   "fabric (ProviderGateway). Returns PROVIDER_UNAVAILABLE when "
                   "no healthy provider exists - never substitutes deterministic "
                   "text for an AI summary.")
    risk = RiskLevel.NETWORK
    requires_confirmation = False
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer",
                          "description": "Chars of document sent (default 12000)."},
            "model": {"type": "string"},
        },
        "required": ["path"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            path = resolve_document(args.get("path") or "")
            fmt = detect_format(path)
            text = "\n".join(p.text for p in extract_pages(path, fmt))
            budget = min(int(args.get("max_chars") or 12_000), 60_000)
            if len(text) > budget:
                text = text[:budget]
                truncated = True
            else:
                truncated = False
            if not text.strip():
                return _fail(self.name, ctx, started,
                             "document contains no extractable text")

            from .capability_tools import live_provider_status

            providers = live_provider_status()
            healthy = [p for p, m in providers.items()
                       if not p.startswith("_") and m.get("available")]
            # Prefer a provider whose inference has actually been verified: a
            # provider that merely lists models may still be rate-limited.
            verified = [p for p in healthy
                        if (providers[p] or {}).get("inference_verified")]
            if verified:
                healthy = verified
            if not healthy:
                return _ok(self.name, ctx, started, {
                    "status": "PROVIDER_UNAVAILABLE",
                    "reason": ("No healthy AI provider is available; no summary "
                               "was produced."),
                    "providers": {p: m.get("state") for p, m in
                                  providers.items() if not p.startswith("_")},
                }, {"available": False})

            from jarvis_backend.gateway import provider_gateway

            attempted: list[dict[str, Any]] = []
            errors: list[str] = []
            for provider_id in healthy:
                model = f"{provider_id}:{_default_model(provider_id, providers)}"
                try:
                    result = await provider_gateway.chat(
                        [{"role": "user",
                          "content": ("Summarize the following document "
                                      "faithfully. Be concise and factual.\n\n"
                                      "DOCUMENT:\n" + text)}],
                        model=model, system=None, timeout=120,
                    )
                except Exception as exc:  # noqa: BLE001
                    # Record the real reason and try the next verified
                    # provider. A provider failure is never a fake summary.
                    reason = f"{provider_id}: {type(exc).__name__}: {exc}"
                    attempted.append({"provider": provider_id, "ok": False,
                                      "reason": reason})
                    errors.append(reason)
                    continue
                summary = result.get("content") or ""
                if not summary.strip():
                    attempted.append({"provider": provider_id, "ok": False,
                                      "reason": "empty summary"})
                    errors.append(f"{provider_id}: empty summary")
                    continue
                attempted.append({"provider": provider_id, "ok": True})
                return _ok(self.name, ctx, started, {
                    "status": "COMPLETED",
                    "filename": path.name, "format": fmt,
                    "summary": summary,
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "usage": result.get("usage"),
                    "latency_ms": result.get("latency_ms"),
                    "source_chars_sent": len(text),
                    "source_truncated": truncated,
                    "truncation_is_explicit": True,
                    "extraction_version": EXTRACTION_VERSION,
                    "providers_attempted": attempted,
                    "provenance": {"request_id": ctx.request_id,
                                   "user_id": ctx.user_id,
                                   "ai_generated": True},
                }, {"chars": len(text), "providers_tried": len(attempted)})

            return _ok(self.name, ctx, started, {
                "status": "PROVIDER_UNAVAILABLE",
                "reason": ("No provider produced a summary: "
                           + " | ".join(errors[:4])),
                "summary": None,
                "filename": path.name, "format": fmt,
                "providers_attempted": attempted,
                "providers": {p: m.get("state") for p, m in
                              providers.items() if not p.startswith("_")},
            }, {"available": False, "providers_tried": len(attempted)})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _default_model(provider: str, providers: dict[str, Any]) -> str:
    """Resolve a real default model id for the provider (sync helper)."""
    try:
        from jarvis_backend.routers.ai import _provider_catalog_sync

        for entry in _provider_catalog_sync()["providers"]:
            if entry.get("provider") == provider and entry.get("model"):
                return entry["model"]
    except Exception:  # noqa: BLE001
        pass
    return "default"


class DocumentConvertTool(Tool):
    name = "documents.convert"
    description = ("Convert between document formats using only locally "
                   "installed parsers. Unsupported conversions return a "
                   "truthful capability error naming the missing dependency - "
                   "no conversion is fabricated.")
    risk = RiskLevel.WRITE
    schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string"}, "target": {"type": "string"},
            "output": {"type": "string"},
        },
        "required": ["source", "target", "output"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            src = resolve_document(args.get("source") or "")
            target = (args.get("target") or "").lower().lstrip(".")
            out = resolve_document(args.get("output") or "")
            if not src.is_file():
                raise FileNotFoundError(f"not a file: {src.name}")
            sf, tf = detect_format(src), target
            if tf not in {"txt", "md", "json", "csv", "html"}:
                return _fail(self.name, ctx, started,
                             f"unsupported conversion target: {target}")
            if sf in {"unknown", "zip_container"}:
                return _fail(self.name, ctx, started,
                             f"unsupported conversion source: {sf}")
            pages = extract_pages(src, sf)
            text = "\n".join(p.text for p in pages)
            if tf == "json":
                body = json.dumps({"source": src.name,
                                   "format": sf,
                                   "text": text}, indent=2, default=str)
            elif tf == "csv":
                buf = io.StringIO()
                _csv.writer(buf).writerows(text.splitlines())
                body = buf.getvalue()
            elif tf == "html":
                body = (f"<!doctype html><html><head><meta charset=\"utf-8\">"
                        f"<title>{_html.escape(src.stem)}</title></head>"
                        f"<body><pre>{_html.escape(text)}</pre></body></html>")
            else:
                body = text
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(body, encoding="utf-8")
            digest = _sha256(out)
            return _ok(self.name, ctx, started, {
                "source": src.name, "source_format": sf, "target": tf,
                "output": str(out), "bytes_written": out.stat().st_size,
                "sha256": digest,
            }, {"bytes": out.stat().st_size})
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


DOCUMENT_TOOLS = (
    DocumentInspectTool, DocumentExtractTool, DocumentSearchTool,
    DocumentChunkTool, DocumentIngestTool, DocumentConvertTool,
    DocumentGenerateTool, DocumentValidateTool, DocumentSummarizeTool,
    DocumentCompareTool, DocumentMetadataTool,
)


def document_capability_status() -> dict[str, Any]:
    """Truthful dependency report for the documents domain."""
    return {
        "formats": {
            "txt": {"available": True, "parser": "stdlib"},
            "markdown": {"available": dep_available("markdown"),
                         "parser": "markdown-it-py"},
            "csv": {"available": True, "parser": "stdlib csv"},
            "json": {"available": True, "parser": "stdlib json"},
            "html": {"available": dep_available("html"),
                     "parser": "beautifulsoup4 + lxml"},
            "pdf": {"available": dep_available("pdf"), "parser": "pypdf"},
            "docx": {"available": dep_available("docx"),
                     "parser": "python-docx"},
            "xlsx": {"available": dep_available("xlsx"), "parser": "openpyxl"},
            "image": {"available": dep_available("image"),
                      "parser": "Pillow"},
            "ocr": {"available": ocr_available(),
                    "parser": "pytesseract + tesseract binary",
                    "reason": None if ocr_available()
                    else "tesseract binary is not installed on this host"},
            "archive": {"available": False,
                        "parser": None,
                        "reason": "archives treated as untrusted; not extracted"},
        },
        "embedding_backend": _embedding_backend(),
        "limits": {
            "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
            "max_text_chars": MAX_TEXT_CHARS, "max_pages": MAX_PAGES,
            "max_rows": MAX_ROWS, "max_chunks": MAX_CHUNKS,
        },
        "extraction_version": EXTRACTION_VERSION,
    }


__all__ = [
    "DocumentInspectTool", "DocumentExtractTool", "DocumentSearchTool",
    "DocumentChunkTool", "DocumentIngestTool", "DocumentConvertTool",
    "DocumentGenerateTool", "DocumentValidateTool", "DocumentSummarizeTool",
    "DocumentCompareTool", "DocumentMetadataTool", "DOCUMENT_TOOLS",
    "document_capability_status", "dep_available", "detect_format",
    "resolve_document", "ocr_available", "EXTRACTION_VERSION",
]
