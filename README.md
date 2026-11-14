# EvidentAI

EvidentAI is an AI-powered digital evidence intelligence platform starter for organizing and reviewing evidence. This repository contains a React + Vite frontend and a Python + FastAPI backend. Uploaded files and analysis metadata are stored temporarily on the backend filesystem; no database or Supabase connection is configured.

## Requirements

- Node.js 18+ and npm
- Python 3.10+

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves the app at http://localhost:5173. Set `VITE_API_BASE_URL` in `frontend/.env` to change the backend URL; it defaults to `http://localhost:8000`.

## Run the backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000. Interactive docs are at http://localhost:8000/docs and health check at http://localhost:8000/api/health. CORS allows the Vite development origin; configure `FRONTEND_ORIGIN` to change it.

To enable Gemini analysis, copy `backend/.env.example` to `backend/.env`, then set `GEMINI_API_KEY` in that backend-only file. `GEMINI_MODEL` is optional; it defaults to `gemini-3.8-flash`. Never put the Gemini key in the frontend.

## Analyze evidence text

Start the backend, open http://127.0.0.1:8000/docs, expand **POST /api/analyze**, select **Try it out**, submit this request, and select **Execute**:

```json
{
  "evidence_text": "On 2025-04-12, Jordan Lee met Casey Morgan at the North Station office. A payment was discussed at 14:30."
}
```

The response contains `summary`, `people`, `locations`, `dates`, `events` (in chronological order, each with `date_or_time` and `description`), and `concerns`. The endpoint analyzes the submitted text without storing it. Invalid input returns HTTP 422, missing Gemini configuration returns HTTP 503, and Gemini or invalid-response failures return HTTP 502.

Evidence files and their small metadata/analysis sidecars are stored locally under `backend/uploads/`. This is temporary file storage; no database or Supabase connection is configured. Dashboard, evidence list, timeline, graph, summary, and integrity responses are derived from these local records. Cases remain empty until the separate database integration is added.

## Extract and analyze a PDF

1. Open http://127.0.0.1:8000/docs and use **POST /api/evidence/upload** to upload a readable, text-based PDF. Copy the `evidence_id` from the response.
2. In Swagger, open **POST /api/evidence/{evidence_id}/analyze**, choose **Try it out**, paste that UUID into the `evidence_id` field, and choose **Execute**.

The endpoint reads the PDF already stored in `backend/uploads/`, extracts its text with pypdf, and sends it to the existing Gemini analysis service. It returns the evidence ID, original filename, a short text preview, extraction status, and structured analysis. The full extracted text is not returned. Scanned image-only PDFs are not supported because OCR is not enabled. Missing files, non-PDF evidence, unreadable PDFs, empty extraction results, oversized extracted text, and Gemini errors return clear HTTP errors. No database is used.

## Upload evidence files

Open http://127.0.0.1:8000/docs, expand **POST /api/evidence/upload**, choose **Try it out**, select one file, and choose **Execute**. Supported extensions are `.pdf`, `.jpg`, `.jpeg`, `.png`, `.txt`, `.csv`, `.mp3`, `.wav`, and `.m4a`; files must be non-empty and no larger than 200 MB. A successful response includes the evidence UUID, detected category, byte size, SHA-256 hash, upload status, and UTC upload time. Uploaded files are stored temporarily under `backend/uploads/`; that directory is ignored by Git. No database is used.

## Analyze uploaded evidence

After uploading a file, copy its `evidence_id` and call **POST /api/evidence/{evidence_id}/analyze** in Swagger. The backend extracts text from PDF, TXT, and CSV files, runs OCR on images, and transcribes supported audio before sending the resulting text to Gemini. Results are saved in the temporary evidence metadata so the dashboard, timeline, relationship graph, and AI Summary pages can display them. **POST /api/analyze** remains available for direct text analysis.

Image OCR uses Pillow and the `pytesseract` Python wrapper, plus the separate Tesseract OCR executable. On Windows, install Tesseract using the [official Tesseract installation guidance](https://github.com/tesseract-ocr/tessdoc/blob/main/Installation.md), ensure `tesseract.exe` is on `PATH`, then restart the terminal and backend. If the executable is unavailable, image analysis returns an actionable error. OCR only extracts visible text; scanned PDFs still require OCR support and currently return a clear no-extractable-text response.

Audio transcription uses Gemini's `gemini-3.5-transcribe` model through the existing backend Gemini credentials and Files API; no local FFmpeg or speech-recognition package is required. Audio is sent to Gemini for transcription and the temporary remote file is deleted after the request. This requires network access and an enabled Gemini API key. See Google's [audio transcription documentation](https://ai.google.dev/gemini-api/docs/transcribe?hl=en) for supported formats and service limits.

## Integrity re-verification

Open **Integrity Center** in the frontend and choose **Re-verify** for an evidence item, or call `GET /api/evidence/{evidence_id}/integrity` from Swagger. The endpoint recalculates SHA-256 and compares it with the hash recorded at upload.
