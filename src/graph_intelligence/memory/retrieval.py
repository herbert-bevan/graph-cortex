"""Deterministic scoring engine for user memory retrieval."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from graph_intelligence.common.text import normalize_term, squash, tokenize


def calculate_recency_score(created_at_str: Optional[str]) -> float:
    """Calculate linear recency score between 0.0 and 0.5 over the last 30 days."""
    if not created_at_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_old = (now - dt).total_seconds() / 86400.0
        if days_old <= 0:
            return 0.5
        if days_old >= 30:
            return 0.0
        return round(0.5 * (1.0 - (days_old / 30.0)), 4)
    except Exception:
        return 0.0


def score_summary(
    candidate: Dict[str, Any],
    query_text: str,
    query_keywords: List[str],
    query_entities: List[str],
    query_project: Optional[str] = None,
    query_adjacent_entity_ids: Optional[Set[str]] = None,
) -> Tuple[float, List[str], List[str], str]:
    """
    Score a candidate SessionSummary deterministically against search signals.
    Returns: (total_score, matched_keywords, matched_entities, match_reason)
    """
    score = 0.0
    matched_keywords: List[str] = []
    matched_entities: List[str] = []
    reasons: List[str] = []

    # 1. Project match: +4
    cand_proj_id = candidate.get("project_id") or ""
    cand_proj_name = candidate.get("project_name") or ""
    if query_project:
        q_proj_squashed = squash(query_project)
        if q_proj_squashed in (squash(cand_proj_id), squash(cand_proj_name)):
            score += 4.0
            reasons.append("project_match(+4.0)")

    # 2. Entity matches: +5 each (max 15)
    # candidate entities: linked_entities (list of dicts) + entity_keys (list of strings)
    cand_entity_squashed = set()
    for e in candidate.get("linked_entities") or []:
        if isinstance(e, dict):
            if e.get("id"):
                cand_entity_squashed.add(squash(e["id"]))
            if e.get("name"):
                cand_entity_squashed.add(squash(e["name"]))
    for ek in candidate.get("entity_keys") or []:
        cand_entity_squashed.add(squash(ek))

    entity_points = 0.0
    for qe in query_entities:
        qe_squashed = squash(qe)
        if qe_squashed and qe_squashed in cand_entity_squashed:
            if entity_points < 15.0:
                entity_points = min(entity_points + 5.0, 15.0)
                matched_entities.append(qe)
    if entity_points > 0:
        score += entity_points
        reasons.append(f"entity_match(+{entity_points})")

    # 3. Phrase match of provided keyword with stored keyword: +3 each (max 12)
    stored_keywords = candidate.get("keywords") or []
    if isinstance(stored_keywords, str):
        stored_keywords = [stored_keywords]
    stored_keywords_norm = [normalize_term(k) for k in stored_keywords]

    kw_phrase_points = 0.0
    for qk in query_keywords:
        norm_qk = normalize_term(qk)
        if norm_qk and any(norm_qk == sk or norm_qk in sk for sk in stored_keywords_norm):
            if kw_phrase_points < 12.0:
                kw_phrase_points = min(kw_phrase_points + 3.0, 12.0)
                if qk not in matched_keywords:
                    matched_keywords.append(qk)
    if kw_phrase_points > 0:
        score += kw_phrase_points
        reasons.append(f"keyword_phrase(+{kw_phrase_points})")

    # 4. Token overlap: query/keyword tokens ∩ stored-keyword tokens: +2 each distinct token (max 12)
    query_tokens = set(tokenize(query_text))
    for qk in query_keywords:
        query_tokens.update(tokenize(qk))

    stored_kw_tokens = set()
    for sk in stored_keywords:
        stored_kw_tokens.update(tokenize(sk))

    common_kw_tokens = query_tokens.intersection(stored_kw_tokens)
    kw_token_points = min(len(common_kw_tokens) * 2.0, 12.0)
    if kw_token_points > 0:
        score += kw_token_points
        reasons.append(f"token_overlap_keywords(+{kw_token_points})")
        for ct in common_kw_tokens:
            if ct not in matched_keywords:
                matched_keywords.append(ct)

    # 5. Token overlap with title/summary text: +0.5 each distinct token (max 3)
    text_content = f"{candidate.get('title', '')} {candidate.get('summary', '')}"
    content_tokens = set(tokenize(text_content))
    common_content_tokens = query_tokens.intersection(content_tokens) - common_kw_tokens
    content_points = min(len(common_content_tokens) * 0.5, 3.0)
    if content_points > 0:
        score += content_points
        reasons.append(f"token_overlap_content(+{content_points})")

    # 6. Graph hop: summary mentions an entity directly adjacent (1 hop) to a query entity: +2 (max 4)
    if query_adjacent_entity_ids:
        adj_points = 0.0
        for e in candidate.get("linked_entities") or []:
            if isinstance(e, dict) and e.get("id") in query_adjacent_entity_ids:
                if adj_points < 4.0:
                    adj_points = min(adj_points + 2.0, 4.0)
                    reasons.append(f"graph_hop(+{adj_points})")
                    break
        score += adj_points

    # 7. Recency tiebreak: up to +0.5
    recency = calculate_recency_score(candidate.get("created_at"))
    score += recency

    # 8. Superseded status: -3.0
    if candidate.get("status") == "superseded":
        score -= 3.0
        reasons.append("superseded_penalty(-3.0)")

    match_reason = "; ".join(reasons) if reasons else "baseline"
    return round(score, 2), matched_keywords, matched_entities, match_reason
