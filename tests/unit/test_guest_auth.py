"""Unit tests for guest authentication and quota enforcement."""

from datetime import datetime, timezone, timedelta
from graph_intelligence.remote.auth import (
    create_guest,
    validate_guest_token,
    record_session_operation,
    cleanup_expired_guests,
)


def test_create_and_validate_guest():
    ok, guest = create_guest("AliceTester", "127.0.0.1")
    assert ok is True
    assert guest["nickname"] == "AliceTester"
    assert guest["guest_id"].startswith("gst_")
    assert guest["token"].startswith("key_")
    assert guest["session_quota"] == 10

    # Validate valid token
    res = validate_guest_token(guest["token"])
    assert res["valid"] is True
    assert res["guest_id"] == guest["guest_id"]
    assert res["sessions_left"] == 10


def test_invalid_and_missing_token():
    assert validate_guest_token("")["valid"] is False
    assert validate_guest_token("non_existent_key")["valid"] is False


def test_session_operation_decrement():
    ok, guest = create_guest("BobTester", "127.0.0.1")
    assert ok is True
    token = guest["token"]
    gid = guest["guest_id"]

    # Record first operation in session 1
    record_session_operation(gid, "sess_1", "/sse")
    res1 = validate_guest_token(token)
    assert res1["sessions_used"] == 1
    assert res1["sessions_left"] == 9

    # Record second operation in the same session (does not decrement again)
    record_session_operation(gid, "sess_1", "/messages")
    res2 = validate_guest_token(token)
    assert res2["sessions_used"] == 1
    assert res2["sessions_left"] == 9

    # Record operation in a NEW session (decrements quota)
    record_session_operation(gid, "sess_2", "/sse")
    res3 = validate_guest_token(token)
    assert res3["sessions_used"] == 2
    assert res3["sessions_left"] == 8
