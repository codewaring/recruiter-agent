import json
from typing import Any, Dict, List

from google import genai

from .candidate_source import candidate_brief
from .config import settings


def _client() -> genai.Client:
    return genai.Client(
        vertexai=(settings.google_genai_use_vertexai.lower() == "true"),
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
    )


def _fallback_rank(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    sorted_items = sorted(candidates, key=lambda c: int(c.get("current_score", 0)), reverse=True)
    ranked = []
    for c in sorted_items:
        ranked.append(
            {
                "application_id": c.get("application_id", ""),
                "candidate_name": c.get("name", "Unknown"),
                "revised_score": int(c.get("current_score", 0)),
                "reason": "Fallback ranking based on existing match_score because model output was not parseable.",
                "key_tradeoff": "No personalized re-weighting was applied in fallback mode.",
            }
        )
    return {
        "manager_preference_summary": "Fallback mode applied.",
        "ranked_candidates": ranked,
    }


def rerank_with_preferences(
    jd_id: str,
    manager_message: str,
    history: List[Dict[str, str]],
    raw_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    compact_candidates = [candidate_brief(c) for c in raw_candidates]

    prompt = {
        "task": "Re-evaluate candidate ranking for a recruiter based on manager preference in chat.",
        "rules": [
            "Use manager preference as re-weighting criteria.",
            "Keep revised_score in range 0-100.",
            "Return all candidates in ranked order.",
            "Explain each score with one concise reason and one tradeoff.",
            "Respond with JSON only.",
        ],
        "jd_id": jd_id,
        "manager_message": manager_message,
        "chat_history": history[-6:],
        "candidates": compact_candidates,
        "response_schema": {
            "manager_preference_summary": "string",
            "ranked_candidates": [
                {
                    "application_id": "string",
                    "candidate_name": "string",
                    "revised_score": "integer 0-100",
                    "reason": "string",
                    "key_tradeoff": "string",
                }
            ],
        },
    }

    client = _client()
    response = client.models.generate_content(
        model=settings.model_name,
        contents=json.dumps(prompt, ensure_ascii=True),
    )

    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Model output is not a JSON object")
        if not isinstance(parsed.get("ranked_candidates"), list):
            raise ValueError("Missing ranked_candidates")
        return parsed
    except Exception:
        return _fallback_rank(compact_candidates)
