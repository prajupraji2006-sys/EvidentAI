import hashlib
import io
import wave
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image
from pypdf import PdfWriter

from app.services import evidence_upload
from app.services.ai_analysis import EvidenceAnalysis
from app.services.authenticity import DISCLAIMER, assess_file
from app.services.evidence_processing import EvidenceTextError, extract_evidence_text
from app.services.pdf_extraction import PDFProcessingError, extract_pdf_text


def test_sha256_matches_standard_digest(tmp_path):
    source = tmp_path / "sample.txt"
    source.write_bytes(b"synthetic test fixture")
    assert evidence_upload.calculate_sha256(source) == hashlib.sha256(source.read_bytes()).hexdigest()


def test_filename_sanitizer_removes_path_components():
    assert evidence_upload._safe_filename(r"C:\private\sample.txt") == "sample.txt"
    assert evidence_upload._safe_filename("../../report.csv") == "report.csv"


def test_file_extension_and_content_must_match(tmp_path):
    with pytest.raises(evidence_upload.EvidenceUploadError) as error:
        evidence_upload._detect_file_type("malware.exe")
    assert error.value.status_code == 415
    content = tmp_path / "wrong.pdf"
    content.write_bytes(b"plain text pretending to be a PDF")
    with pytest.raises(evidence_upload.EvidenceUploadError):
        evidence_upload._validate_file_content(content, ".pdf")


def test_declared_mime_must_match_extension():
    image_as_pdf = UploadFile(filename="record.pdf", file=io.BytesIO(b""), headers={"content-type": "image/png"})
    with pytest.raises(evidence_upload.EvidenceUploadError) as error:
        evidence_upload._validate_declared_mime(image_as_pdf, ".pdf")
    assert error.value.status_code == 415
    generic = UploadFile(filename="record.pdf", file=io.BytesIO(b""), headers={"content-type": "application/octet-stream"})
    evidence_upload._validate_declared_mime(generic, ".pdf")


def test_upload_size_limit_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence_upload, "MAX_FILE_SIZE", 3)
    upload = UploadFile(filename="short.txt", file=io.BytesIO(b"four"))
    with pytest.raises(evidence_upload.EvidenceUploadError) as error:
        evidence_upload._copy_upload_to_temp(upload, tmp_path / "temporary.txt")
    assert error.value.status_code == 413


def test_exact_duplicate_detection_is_scoped_to_uploader():
    class Query:
        def __init__(self, table):
            self.table = table
            self.filters = []

        def select(self, *_args):
            return self

        def eq(self, key, value):
            self.filters.append((key, value))
            return self

        def in_(self, key, value):
            self.filters.append((key, value))
            return self

        def limit(self, _count):
            return self

        def execute(self):
            if self.table == "incidents":
                assert ("owner_id", "user-1") in self.filters
                return type("Result", (), {"data": [{"id": "owned-incident"}]})()
            if self.table == "evidence":
                assert ("uploaded_by", "user-1") in self.filters
                assert ("incident_id", ["owned-incident"]) in self.filters
                return type("Result", (), {"data": [{"id": "owned-evidence"}]})()
            assert ("evidence_id", ["owned-evidence"]) in self.filters
            return type("Result", (), {"data": [{"evidence_id": "owned-evidence"}]})()

    class Client:
        def table(self, name):
            return Query(name)

    assert evidence_upload._find_exact_duplicate(Client(), "user-1", "same-sha") == "owned-evidence"


def test_incident_ownership_check_requires_matching_owner():
    class Query:
        def __init__(self):
            self.filters = []

        def select(self, *_args):
            return self

        def eq(self, key, value):
            self.filters.append((key, value))
            return self

        def limit(self, _count):
            return self

        def execute(self):
            return type("Result", (), {"data": [{"id": "incident-1"}] if ("owner_id", "user-1") in self.filters else []})()

    class Client:
        def table(self, _name):
            return Query()

    assert evidence_upload._incident_is_owned(Client(), "incident-1", "user-1")
    assert not evidence_upload._incident_is_owned(Client(), "incident-1", "user-2")


def test_text_extraction_and_conservative_authenticity(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Synthetic test fixture only. The meeting is at noon.", encoding="utf-8")
    extracted, method = extract_evidence_text(source, "text")
    result = assess_file(source, "text")
    assert "meeting" in extracted
    assert method == "text_file"
    assert result["classification"] == "INCONCLUSIVE"
    assert result["confidence"] == 0.0
    assert DISCLAIMER in result["limitations"]
    assert "No reliable AI-text detector" in " ".join(result["limitations"])


def test_image_metadata_assessment_reports_dimensions_without_verdict(tmp_path):
    source = tmp_path / "test-fixture.png"
    Image.new("RGB", (12, 8), color="blue").save(source)
    result = assess_file(source, "image")
    assert result["metadata_analysis"]["width"] == 12
    assert result["metadata_analysis"]["height"] == 8
    assert result["classification"] == "INCONCLUSIVE"


def test_wav_assessment_reports_measured_audio_properties(tmp_path):
    source = tmp_path / "test-fixture.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 800)
    result = assess_file(source, "audio")
    assert result["metadata_analysis"]["sample_rate_hz"] == 8000
    assert result["metadata_analysis"]["duration_seconds"] == 0.1
    assert result["classification"] == "INCONCLUSIVE"


def test_pdf_empty_extraction_is_reported_as_insufficient(tmp_path):
    source = tmp_path / "empty-test-fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as target:
        writer.write(target)
    with pytest.raises(PDFProcessingError):
        extract_pdf_text(source)
    with pytest.raises(EvidenceTextError):
        extract_evidence_text(source, "pdf")


def test_analysis_schema_accepts_structured_results():
    result = EvidenceAnalysis.model_validate({
        "summary": "A source-supported summary.", "people": ["Asha"],
        "locations": [], "dates": [], "events": [{"date_or_time": "", "description": "Message received"}],
        "concerns": [],
    })
    assert result.events[0].description == "Message received"
