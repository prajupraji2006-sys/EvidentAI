import hashlib
import hmac
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# Load backend/.env before reading application environment settings.
from app import config as _config  # noqa: F401
from app.services.ai_analysis import (
    EvidenceAnalysis,
    GeminiServiceError,
    InvalidGeminiResponseError,
    analyze_evidence,
)
from app.services.evidence_upload import (
    EvidenceUploadError,
    EvidenceUploadResult,
    SUPPORTED_EXTENSIONS,
    UPLOAD_DIR,
    calculate_sha256,
    find_stored_file,
    list_evidence_records,
    read_evidence_metadata,
    save_evidence_file,
    save_analysis_result,
)
from app.services.evidence_processing import (
    MAX_ANALYSIS_TEXT_CHARS,
    EvidenceTextError,
    extract_evidence_text,
)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
allowed_origins = list(
    {frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"}
)

app = FastAPI(title="EvidentAI API", version="0.1.0", description="Digital evidence intelligence API starter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "EvidentAI API is running"}


class AnalyzeRequest(BaseModel):
    evidence_text: str = Field(
        min_length=1,
        max_length=MAX_ANALYSIS_TEXT_CHARS,
        description=f"Plain-text evidence to analyze (maximum {MAX_ANALYSIS_TEXT_CHARS:,} characters).",
        json_schema_extra={
            "examples": [
                "On 2025-04-12, Jordan Lee met Casey Morgan at the North Station office."
            ]
        },
    )

    @field_validator("evidence_text")
    @classmethod
    def evidence_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("evidence_text must contain non-whitespace text")
        return value


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "evidentai-api"}


@app.post(
    "/api/analyze",
    response_model=EvidenceAnalysis,
    summary="Analyze evidence text with Gemini",
    description=(
        "Submit plain-text evidence for structured analysis. The endpoint does not store "
        "the submitted text. Use the example request in Swagger's request body editor."
    ),
)
def analyze(request: AnalyzeRequest) -> EvidenceAnalysis:
    try:
        return analyze_evidence(request.evidence_text)
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini is not configured. Set GEMINI_API_KEY in backend/.env "
                "and restart the backend."
            ),
        ) from None
    except InvalidGeminiResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except GeminiServiceError:
        raise HTTPException(
            status_code=502,
            detail="Gemini analysis is temporarily unavailable. Please try again.",
        ) from None


@app.get("/api/dashboard")
async def dashboard():
    records = list_evidence_records()
    analyzed_records = [record for record in records if record.get("analysis")]
    events_count = sum(
        len(record["analysis"].get("events", []))
        for record in analyzed_records
        if isinstance(record.get("analysis"), dict)
    )
    return {
        "active_investigations": 0,
        "evidence_items": len(records),
        "events_identified": events_count,
        "integrity_verified_percent": None,
        "processing_items": 0,
        "recent_evidence": records[:5],
    }


@app.get("/api/cases")
async def cases():
    # Cases will be supplied by the future database integration.
    return {"cases": []}


@app.get("/api/evidence")
async def evidence_list():
    return {"items": list_evidence_records()}


@app.post(
    "/api/evidence/upload",
    response_model=EvidenceUploadResult,
    summary="Upload and verify an evidence file",
    description=(
        "Accepts one PDF, image, text/CSV, or audio file up to 200 MB. "
        "The file is temporarily stored under backend/uploads and hashed with SHA-256. "
        "Files are not persisted to a database."
    ),
)
def upload_evidence(file: UploadFile = File(...)) -> EvidenceUploadResult:
    try:
        return save_evidence_file(file)
    except EvidenceUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None


class PDFAnalysisResponse(BaseModel):
    evidence_id: str
    original_filename: str
    extracted_text_preview: str
    extraction_status: str
    extraction_method: str
    analysis: EvidenceAnalysis


@app.post(
    "/api/evidence/{evidence_id}/analyze",
    response_model=PDFAnalysisResponse,
    summary="Extract and analyze uploaded evidence",
    description=(
        "First upload a supported file with POST /api/evidence/upload and copy its evidence_id. "
        "Submit that UUID here to extract text, run OCR, or transcribe audio as appropriate, "
        "then analyze the extracted content with Gemini. Only a short preview is returned."
    ),
)
def analyze_uploaded_evidence(evidence_id: UUID) -> PDFAnalysisResponse:
    try:
        evidence_path = find_stored_file(evidence_id)
        if evidence_path is None:
            raise HTTPException(status_code=404, detail="Evidence file was not found.")
        metadata = read_evidence_metadata(evidence_id)
        file_type = metadata.get(
            "file_type", SUPPORTED_EXTENSIONS.get(evidence_path.suffix.lower())
        )
        extracted_text, extraction_method = extract_evidence_text(evidence_path, file_type or "")
        if len(extracted_text) > MAX_ANALYSIS_TEXT_CHARS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Extracted content exceeds the {MAX_ANALYSIS_TEXT_CHARS:,} character "
                    "analysis limit. Use a shorter file or split the evidence."
                ),
            )
        analysis = analyze_evidence(extracted_text)
        preview = extracted_text[:500]
        preview += "… [preview only]" if len(extracted_text) > 500 else " [preview only]"
        save_analysis_result(evidence_id, analysis.model_dump(mode="json"), preview)
    except EvidenceTextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except HTTPException:
        raise
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini is not configured. Set GEMINI_API_KEY in backend/.env "
                "and restart the backend."
            ),
        ) from None
    except InvalidGeminiResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except GeminiServiceError:
        raise HTTPException(
            status_code=502,
            detail="Gemini analysis is temporarily unavailable. Please try again.",
        ) from None
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="Analysis completed, but its result could not be saved. Please retry.",
        ) from None
    return PDFAnalysisResponse(
        evidence_id=str(evidence_id),
        original_filename=metadata.get("original_filename", evidence_path.name),
        extracted_text_preview=preview,
        extraction_status="completed",
        extraction_method=extraction_method,
        analysis=analysis,
    )


@app.get("/api/timeline")
async def timeline():
    events = []
    for record in list_evidence_records():
        analysis = record.get("analysis") or {}
        for event in analysis.get("events", []):
            events.append({
                **event,
                "evidence_id": record["evidence_id"],
                "original_filename": record["original_filename"],
            })

    def event_sort_key(event):
        date_or_time = event.get("date_or_time", "")
        try:
            parsed = datetime.fromisoformat(date_or_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (0, parsed.timestamp())
        except (TypeError, ValueError):
            return (1, str(date_or_time).casefold())

    events.sort(key=event_sort_key)
    return {"events": events}


@app.get("/api/graph")
async def graph():
    nodes_by_id = {}
    edges_by_id = {}

    def add_relationship_node(kind: str, label: str, evidence_id: str):
        normalized = label.strip()
        if not normalized:
            return
        node_id = f"{kind}:{normalized.casefold()}"
        nodes_by_id[node_id] = {"id": node_id, "label": normalized, "type": kind}
        evidence_node_id = f"evidence:{evidence_id}"
        edge_id = f"{node_id}->{evidence_node_id}"
        edges_by_id[edge_id] = {
            "id": edge_id,
            "source": node_id,
            "target": evidence_node_id,
            "label": "mentioned in",
        }

    for record in list_evidence_records():
        evidence_id = record["evidence_id"]
        evidence_node_id = f"evidence:{evidence_id}"
        nodes_by_id[evidence_node_id] = {
            "id": evidence_node_id,
            "label": record["original_filename"],
            "type": "evidence",
        }
        analysis = record.get("analysis") or {}
        for category, node_type in (("people", "person"), ("locations", "location"), ("dates", "date")):
            for value in analysis.get(category, []):
                add_relationship_node(node_type, value, evidence_id)
        for index, event in enumerate(analysis.get("events", [])):
            label = event.get("description", "").strip()
            event_key = f"event:{evidence_id}:{index}"
            if label:
                nodes_by_id[event_key] = {"id": event_key, "label": label, "type": "event"}
                edge_id = f"{event_key}->{evidence_node_id}"
                edges_by_id[edge_id] = {
                    "id": edge_id,
                    "source": event_key,
                    "target": evidence_node_id,
                    "label": "derived from",
                }

    return {"nodes": list(nodes_by_id.values()), "edges": list(edges_by_id.values())}


@app.get("/api/summary")
async def summary():
    records = [record for record in list_evidence_records() if record.get("analysis")]
    analyses = [record["analysis"] for record in records]

    def unique_values(field: str) -> list[str]:
        values = []
        seen = set()
        for item in analyses:
            for value in item.get(field, []):
                normalized = value.strip()
                if normalized and normalized.casefold() not in seen:
                    seen.add(normalized.casefold())
                    values.append(normalized)
        return values

    summaries = [item.get("summary", "").strip() for item in analyses if item.get("summary")]
    events = [event for item in analyses for event in item.get("events", [])]
    return {
        "summary": "\n\n".join(summaries),
        "people": unique_values("people"),
        "locations": unique_values("locations"),
        "dates": unique_values("dates"),
        "events": events,
        "concerns": unique_values("concerns"),
        "evidence_count": len(records),
        "generated_at": datetime.now(timezone.utc).isoformat() if analyses else None,
    }


@app.get("/api/evidence/{evidence_id}/integrity")
async def evidence_integrity(evidence_id: UUID):
    evidence_path = find_stored_file(evidence_id)
    if evidence_path is None:
        raise HTTPException(status_code=404, detail="Evidence file was not found.")
    original_hash = read_evidence_metadata(evidence_id).get("sha256_hash")
    if not original_hash:
        raise HTTPException(
            status_code=409,
            detail="The original upload hash is unavailable for this evidence file.",
        )
    try:
        current_hash = calculate_sha256(evidence_path)
    except OSError:
        raise HTTPException(status_code=500, detail="Evidence file could not be verified.") from None
    return {
        "evidence_id": str(evidence_id),
        "original_sha256_hash": original_hash,
        "current_sha256_hash": current_hash,
        "verified": hmac.compare_digest(original_hash, current_hash),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/integrity")
async def integrity():
    results = []
    for record in list_evidence_records():
        evidence_id = UUID(record["evidence_id"])
        evidence_path = find_stored_file(evidence_id)
        original_hash = record.get("sha256_hash")
        if evidence_path is None or not original_hash:
            verified = False
            current_hash = None
        else:
            try:
                current_hash = calculate_sha256(evidence_path)
                verified = hmac.compare_digest(original_hash, current_hash)
            except OSError:
                current_hash = None
                verified = False
        results.append({
            "evidence_id": record["evidence_id"],
            "original_filename": record["original_filename"],
            "original_sha256_hash": original_hash,
            "current_sha256_hash": current_hash,
            "verified": verified,
        })
    exceptions = sum(not item["verified"] for item in results)
    return {
        "status": "no_evidence" if not results else "verified" if exceptions == 0 else "attention_required",
        "items_checked": len(results),
        "exceptions": exceptions,
        "algorithm": "SHA-256",
        "items": results,
    }
