"""Unit tests for the daily cleanup service."""

from datetime import datetime, timezone, timedelta
from graph_intelligence.remote.auth import (
    create_guest,
    record_session_operation,
    _get_connection,
    _USE_POSTGRES,
)
from graph_intelligence.remote.cleanup import cleanup_stale_records_and_graphs


def test_cleanup_stale_guest_records():
    # 1. Create a guest user
    ok, guest = create_guest("StaleTester", "127.0.0.1")
    assert ok is True
    gid = guest["guest_id"]

    # Record an operation
    record_session_operation(gid, "sess_clean", "/sse")

    # Manually backdate created_at and expires_at to 3 days ago
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    conn = _get_connection()
    try:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute(
                "UPDATE guest_users SET created_at = %s, expires_at = %s WHERE id = %s",
                (three_days_ago, three_days_ago, gid),
            )
            cur.execute(
                "UPDATE guest_session_logs SET created_at = %s WHERE guest_id = %s",
                (three_days_ago, gid),
            )
        else:
            cur.execute(
                "UPDATE guest_users SET created_at = ?, expires_at = ? WHERE id = ?",
                (three_days_ago.isoformat(), three_days_ago.isoformat(), gid),
            )
            cur.execute(
                "UPDATE guest_session_logs SET created_at = ? WHERE guest_id = ?",
                (three_days_ago.isoformat(), gid),
            )
        conn.commit()
    finally:
        conn.close()

    # Run cleanup with 2-day threshold
    stats = cleanup_stale_records_and_graphs(days=2)
    assert gid in stats["deleted_guest_ids"]
    assert stats["deleted_guest_count"] >= 1
    assert stats["deleted_session_logs_count"] >= 1
