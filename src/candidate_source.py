import re
import json
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

import httpx
from google.cloud import storage

from .config import settings


def _extract_app_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("applications"), list):
        return [x for x in payload["applications"] if isinstance(x, dict)]
    return []


def _normalize_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(record)
    if not row.get("candidate_name") and row.get("applicant_name"):
        row["candidate_name"] = row.get("applicant_name")
    if not row.get("email") and row.get("applicant_email"):
        row["email"] = row.get("applicant_email")
    return row


async def fetch_candidates(jd_id: str) -> List[Dict[str, Any]]:
    base = settings.source_api_base_url.rstrip("/")
    url = f"{base}/api/jds/{jd_id}/applications"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return [_normalize_candidate(x) for x in _extract_app_list(resp.json())]
        except httpx.HTTPStatusError as exc:
            # Source service may return 404 if JD metadata is missing even when applications exist.
            if exc.response.status_code != 404:
                raise

        fallback_resp = await client.get(f"{base}/api/applications")
        fallback_resp.raise_for_status()
        apps = [_normalize_candidate(x) for x in _extract_app_list(fallback_resp.json())]
        return [x for x in apps if str(x.get("jd_id", "")) == str(jd_id)]


async def fetch_jds() -> List[Dict[str, Any]]:
    url = f"{settings.source_api_base_url.rstrip('/')}/api/jds"
    payload: Any = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        payload = None

    result: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        result = payload
    elif isinstance(payload, dict):
        for key in ("jds", "items", "data"):
            if isinstance(payload.get(key), list):
                result = payload[key]
                break

        # Also support mapping shaped like {"<jd_id>": {...meta...}}
        if not result:
            mapped = []
            for k, v in payload.items():
                if isinstance(v, dict) and (v.get("jd_id") or k):
                    row = dict(v)
                    row.setdefault("jd_id", k)
                    mapped.append(row)
            result = mapped

    if result:
        return result

    # Fallback: read GCS-generated JD index when API is empty.
    try:
        client = storage.Client()
        blob = client.bucket(settings.fallback_jd_index_bucket).blob(settings.fallback_jd_index_object)
        text = blob.download_as_text()
        raw = json.loads(text)
        if isinstance(raw, dict):
            out: List[Dict[str, Any]] = []
            for jd_id, meta in raw.items():
                if isinstance(meta, dict):
                    row = dict(meta)
                    row.setdefault("jd_id", jd_id)
                    out.append(row)
            return out
    except Exception:
        pass

    return []


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t}


def _extra_boost(query: str, title: str) -> float:
    q = _norm(query)
    t = _norm(title)
    boost = 0.0

    if "lead" in q and ("manager" in t or "lead" in t):
        boost += 0.18
    if "people" in q and "manager" in t:
        boost += 0.20
    if "cloud" in q and "cloud" in t:
        boost += 0.20
    if "network" in q and "network" in t:
        boost += 0.20
    if "database" in q and ("database" in t or "dba" in t):
        boost += 0.20

    return boost


def _fallback_role_from_query(query: str) -> Tuple[str, str, float]:
    q = _norm(query)

    # Default map uses known demo JD IDs from the existing project snapshot.
    defaults = [
        ("f8fd3644", "Team Lead", ["lead", "people", "manager", "stakeholder", "leadership"]),
        ("c888c0e6", "Database Administrator", ["database", "dba", "sql", "oracle", "postgres"]),
        ("ef658af6", "Senior Engineer", ["senior", "engineer", "backend", "platform"]),
        ("3d5e83c7", "Software Engineer", ["software", "developer", "coding", "full stack"]),
    ]

    best = ("", "", 0.0)
    for jd_id, title, keys in defaults:
        score = 0.0
        for k in keys:
            if k in q:
                score += 0.2
        if "cloud" in q and title == "Senior Engineer":
            score += 0.12
        if "network" in q and title == "Senior Engineer":
            score += 0.1

        if score > best[2]:
            best = (jd_id, title, min(score, 0.95))

    return best


def resolve_best_jd(
    jds: List[Dict[str, Any]],
    manager_text: str,
    explicit_jd_id: str | None = None,
) -> Tuple[str, str, float]:
    if explicit_jd_id and not jds:
        return explicit_jd_id, "Manual JD", 0.5

    if not jds:
        return _fallback_role_from_query(manager_text)

    if explicit_jd_id:
        for jd in jds:
            if jd.get("jd_id") == explicit_jd_id:
                return explicit_jd_id, jd.get("role_title", "Unknown"), 1.0

    q = _norm(manager_text)
    q_tokens = _tokens(manager_text)

    best_id = ""
    best_title = ""
    best_score = -1.0

    for jd in jds:
        jd_id = jd.get("jd_id", "")
        title = jd.get("role_title", "")
        title_norm = _norm(title)
        t_tokens = _tokens(title)

        overlap = 0.0
        if q_tokens and t_tokens:
            overlap = len(q_tokens & t_tokens) / max(len(t_tokens), 1)

        seq = SequenceMatcher(None, q, title_norm).ratio() if q and title_norm else 0.0
        score = 0.62 * overlap + 0.38 * seq + _extra_boost(q, title)

        if score > best_score:
            best_score = score
            best_id = jd_id
            best_title = title or "Unknown"

    return best_id, best_title, max(0.0, min(1.0, best_score))


def candidate_brief(candidate: Dict[str, Any]) -> Dict[str, Any]:
    parsed = candidate.get("parsed_resume") or {}
    return {
        "application_id": candidate.get("application_id", ""),
        "name": candidate.get("candidate_name") or parsed.get("name") or "Unknown",
        "email": candidate.get("email") or parsed.get("email") or "",
        "title": parsed.get("title") or candidate.get("title") or "",
        "years_experience": parsed.get("years_experience") or candidate.get("years_experience") or "",
        "skills": parsed.get("skills") or candidate.get("skills") or [],
        "current_score": candidate.get("match_score") or 0,
        "strengths_summary": candidate.get("strengths_summary") or "",
    }
