from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: str
    content: str


class RerankChatRequest(BaseModel):
    jd_id: str | None = None
    message: str = Field(min_length=1)
    history: List[ChatTurn] = []


class RankedCandidate(BaseModel):
    application_id: str
    candidate_name: str
    revised_score: int
    reason: str
    key_tradeoff: str


class RerankChatResponse(BaseModel):
    reply: str
    selected_jd_id: str
    selected_jd_title: str
    manager_preference_summary: str
    ranked_candidates: List[RankedCandidate]
    candidate_count: int
    raw_model_output: Dict[str, Any]
