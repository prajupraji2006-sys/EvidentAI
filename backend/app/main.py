from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app import config as _config  # Load backend/.env before application settings.
from app.security import append_audit_event, authenticated_user
from app.services.ai_analysis import EvidenceAnalysis, GeminiServiceError, InvalidGeminiResponseError, analyze_evidence
from app.services.authenticity import assess_file
from app.services.evidence_processing import MAX_ANALYSIS_TEXT_CHARS, EvidenceTextError, extract_evidence_text
from app.services.evidence_upload import (
    EvidenceUploadError, EvidenceUploadResult, calculate_sha256, find_stored_file,
    get_supabase_client, list_evidence_records, read_evidence_metadata,
    save_analysis_result, save_evidence_file, set_processing_status, verify_evidence_integrity,
)

logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGINS") or os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if os.getenv("APP_ENV", "development").lower() != "production":
        origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
    return sorted(set(origins))


app = FastAPI(title="EvidentAI API", version="0.2.0", description="Authenticated digital evidence intake and intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(), allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(Exception)
async def safe_internal_error(_request, exc: Exception):
    # Avoid returning provider errors, evidence content, or credential-bearing URLs.
    logger.error("Unhandled API error (error_type=%s)", type(exc).__name__)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": "The request could not be completed."})


@app.get("/")
async def root():
    return {"status": "EvidentAI API is running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "evidentai-api"}


class AnalyzeRequest(BaseModel):
    evidence_text: str = Field(min_length=1, max_length=MAX_ANALYSIS_TEXT_CHARS)

    @field_validator("evidence_text")
    @classmethod
    def evidence_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("evidence_text must contain non-whitespace text")
        return value


class IncidentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Incident title cannot be blank.")
        return value


@app.post("/api/profile/bootstrap")
def bootstrap_profile(user: dict[str, str] = Depends(authenticated_user)):
    """Create the authenticated user's profile once, without accepting a client-supplied id or role."""
    client = get_supabase_client()
    existing = client.table("profiles").select(
        "id,full_name,role,created_at,updated_at"
    ).eq("id", user["id"]).limit(1).execute().data or []
    if existing:
        return {"profile": existing[0], "created": False}
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = client.table("profiles").insert({
            "id": user["id"],
            "role": "investigator",
            "created_at": now,
            "updated_at": now,
        }).execute().data or []
    except Exception:
        # A concurrent first request may have inserted the same unique user id.
        rows = client.table("profiles").select(
            "id,full_name,role,created_at,updated_at"
        ).eq("id", user["id"]).limit(1).execute().data or []
        if not rows:
            raise HTTPException(status_code=503, detail="The user profile could not be initialized.") from None
    if not rows:
        raise HTTPException(status_code=503, detail="The user profile could not be initialized.")
    return {"profile": rows[0], "created": True}


@app.post("/api/analyze", response_model=EvidenceAnalysis)
def analyze(request: AnalyzeRequest, user: dict[str, str] = Depends(authenticated_user)) -> EvidenceAnalysis:
    try:
        result = analyze_evidence(request.evidence_text)
        append_audit_event(user["id"], "analysis_completed", "text_analysis", None)
        return result
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Gemini analysis is not configured.") from None
    except InvalidGeminiResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except GeminiServiceError:
        raise HTTPException(status_code=502, detail="Gemini analysis is temporarily unavailable. Please retry.") from None


@app.get("/api/cases")
def cases(user: dict[str, str] = Depends(authenticated_user)):
    rows = get_supabase_client().table("incidents").select(
        "id,owner_id,incident_number,title,description,status,created_at,updated_at"
    ).eq("owner_id", user["id"]).order("created_at", desc=True).execute().data or []
    return {"cases": rows}


@app.post("/api/audit/login")
def record_login(user: dict[str, str] = Depends(authenticated_user)):
    return {"recorded": append_audit_event(user["id"], "login", "account", user["id"])}


@app.post("/api/cases", status_code=201)
def create_case(request: IncidentCreateRequest, user: dict[str, str] = Depends(authenticated_user)):
    now = datetime.now(timezone.utc).isoformat()
    case_id = uuid4()
    row = {
        "id": str(case_id), "owner_id": user["id"],
        "incident_number": f"INC-{case_id.hex[:8].upper()}",
        "title": request.title, "description": request.description,
        "status": "active", "created_at": now, "updated_at": now,
    }
    saved = get_supabase_client().table("incidents").insert(row).execute().data or []
    if not saved:
        raise HTTPException(status_code=503, detail="The incident could not be saved.")
    append_audit_event(user["id"], "incident_created", "incident", str(case_id))
    return {"case": saved[0]}


@app.get("/api/dashboard")
def dashboard(user: dict[str, str] = Depends(authenticated_user)):
    records = list_evidence_records(user["id"])
    cases_response = get_supabase_client().table("incidents").select("id,status").eq("owner_id", user["id"]).execute()
    analyses = [row.get("analysis") or {} for row in records if row.get("analysis")]
    return {
        "active_investigations": sum(1 for case in (cases_response.data or []) if case.get("status") == "active"),
        "evidence_items": len(records),
        "events_identified": sum(len(item.get("events", [])) for item in analyses),
        "integrity_verified_percent": None,
        "processing_items": sum(1 for row in records if row.get("processing_status") in {"uploaded", "processing"}),
        "recent_evidence": records[:5],
    }


@app.get("/api/evidence")
def evidence_list(user: dict[str, str] = Depends(authenticated_user)):
    return {"items": list_evidence_records(user["id"])}


@app.post("/api/evidence/upload", response_model=EvidenceUploadResult)
def upload_evidence(file: UploadFile = File(...), incident_id: UUID = Form(...), user: dict[str, str] = Depends(authenticated_user)) -> EvidenceUploadResult:
    try:
        result = save_evidence_file(file, incident_id, user["id"])
    except EvidenceUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    append_audit_event(user["id"], "evidence_uploaded", "evidence", str(result.evidence_id), {
        "incident_id": str(incident_id), "file_size": result.file_size,
        "sha256_hash": result.sha256_hash, "exact_duplicate": result.exact_duplicate,
    })
    append_audit_event(user["id"], "hash_created", "evidence", str(result.evidence_id), {
        "algorithm": "SHA-256", "sha256_hash": result.sha256_hash,
    })
    return result


class EvidenceAnalysisResponse(BaseModel):
    evidence_id: str
    original_filename: str
    extracted_text_preview: str
    extraction_status: str
    extraction_method: str
    analysis: EvidenceAnalysis


def _analyze_evidence_job(evidence_id: UUID, user_id: str) -> EvidenceAnalysisResponse:
    metadata = read_evidence_metadata(evidence_id, user_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Evidence file was not found.")
    evidence_path = find_stored_file(evidence_id, user_id)
    try:
        extracted_text, extraction_method = extract_evidence_text(evidence_path, metadata.get("evidence_type", ""))
        if len(extracted_text) > MAX_ANALYSIS_TEXT_CHARS:
            raise HTTPException(status_code=413, detail=f"Extracted content exceeds the {MAX_ANALYSIS_TEXT_CHARS:,} character analysis limit.")
        analysis = analyze_evidence(extracted_text)
        preview = extracted_text[:500] + ("… [preview only]" if len(extracted_text) > 500 else " [preview only]")
        save_analysis_result(evidence_id, user_id, analysis.model_dump(mode="json"), preview, extraction_method)
        append_audit_event(user_id, "analysis_completed", "evidence", str(evidence_id), {"extraction_method": extraction_method})
        return EvidenceAnalysisResponse(
            evidence_id=str(evidence_id), original_filename=metadata.get("original_filename", "Evidence file"),
            extracted_text_preview=preview, extraction_status="processed", extraction_method=extraction_method, analysis=analysis,
        )
    finally:
        evidence_path.unlink(missing_ok=True)


@app.post("/api/evidence/{evidence_id}/analyze", response_model=EvidenceAnalysisResponse)
def analyze_uploaded_evidence(evidence_id: UUID, user: dict[str, str] = Depends(authenticated_user)):
    try:
        set_processing_status(evidence_id, user["id"], "processing")
        append_audit_event(user["id"], "analysis_started", "evidence", str(evidence_id))
        return _analyze_evidence_job(evidence_id, user["id"])
    except HTTPException:
        try:
            set_processing_status(evidence_id, user["id"], "failed", "Evidence processing failed. Retry when the file and required services are available.")
            append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id))
        except Exception:
            pass
        raise
    except HTTPException:
        try:
            set_processing_status(evidence_id, user["id"], "failed", "Evidence processing failed. Retry when the source file and required services are available.")
            append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id))
        except Exception:
            pass
        raise
    except EvidenceTextError as exc:
        set_processing_status(evidence_id, user["id"], "failed", str(exc))
        append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": type(exc).__name__})
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except RuntimeError:
        set_processing_status(evidence_id, user["id"], "failed", "Gemini analysis is not configured.")
        append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": "configuration"})
        raise HTTPException(status_code=503, detail="Gemini analysis is not configured.") from None
    except InvalidGeminiResponseError as exc:
        set_processing_status(evidence_id, user["id"], "failed", str(exc))
        append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": "invalid_model_response"})
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except GeminiServiceError:
        set_processing_status(evidence_id, user["id"], "failed", "Gemini analysis is temporarily unavailable.")
        append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": "ai_provider"})
        raise HTTPException(status_code=502, detail="Gemini analysis is temporarily unavailable. Please retry.") from None
    except EvidenceUploadError as exc:
        try:
            set_processing_status(evidence_id, user["id"], "failed", "The stored evidence could not be retrieved for processing.")
            append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": "storage"})
        except Exception:
            pass
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None


@app.get("/api/timeline")
def timeline(user: dict[str, str] = Depends(authenticated_user)):
    events = []
    for record in list_evidence_records(user["id"]):
        for event in (record.get("analysis") or {}).get("events", []):
            events.append({**event, "evidence_id": record["evidence_id"], "original_filename": record["original_filename"]})
    def event_sort_key(item):
        value = str(item.get("date_or_time") or "")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (0, parsed.timestamp())
        except (TypeError, ValueError):
            return (1, value.casefold())
    events.sort(key=event_sort_key)
    return {"events": events}


@app.get("/api/graph")
def graph(user: dict[str, str] = Depends(authenticated_user)):
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for record in list_evidence_records(user["id"]):
        evidence_id = record["evidence_id"]
        target = f"evidence:{evidence_id}"
        nodes[target] = {"id": target, "label": record["original_filename"], "type": "evidence", "evidence_id": evidence_id}
        analysis = record.get("analysis") or {}
        for category, kind in (("people", "person"), ("locations", "location"), ("dates", "date")):
            for value in analysis.get(category, []):
                label = str(value).strip()
                if not label:
                    continue
                node_id = f"{kind}:{label.casefold()}"
                if node_id not in nodes:
                    nodes[node_id] = {"id": node_id, "label": label, "type": kind, "source_evidence_ids": []}
                if evidence_id not in nodes[node_id]["source_evidence_ids"]:
                    nodes[node_id]["source_evidence_ids"].append(evidence_id)
                edge_id = f"{node_id}->{target}"
                edges[edge_id] = {"id": edge_id, "source": node_id, "target": target, "label": "mentioned in", "evidence_id": evidence_id}
        for index, event in enumerate(analysis.get("events", [])):
            label = str(event.get("description", "")).strip()
            if label:
                node_id = f"event:{evidence_id}:{index}"
                nodes[node_id] = {"id": node_id, "label": label, "type": "event", "source_evidence_ids": [evidence_id]}
                edge_id = f"{node_id}->{target}"
                edges[edge_id] = {"id": edge_id, "source": node_id, "target": target, "label": "derived from", "evidence_id": evidence_id}
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


@app.get("/api/summary")
def summary(user: dict[str, str] = Depends(authenticated_user)):
    records = [row for row in list_evidence_records(user["id"]) if row.get("analysis")]
    analyses = [row["analysis"] for row in records]
    def unique_values(field: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for analysis in analyses:
            for item in analysis.get(field, []):
                value = str(item).strip()
                if value and value.casefold() not in seen:
                    seen.add(value.casefold())
                    result.append(value)
        return result
    summaries = [str(item.get("summary", "")).strip() for item in analyses if item.get("summary")]
    events = [{**event, "evidence_id": row["evidence_id"], "original_filename": row["original_filename"]} for row in records for event in row["analysis"].get("events", [])]
    return {"summary": "\n\n".join(summaries), "people": unique_values("people"), "locations": unique_values("locations"),
            "dates": unique_values("dates"), "events": events, "concerns": unique_values("concerns"), "evidence_count": len(records),
            "generated_at": datetime.now(timezone.utc).isoformat() if analyses else None}


@app.post("/api/evidence/{evidence_id}/authenticity-assessment")
def create_authenticity_assessment(evidence_id: UUID, user: dict[str, str] = Depends(authenticated_user)):
    metadata = read_evidence_metadata(evidence_id, user["id"])
    if metadata is None:
        raise HTTPException(status_code=404, detail="Evidence file was not found.")
    path = find_stored_file(evidence_id, user["id"])
    try:
        assessment = assess_file(path, metadata.get("evidence_type", ""))
        client = get_supabase_client()
        hash_rows = client.table("evidence_hashes").select(
            "sha256_hash"
        ).eq("evidence_id", str(evidence_id)).limit(1).execute().data or []
        if hash_rows and hash_rows[0].get("sha256_hash"):
            expected_hash = str(hash_rows[0]["sha256_hash"])
            current_hash = calculate_sha256(path)
            verified = expected_hash.casefold() == current_hash.casefold()
            verified_at = datetime.now(timezone.utc).isoformat()
            client.table("evidence_hashes").update({
                "verified_at": verified_at,
                "verification_status": "verified" if verified else "failed",
            }).eq("evidence_id", str(evidence_id)).execute()
            assessment["integrity_information"] = {
                "status": "VERIFIED" if verified else "FAILED",
                "algorithm": "SHA-256",
                "stored_hash": expected_hash,
                "current_hash": current_hash,
                "verified_at": verified_at,
                "meaning": "A matching hash confirms these stored bytes match the upload hash; it does not prove the source file was genuine.",
            }
            append_audit_event(user["id"], "integrity_verified", "evidence", str(evidence_id), {
                "verification_status": "verified" if verified else "failed",
            })
        else:
            assessment["integrity_information"] = {"status": "NOT VERIFIED", "algorithm": "SHA-256"}
    finally:
        path.unlink(missing_ok=True)
    saved = get_supabase_client().table("authenticity_assessments").insert({
        "evidence_id": str(evidence_id), "classification": assessment["classification"],
        "confidence": assessment["confidence"], "assessment": assessment,
    }).execute().data or []
    append_audit_event(user["id"], "authenticity_assessment_created", "evidence", str(evidence_id), {"classification": assessment["classification"]})
    return {"assessment_id": saved[0]["id"] if saved else None, **assessment}


@app.get("/api/evidence/{evidence_id}/authenticity-assessment")
def get_authenticity_assessment(evidence_id: UUID, user: dict[str, str] = Depends(authenticated_user)):
    if read_evidence_metadata(evidence_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Evidence file was not found.")
    rows = get_supabase_client().table("authenticity_assessments").select("id,assessment,created_at").eq("evidence_id", str(evidence_id)).order("created_at", desc=True).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="No authenticity assessment is available yet.")
    return {"assessment_id": rows[0]["id"], "created_at": rows[0]["created_at"], **rows[0]["assessment"]}


@app.get("/api/evidence/{evidence_id}/integrity")
def evidence_integrity(evidence_id: UUID, user: dict[str, str] = Depends(authenticated_user)):
    try:
        result = verify_evidence_integrity(evidence_id, user["id"])
    except EvidenceUploadError as exc:
        try:
            set_processing_status(evidence_id, user["id"], "failed", "The original file could not be retrieved for processing.")
            append_audit_event(user["id"], "analysis_failed", "evidence", str(evidence_id), {"error_type": "storage"})
        except Exception:
            pass
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    append_audit_event(user["id"], "integrity_verified", "evidence", str(evidence_id), {"verification_status": result["verification_status"]})
    return {"evidence_id": result["evidence_id"], "original_sha256_hash": result["original_hash"],
            "current_sha256_hash": result["current_hash"], "verified": result["verified"],
            "verification_status": result["verification_status"], "checked_at": result["verified_at"]}


@app.get("/api/integrity")
def integrity(user: dict[str, str] = Depends(authenticated_user)):
    results = []
    for record in list_evidence_records(user["id"]):
        try:
            result = verify_evidence_integrity(UUID(record["evidence_id"]), user["id"])
        except EvidenceUploadError:
            result = {"evidence_id": record["evidence_id"], "original_hash": record.get("sha256_hash"), "current_hash": None, "verified": False, "verification_status": "failed", "verified_at": None}
        results.append({"evidence_id": record["evidence_id"], "original_filename": record["original_filename"],
                        "original_sha256_hash": result["original_hash"], "current_sha256_hash": result["current_hash"],
                        "verified": result["verified"], "verification_status": result["verification_status"]})
    failures = sum(1 for item in results if not item["verified"])
    return {"status": "no_evidence" if not results else "verified" if not failures else "attention_required",
            "items_checked": len(results), "exceptions": failures, "algorithm": "SHA-256", "items": results}


@app.get("/api/audit")
def audit_log(limit: int = 100, user: dict[str, str] = Depends(authenticated_user)):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500.")
    rows = get_supabase_client().table("audit_logs").select(
        "id,actor_id,action,resource_type,resource_id,event_data,previous_hash,current_hash,created_at"
    ).eq("actor_id", user["id"]).order("created_at", desc=True).limit(limit).execute().data or []
    return {"items": rows}
