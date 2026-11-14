# EvidentAI

EvidentAI is a React/Vite evidence review interface backed by FastAPI, Supabase Auth, Supabase Postgres, private Supabase Storage, and Gemini analysis. The original evidence file is stored separately from extracted text and analysis. No sample evidence is inserted into production workflows.

## Current architecture

- **Frontend:** React 18, Vite, React Router, Supabase Auth. Browser requests use the Supabase publishable key and the signed-in user's bearer token.
- **Backend:** Python 3.10+, FastAPI. The Supabase secret/service key and Gemini API key stay server-side.
- **Database and storage:** Existing `profiles`, `incidents`, `evidence`, and `evidence_hashes` tables and the private `evidence-files` bucket. A migration in `supabase/migrations/` adds analysis, authenticity, audit-chain, owner-policy, duplicate, and analysis-status support.
- **Evidence pipeline:** Extension, declared MIME, and basic file-signature validation, a 200 MB cap, streamed local hashing, private Storage upload, metadata and SHA-256 records, PDF/text/CSV extraction, image OCR, audio transcription, and Gemini structured analysis. The Tesseract OCR engine must be installed on the backend host and available on PATH; `pytesseract` is only its Python wrapper.
- **Assessment limits:** Authenticity checks report measurable metadata and always classify results as `INCONCLUSIVE` until a validated forensic detector is added. The service does not prove fraud, genuineness, manipulation, or AI generation.

## Local setup

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env.local`. Fill the backend file with `SUPABASE_URL`, a server-only `SUPABASE_SECRET_KEY`, and `GEMINI_API_KEY`. Fill the frontend file with `VITE_SUPABASE_URL`, the public `VITE_SUPABASE_PUBLISHABLE_KEY`, and the backend URL in `VITE_API_BASE_URL`. Never place the Supabase secret/service-role key or Gemini key in a `VITE_` variable.

Install and run the backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765
```

Install and run the frontend in another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Configure Supabase Auth email confirmation and redirect URLs for the local Vite origin. In the app, sign in. The frontend waits for the backend to ensure the signed-in user's profile exists, then create or select an active incident and upload a supported file. A failed processing job retains the original evidence record and can be retried from the Evidence Vault.

## Supabase migration

The existing database and private bucket were inspected read-only. The database currently lacks the `evidence_analysis`, `authenticity_assessments`, and `audit_logs` tables. Review and apply `supabase/migrations/202611150001_evidence_security_foundation.sql` in the Supabase SQL Editor or with the Supabase CLI before using analysis persistence, authenticity assessment, or the audit trail. The migration enables owner-scoped RLS and keeps the evidence bucket private. The backend also filters each service-role query by the authenticated user because service-role requests bypass RLS.

Do not apply this migration to a different Supabase project without reviewing its existing policies. The migration replaces policies on the EvidentAI application tables with the documented owner rules.

## API

Public endpoints: `GET /` and `GET /api/health`.

All other endpoints require `Authorization: Bearer <Supabase access token>`:

- `POST /api/analyze`
- `POST /api/profile/bootstrap`
- `GET, POST /api/cases`
- `GET /api/dashboard`
- `GET /api/evidence`
- `POST /api/evidence/upload` (multipart `file` and `incident_id`)
- `POST /api/evidence/{evidence_id}/analyze`
- `GET /api/timeline`, `/api/graph`, `/api/summary`
- `POST, GET /api/evidence/{evidence_id}/authenticity-assessment`
- `GET /api/evidence/{evidence_id}/integrity`, `GET /api/integrity`
- `GET /api/audit` and `POST /api/audit/login`

Interactive API docs are available locally at `http://localhost:8765/docs`.

## Verification

Run backend tests after `pip install -r requirements-dev.txt` with `cd backend; python -m pytest -q`. Build the frontend with `cd frontend; npm run build`. Tests use clearly synthetic temporary fixtures and do not write to Supabase.

## Deployment

`render.yaml` and `frontend/vercel.json` provide deployment configuration for Render and Vercel. Before deploying, apply the migration, set backend secrets in Render, set the three frontend variables in Vercel, set `FRONTEND_ORIGINS` to the exact deployed frontend origin, configure Supabase Auth redirect URLs, and run end-to-end checks against the deployed services. No public URLs are configured or claimed by this repository.

## Known limitations

- Evidence processing currently runs synchronously in the API request; there is no durable worker or job queue.
- MP3/M4A metadata extraction, signed PDF signature verification, C2PA validation, perceptual-hash image comparison, reliable AI-generated-content detection, contradiction detection, and source-region citations are not implemented.
- There is no secure evidence download/preview endpoint yet.
- Audit hash chaining covers implemented backend actions only. Login events, downloads, deletions, and sharing actions are not yet recorded.
- The Supabase migration must be applied to the intended project. Production deployment and authenticated end-to-end upload have not been verified.
