"""Tests for the JARVIS Documents Capability Domain.

REAL tests use genuinely generated PDF/DOCX/XLSX/TXT/CSV/JSON documents and the
real installed parsers. No document capability result is mocked.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from research_engine.document_tools import (  # noqa: E402
    dep_available,
    detect_format,
    document_capability_status,
    ocr_available,
    resolve_document,
)
from research_engine.tool_registry import ToolContext  # noqa: E402

DOCS = ROOT / "tests" / "_document_fixtures"
DOCS.mkdir(exist_ok=True)


def _invoke(cap: str, args: dict, auto_confirm: bool = False) -> dict:
    """Invoke a capability. NETWORK capabilities need an explicit confirmation
    grant, exactly as the existing DefaultPermissionPolicy requires."""
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import DefaultPermissionPolicy

    policy = DefaultPermissionPolicy()
    if auto_confirm:
        policy._confirmations["dt-user:" + cap] = True
    reg = build_capability_registry(policy=policy)
    res = asyncio.run(reg.invoke(cap, args, ToolContext(request_id="dt",
                                                        user_id="dt-user")))
    return {"success": res.success, "error": res.error, "data": (
        json.loads(res.result) if res.success and res.result else None)}


# --------------------------------------------------------------------------- #
# REAL fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def txt_file() -> Path:
    p = DOCS / "sample.txt"
    p.write_text("alpha\nbravo\ncharlie\ndelta\nALPHA again\n", encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def md_file() -> Path:
    p = DOCS / "sample.md"
    p.write_text("# Title\n\nSome **bold** text.\n\n- a\n- b\n", encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def csv_file() -> Path:
    p = DOCS / "sample.csv"
    p.write_text("name,role\nada,engineer\ngrace,admiral\n",
                 encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def json_file() -> Path:
    p = DOCS / "sample.json"
    p.write_text(json.dumps({"a": 1, "b": [1, 2, 3]}, indent=2),
                 encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def bad_json_file() -> Path:
    p = DOCS / "broken.json"
    p.write_text("{not valid json,,}", encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def pdf_file() -> Path:
    if not dep_available("pdf"):
        pytest.skip("pypdf not installed")
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    for body in ("page one alpha bravo", "page two charlie delta"):
        writer.add_blank_page(width=200, height=200)
        page = writer.pages[-1]
        # pypdf cannot author text; embed a minimal content stream instead.
        from pypdf.generic import DecodedStreamObject, NameObject

        font = writer.add_blank_page  # placeholder to keep API happy
    # Build a real PDF with a text-bearing content stream.
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    w = pypdf.PdfWriter()
    for text in ("alpha bravo charlie", "delta echo foxtrot"):
        page = w.add_blank_page(width=300, height=300)
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 12 Tf 20 150 Td ({text}) Tj ET".encode("latin-1"))
        font = DictionaryObject()
        font.update({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)}),
        })
        page[NameObject("/Contents")] = w._add_object(stream)
    out = DOCS / "sample.pdf"
    with out.open("wb") as fh:
        w.write(fh)
    return out


@pytest.fixture(scope="module")
def docx_file() -> Path:
    if not dep_available("docx"):
        pytest.skip("python-docx not installed")
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Report", level=1)
    d.add_paragraph("alpha bravo")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "k"; t.cell(0, 1).text = "v"
    t.cell(1, 0).text = "x"; t.cell(1, 1).text = "y"
    out = DOCS / "sample.docx"
    d.save(str(out))
    return out


@pytest.fixture(scope="module")
def xlsx_file() -> Path:
    if not dep_available("xlsx"):
        pytest.skip("openpyxl not installed")
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["name", "value"])
    ws.append(["alpha", 1])
    ws2 = wb.create_sheet("More")
    ws2.append(["charlie", 2])
    out = DOCS / "sample.xlsx"
    wb.save(str(out))
    return out


# --------------------------------------------------------------------------- #
# Registration + contract
# --------------------------------------------------------------------------- #
EXPECTED_CAPS = (
    "documents.inspect", "documents.extract_text", "documents.search",
    "documents.chunk", "documents.ingest", "documents.convert",
    "documents.generate", "documents.validate", "documents.summarize",
    "documents.compare", "documents.metadata",
)


def test_all_document_capabilities_registered() -> None:
    from research_engine.capability_tools import build_capability_registry

    available = set(build_capability_registry().available())
    missing = set(EXPECTED_CAPS) - available
    assert not missing, f"missing: {missing}"


def test_document_capabilities_have_schemas_and_risk() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    valid = {r.value for r in RiskLevel}
    for cap in EXPECTED_CAPS:
        d = by_name[cap]
        assert d["parameters"].get("type") == "object", cap
        assert d["risk"] in valid, cap
    assert by_name["documents.generate"]["risk"] == RiskLevel.WRITE.value
    assert by_name["documents.ingest"]["risk"] == RiskLevel.WRITE.value
    assert by_name["documents.inspect"]["risk"] == RiskLevel.READ.value


# --------------------------------------------------------------------------- #
# REAL inspect / extract
# --------------------------------------------------------------------------- #
def test_inspect_txt(txt_file: Path) -> None:
    r = _invoke("documents.inspect", {"path": str(txt_file)})
    assert r["success"], r["error"]
    assert r["data"]["format"] == "txt"
    assert r["data"]["size_bytes"] > 0
    assert r["data"]["sha256"]
    assert r["data"]["line_count"] == 6


def test_extract_txt(txt_file: Path) -> None:
    r = _invoke("documents.extract_text", {"path": str(txt_file)})
    assert r["success"], r["error"]
    assert "bravo" in r["data"]["pages"][0]["text"]
    assert r["data"]["truncation_is_explicit"] is True


def test_extract_markdown(md_file: Path) -> None:
    r = _invoke("documents.extract_text", {"path": str(md_file)})
    assert r["success"]
    assert "Title" in r["data"]["pages"][0]["text"]


def test_extract_csv(csv_file: Path) -> None:
    r = _invoke("documents.extract_text", {"path": str(csv_file)})
    assert r["success"]
    assert "ada" in r["data"]["pages"][0]["text"]
    assert "grace" in r["data"]["pages"][0]["text"]


def test_extract_json(json_file: Path) -> None:
    r = _invoke("documents.extract_text", {"path": str(json_file)})
    assert r["success"]
    assert '"a"' in r["data"]["pages"][0]["text"]


def test_inspect_and_extract_real_pdf(pdf_file: Path) -> None:
    """REAL pypdf inspection + extraction of a genuine PDF."""
    r = _invoke("documents.inspect", {"path": str(pdf_file)})
    assert r["success"], r["error"]
    assert r["data"]["format"] == "pdf"
    assert r["data"]["unit_count"] == 2
    assert r["data"]["unit_kind"] == "page"
    e = _invoke("documents.extract_text", {"path": str(pdf_file)})
    assert e["success"], e["error"]
    assert e["data"]["unit_count"] == 2
    text = " ".join(p["text"] for p in e["data"]["pages"])
    assert "alpha" in text and "foxtrot" in text, "real PDF text not extracted"


def test_inspect_and_extract_real_docx(docx_file: Path) -> None:
    """REAL python-docx extraction with paragraph + table structure."""
    r = _invoke("documents.inspect", {"path": str(docx_file)})
    assert r["success"], r["error"]
    assert r["data"]["format"] == "docx"
    e = _invoke("documents.extract_text", {"path": str(docx_file)})
    assert e["success"], e["error"]
    text = e["data"]["pages"][0]["text"]
    assert "alpha bravo" in text
    assert "table 1" in text, "DOCX table structure must be preserved"


def test_inspect_and_extract_real_xlsx(xlsx_file: Path) -> None:
    """REAL openpyxl extraction across multiple sheets."""
    r = _invoke("documents.inspect", {"path": str(xlsx_file)})
    assert r["success"], r["error"]
    assert r["data"]["unit_count"] == 2, "xlsx has two sheets"
    e = _invoke("documents.extract_text", {"path": str(xlsx_file)})
    assert e["success"], e["error"]
    labels = [p["label"] for p in e["data"]["pages"]]
    assert any("Data" in l for l in labels)
    text = " ".join(p["text"] for p in e["data"]["pages"])
    assert "alpha" in text and "charlie" in text


# --------------------------------------------------------------------------- #
# Search / chunk / validate / compare
# --------------------------------------------------------------------------- #
def test_search_inside_document(txt_file: Path) -> None:
    r = _invoke("documents.search", {"path": str(txt_file), "query": "bravo"})
    assert r["success"], r["error"]
    assert r["data"]["match_count"] == 1
    m = r["data"]["matches"][0]
    assert m["file"] == "sample.txt"
    assert m["line"] == 2
    assert "bravo" in m["excerpt"]


def test_search_case_insensitive_by_default(txt_file: Path) -> None:
    r = _invoke("documents.search", {"path": str(txt_file), "query": "alpha"})
    assert r["data"]["match_count"] == 2


def test_search_directory(txt_file: Path, csv_file: Path) -> None:
    r = _invoke("documents.search", {"path": str(DOCS), "query": "charlie"})
    assert r["success"], r["error"]
    assert r["data"]["files_searched"] >= 2
    assert r["data"]["match_count"] >= 1


def test_search_bounded(txt_file: Path) -> None:
    r = _invoke("documents.search", {"path": str(txt_file), "query": "a",
                                     "max_results": 1})
    assert r["data"]["match_count"] == 1
    assert r["data"]["truncated"] is True


def test_chunk_is_deterministic(txt_file: Path) -> None:
    a = _invoke("documents.chunk", {"path": str(txt_file), "chunk_size": 20,
                                    "overlap": 5})
    b = _invoke("documents.chunk", {"path": str(txt_file), "chunk_size": 20,
                                    "overlap": 5})
    assert a["success"] and b["success"]
    assert [c["text"] for c in a["data"]["chunks"]] == \
           [c["text"] for c in b["data"]["chunks"]]
    for c in a["data"]["chunks"]:
        assert c["chunk_id"] and c["file"] == "sample.txt"
        assert c["char_end"] >= c["char_start"]


def test_chunk_preserves_source_metadata(pdf_file: Path) -> None:
    r = _invoke("documents.chunk", {"path": str(pdf_file), "chunk_size": 200})
    assert r["success"], r["error"]
    assert all("unit" in c and "label" in c for c in r["data"]["chunks"])


def test_validate_json_ok(json_file: Path) -> None:
    r = _invoke("documents.validate", {"path": str(json_file)})
    assert r["success"]
    assert r["data"]["valid"] is True
    assert r["data"]["errors"] == []


def test_validate_malformed_json_distinct_from_unavailable(bad_json_file: Path) -> None:
    r = _invoke("documents.validate", {"path": str(bad_json_file)})
    assert r["success"], r["error"]
    assert r["data"]["valid"] is False
    assert r["data"]["errors"][0]["code"] == "INVALID_JSON"


def test_compare_documents_deterministic(txt_file: Path, md_file: Path) -> None:
    r = _invoke("documents.compare", {"left": str(txt_file),
                                      "right": str(md_file)})
    assert r["success"], r["error"]
    assert r["data"]["identical"] is False
    assert r["data"]["lines_added"] >= 1
    r2 = _invoke("documents.compare", {"left": str(txt_file),
                                       "right": str(txt_file)})
    assert r2["data"]["identical"] is True
    assert r2["data"]["lines_added"] == 0


# --------------------------------------------------------------------------- #
# Generate + ArtifactRegistry
# --------------------------------------------------------------------------- #
def test_generate_json_and_register_artifact() -> None:
    out = DOCS / "generated.json"
    r = _invoke("documents.generate", {
        "path": str(out), "format": "json",
        "content": {"generated": True, "n": 1}})
    assert r["success"], r["error"]
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))["generated"] is True
    assert r["data"]["sha256"]
    # ArtifactRegistry integration is reported either way - never faked.
    assert r["data"]["artifact_registry"] in {"registered", "unavailable"}
    if r["data"]["artifact_registry"] == "registered":
        art = r["data"]["artifact"]
        assert art["artifact_id"]
        assert art["metadata"]["producing_capability"] == "documents.generate"
        assert art["checksum"] == r["data"]["sha256"]


def test_generate_csv_real_writer() -> None:
    out = DOCS / "generated.csv"
    r = _invoke("documents.generate", {
        "path": str(out), "format": "csv",
        "content": [["a", "b"], ["1", "2"]]})
    assert r["success"], r["error"]
    assert "a,b" in out.read_text(encoding="utf-8")


def test_generate_rejects_unsupported_format() -> None:
    r = _invoke("documents.generate", {"path": str(DOCS / "x.pdf"),
                                      "format": "pdf"})
    assert r["success"] is False
    assert "unsupported" in r["error"].lower()


# --------------------------------------------------------------------------- #
# Convert
# --------------------------------------------------------------------------- #
def test_convert_csv_to_text(csv_file: Path) -> None:
    out = DOCS / "converted.txt"
    r = _invoke("documents.convert", {"source": str(csv_file),
                                      "target": "txt", "output": str(out)})
    assert r["success"], r["error"]
    assert "ada" in out.read_text(encoding="utf-8")


def test_convert_unsupported_target_is_truthful(txt_file: Path) -> None:
    r = _invoke("documents.convert", {"source": str(txt_file),
                                      "target": "exe", "output": "x.exe"})
    assert r["success"] is False
    assert "unsupported" in r["error"].lower()


def test_archive_container_refused() -> None:
    fake = DOCS / "archive.zip"
    fake.write_bytes(b"PK\x03\x04" + b"0" * 32)  # real zip container
    r = _invoke("documents.extract_text", {"path": str(fake)})
    fake.unlink(missing_ok=True)
    assert r["success"] is False
    assert "untrusted" in r["error"].lower() or "archive" in r["error"].lower()


# --------------------------------------------------------------------------- #
# Ingest + RAG provenance
# --------------------------------------------------------------------------- #
def test_ingest_records_provenance(pdf_file: Path) -> None:
    r = _invoke("documents.ingest", {"path": str(pdf_file), "chunk_size": 300,
                                     "register_artifact": False})
    assert r["success"], r["error"]
    d = r["data"]
    assert d["chunk_count"] > 0
    assert d["extraction_version"]
    assert d["provenance"]["sha256"]
    assert d["provenance"]["filename"] == "sample.pdf"
    # Embedding availability must be reported honestly, never faked.
    assert "embedding_backend" in d
    assert isinstance(d["retrieval_ready"], bool)
    assert d["retrieval_ready"] == d["embeddings_created"]


# --------------------------------------------------------------------------- #
# Summarize - real provider path / truthful unavailability
# --------------------------------------------------------------------------- #
def test_summarize_routes_through_real_provider_or_reports_unavailable(
        txt_file: Path) -> None:
    """REAL: either a real provider summarizes, or PROVIDER_UNAVAILABLE."""
    r = _invoke("documents.summarize", {"path": str(txt_file),
                                        "max_chars": 2000}, auto_confirm=True)
    assert r["success"], r["error"]
    d = r["data"]
    if d.get("status") == "PROVIDER_UNAVAILABLE":
        assert d["reason"], "unavailable must state why"
        # No summary content may be fabricated.
        assert not d.get("summary"), "must not fabricate a summary"
    else:
        assert d["status"] == "COMPLETED"
        assert d["summary"].strip()
        assert d["provider"], "real provider must be recorded"
        assert d["provenance"]["ai_generated"] is True


def test_summarize_never_returns_deterministic_placeholder(txt_file: Path) -> None:
    r = _invoke("documents.summarize", {"path": str(txt_file)}, auto_confirm=True)
    d = r["data"]
    blob = json.dumps(d).lower()
    for banned in ("i understand your document", "self-reliant mode",
                   "local fallback", "local-rule"):
        assert banned not in blob


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["../../", "../../../Windows/System32",
                                r"..\\..\\", "C:/Windows", "/etc/passwd"])
def test_path_traversal_rejected(bad: str) -> None:
    r = _invoke("documents.inspect", {"path": bad})
    assert r["success"] is False


def test_secret_file_refused() -> None:
    r = _invoke("documents.inspect", {"path": ".env"})
    assert r["success"] is False
    assert "secret" in r["error"].lower()


def test_env_contents_never_returned() -> None:
    r = _invoke("documents.inspect", {"path": str(txt_file)})
    blob = json.dumps(r["data"])
    for pattern in ("HF_TOKEN", "NVIDIA_API_KEY", "DATABASE_URL", "Bearer "):
        assert pattern not in blob


def test_no_shell_or_exec_in_document_tools() -> None:
    import inspect as _inspect

    import research_engine.document_tools as dt

    src = _inspect.getsource(dt)
    for banned in ("subprocess", "os.system", "shell=True", "eval(", "exec("):
        assert banned not in src, f"document tools must not use {banned}"


def test_size_limit_enforced() -> None:
    from research_engine import document_tools as dt

    big = DOCS / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    original = dt.MAX_FILE_BYTES
    try:
        dt.MAX_FILE_BYTES = 10
        r = _invoke("documents.inspect", {"path": str(big)})
        assert r["success"] is False
        assert "limit" in r["error"].lower()
    finally:
        dt.MAX_FILE_BYTES = original
        big.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Dependency honesty
# --------------------------------------------------------------------------- #
def test_ocr_reported_unavailable_without_binary() -> None:
    status = document_capability_status()
    assert status["formats"]["ocr"]["available"] == ocr_available()
    if not ocr_available():
        assert status["formats"]["ocr"]["reason"], \
            "unavailable OCR must state why"


def test_archive_reported_unavailable() -> None:
    status = document_capability_status()
    assert status["formats"]["archive"]["available"] is False
    assert status["formats"]["archive"]["reason"]


def test_format_detection_is_real() -> None:
    assert detect_format(Path("a.pdf")) == "pdf"
    assert detect_format(Path("a.docx")) == "docx"
    assert detect_format(Path("a.xlsx")) == "xlsx"
    assert detect_format(Path("a.md")) == "markdown"
