"""Integration tests for Track 3 company brain."""

import pytest
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.errors import DatabaseUnavailable
from graph_intelligence.company_brain.service import CompanyBrainService
from graph_intelligence.seed.seed_company_graph import seed_company_graph


@pytest.fixture(scope="module")
def brain_service():
    settings = get_settings()
    test_graph = settings.FALKORDB_GRAPH_TEST
    try:
        seed_company_graph(test_graph)
        return CompanyBrainService(graph_name=test_graph)
    except DatabaseUnavailable as exc:
        pytest.skip(f"FalkorDB instance not reachable: {exc}")


def test_answer_company_question_acceptance(brain_service):
    q = "Who owns PaymentService, which team are they on, why did GraphCortex choose idempotency keys, and which document supports that decision?"
    res = brain_service.answer_company_question(q)

    assert res["ok"] is True
    facts_text = " ".join([f["statement"] for f in res["facts"]])

    # Assert Maya Chen, Payments team
    assert "Maya Chen" in facts_text
    assert "Payments" in facts_text

    # Assert ADR-014 rationale
    assert any("ADR-014" in f["statement"] for f in res["facts"])

    # Assert doc-adr-014 source
    source_ids = [s["id"] for s in res["sources"]]
    assert "doc-adr-014" in source_ids


def test_get_service_brief(brain_service):
    res = brain_service.get_service_brief("PaymentService")
    assert res["ok"] is True
    assert res["service"]["name"] == "PaymentService"
    assert res["owner"]["name"] == "Maya Chen"
    assert res["owner"]["team"] == "Payments"


def test_get_decision_context(brain_service):
    res = brain_service.get_decision_context("ADR-014")
    assert res["ok"] is True
    assert res["decision"]["name"] == "ADR-014: Use idempotency keys"
    assert "idempotency keys" in res["decision"]["rationale"].lower()
    doc_ids = [d["id"] for d in res["supporting_documents"]]
    assert "doc-adr-014" in doc_ids


def test_unknown_question_reports_gaps(brain_service):
    q = "Who is the lead architect for quantum blockchain teleportation?"
    res = brain_service.answer_company_question(q)
    assert res["ok"] is True
    assert len(res["gaps"]) > 0
