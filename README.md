# Recruiter Chat Re-Ranking Agent

A standalone chat agent for hiring managers/recruiters to re-rank candidates using personalized preferences.

## What It Does
- Reads candidates from existing JD service API (`jd-agent-gcp`):
  - `GET /api/jds/{jd_id}/applications`
- Accepts manager preference text in chat.
- Uses Gemini to re-score and re-rank all candidates.
- Returns ranked list with reason and tradeoff per candidate.

## Location
This project is intentionally separate from `jd-agent-gcp`:
- `/Users/jackyt/Documents/github02/recruiter-agent`

## Quick Start
```bash
cd /Users/jackyt/Documents/github02/recruiter-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_CLOUD_PROJECT=demo0908
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=true
export MODEL_NAME=gemini-2.5-pro
export SOURCE_API_BASE_URL=http://127.0.0.1:8080

uvicorn src.main:app --host 127.0.0.1 --port 8090
```

Open: `http://127.0.0.1:8090`

## API
- `POST /chat-rerank`
  - Request:
    - `jd_id`: string
    - `message`: recruiter preference text
    - `history`: chat history (optional)
  - Response:
    - `manager_preference_summary`
    - `ranked_candidates[]`
    - `reply`

## Notes
- Keep `jd-agent-gcp` running so this service can fetch applications.
- If model output parsing fails, fallback ranking uses existing `match_score`.
