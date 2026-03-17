from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .candidate_source import fetch_candidates, fetch_jds, resolve_best_jd
from .models import RerankChatRequest, RerankChatResponse
from .rerank_agent import rerank_with_preferences

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Recruiter Re-Ranking Agent")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "recruiter-agent"}


@app.post("/chat-rerank", response_model=RerankChatResponse)
async def chat_rerank(payload: RerankChatRequest) -> RerankChatResponse:
    try:
        jds = await fetch_jds()
    except Exception:
        jds = []

    context_text = " ".join(
        [turn.content for turn in payload.history if turn.role == "user"][-4:] + [payload.message]
    ).strip()

    selected_jd_id, selected_jd_title, confidence = resolve_best_jd(
        jds=jds,
        manager_text=context_text,
        explicit_jd_id=payload.jd_id,
    )

    if not selected_jd_id:
        return RerankChatResponse(
            reply=(
                "I could not find a JD to match yet. "
                "Please add one more clue like 'cloud infrastructure', 'people manager', "
                "'network', or 'database', or provide JD ID once."
            ),
            selected_jd_id="",
            selected_jd_title="Unknown",
            manager_preference_summary="No JD match found.",
            ranked_candidates=[],
            candidate_count=0,
            raw_model_output={"manager_preference_summary": "No JD match found.", "ranked_candidates": []},
        )

    try:
        candidates = await fetch_candidates(selected_jd_id)
    except Exception as exc:
        return RerankChatResponse(
            reply=(
                f"I matched JD '{selected_jd_title}' ({selected_jd_id}), "
                f"but failed to load candidates from source API: {exc}"
            ),
            selected_jd_id=selected_jd_id,
            selected_jd_title=selected_jd_title,
            manager_preference_summary="JD matched but candidate source unavailable.",
            ranked_candidates=[],
            candidate_count=0,
            raw_model_output={"manager_preference_summary": "JD matched but candidate source unavailable.", "ranked_candidates": []},
        )

    if not candidates:
        return RerankChatResponse(
            reply=(
                f"I matched JD '{selected_jd_title}' ({selected_jd_id}), "
                "but no candidates are currently available for this role."
            ),
            selected_jd_id=selected_jd_id,
            selected_jd_title=selected_jd_title,
            manager_preference_summary="JD matched, no candidates found.",
            ranked_candidates=[],
            candidate_count=0,
            raw_model_output={"manager_preference_summary": "JD matched, no candidates found.", "ranked_candidates": []},
        )

    model_output = rerank_with_preferences(
        jd_id=selected_jd_id,
        manager_message=payload.message,
        history=[turn.model_dump() for turn in payload.history],
        raw_candidates=candidates,
    )

    ranked = model_output.get("ranked_candidates", [])
    reply_lines = [
        f"Matched JD: {selected_jd_title} ({selected_jd_id}) | confidence={confidence:.2f}",
        f"Preference summary: {model_output.get('manager_preference_summary', 'N/A')}",
        "Top ranking:",
    ]
    for idx, item in enumerate(ranked[:5], 1):
        reply_lines.append(
            f"{idx}. {item.get('candidate_name', 'Unknown')} - {item.get('revised_score', 0)}"
        )

    return RerankChatResponse(
        reply="\n".join(reply_lines),
        selected_jd_id=selected_jd_id,
        selected_jd_title=selected_jd_title,
        manager_preference_summary=model_output.get("manager_preference_summary", ""),
        ranked_candidates=ranked,
        candidate_count=len(candidates),
        raw_model_output=model_output,
    )
