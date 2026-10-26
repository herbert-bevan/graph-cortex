"""PostgreSQL / SQLite backed Guest Authentication & Quota Engine.

Enforces:
1. IP rate limiting (max 3 tokens / IP / hour)
2. Global concurrent guest cap (max 50 concurrent active guests)
3. Hard session quotas (10 sessions per guest)
4. 24-hour TTL expiration
"""

from datetime import datetime, timezone, timedelta
import hashlib
import os
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from graph_intelligence.common.logging_setup import get_logger

logger = get_logger("guest_auth")

DATABASE_URL = os.getenv("DATABASE_URL", "")
MAX_CONCURRENT_GUESTS = int(os.getenv("MAX_CONCURRENT_GUESTS", "50"))
GUEST_SESSION_LIMIT = int(os.getenv("GUEST_SESSION_LIMIT", "10"))
GUEST_TTL_HOURS = int(os.getenv("GUEST_TTL_HOURS", "24"))

# Check whether to use Postgres or SQLite fallback
_USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if _USE_POSTGRES:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        try:
            import psycopg2 as psycopg
            import psycopg2.extras
            dict_row = None
        except ImportError:
            _USE_POSTGRES = False

if not _USE_POSTGRES:
    import sqlite3
    SQLITE_DIR = os.getenv("SQLITE_DIR", os.path.dirname(__file__))
    os.makedirs(SQLITE_DIR, exist_ok=True)
    SQLITE_PATH = os.path.join(SQLITE_DIR, "guest_auth.db")
else:
    SQLITE_PATH = ""


def get_db_info() -> Dict[str, Any]:
    """Inspect and return runtime database connection info dynamically without hardcoding."""
    if _USE_POSTGRES:
        try:
            p = urlparse(DATABASE_URL)
            host = p.hostname or "unknown"
            port = p.port or 5432
            db_name = p.path.lstrip("/") or "unknown"
            user = p.username or "postgres"
            target = f"PostgreSQL ({user}@{host}:{port}/{db_name})"
        except Exception:
            target = "PostgreSQL (configured via DATABASE_URL)"
        return {
            "engine": "PostgreSQL",
            "target": target,
            "use_postgres": True,
            "sqlite_path": None,
        }
    else:
        return {
            "engine": "SQLite",
            "target": "SQLite (guest_auth.db)",
            "use_postgres": False,
            "sqlite_path": SQLITE_PATH,
        }


def _get_connection():
    """Return an active database connection."""
    if _USE_POSTGRES:
        conn = psycopg.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initialize database tables if they do not exist."""
    info = get_db_info()
    conn = _get_connection()
    try:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS guest_users (
                    id VARCHAR(64) PRIMARY KEY,
                    nickname VARCHAR(64) NOT NULL,
                    api_token_hash VARCHAR(128) NOT NULL UNIQUE,
                    session_quota INT NOT NULL DEFAULT 10,
                    sessions_used INT NOT NULL DEFAULT 0,
                    ip_address VARCHAR(45),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 HOURS'),
                    is_revoked BOOLEAN NOT NULL DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS guest_session_logs (
                    id VARCHAR(64) PRIMARY KEY,
                    guest_id VARCHAR(64) NOT NULL REFERENCES guest_users(id) ON DELETE CASCADE,
                    session_id VARCHAR(64) NOT NULL,
                    tool_name VARCHAR(64) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS guest_users (
                    id TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    api_token_hash TEXT NOT NULL UNIQUE,
                    session_quota INTEGER NOT NULL DEFAULT 10,
                    sessions_used INTEGER NOT NULL DEFAULT 0,
                    ip_address TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_revoked INTEGER NOT NULL DEFAULT 0
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS guest_session_logs (
                    id TEXT PRIMARY KEY,
                    guest_id TEXT NOT NULL REFERENCES guest_users(id),
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
        conn.commit()
        logger.info(f"Database schema verified: {info['target']}")
    except Exception as exc:
        logger.warning(f"Database schema verification error ({info['target']}): {exc}")
        raise
    finally:
        conn.close()


def hash_token(token: str) -> str:
    """Return SHA-256 hash of a bearer token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def create_guest(nickname: str, ip_address: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Create a guest account with session quota and expiration.
    Returns (success, result_dict).
    """
    cleaned_name = (nickname or "Guest").strip()[:32]
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=GUEST_TTL_HOURS)
    info = get_db_info()

    conn = _get_connection()
    try:
        cur = conn.cursor()

        # 1. IP Rate Limiting: Max 3 guest accounts per IP in the last 1 hour
        if ip_address and ip_address not in ("127.0.0.1", "localhost", "::1"):
            one_hour_ago = now - timedelta(hours=1)
            if _USE_POSTGRES:
                cur.execute(
                    "SELECT COUNT(*) FROM guest_users WHERE ip_address = %s AND created_at > %s",
                    (ip_address, one_hour_ago)
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM guest_users WHERE ip_address = ? AND created_at > ?",
                    (ip_address, one_hour_ago.isoformat())
                )
            ip_count = cur.fetchone()[0]
            if ip_count >= 3:
                logger.warning(
                    f"Rate limit exceeded: IP '{ip_address}' attempted to create guest '{cleaned_name}' (count={ip_count}/3 per hour)"
                )
                return False, {
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded: Maximum 3 guest tokens per hour per IP. Please use your existing token or try later."
                }

        # 2. Global Concurrent Guests Cap: Max 50 active guests
        if _USE_POSTGRES:
            cur.execute(
                "SELECT COUNT(*) FROM guest_users WHERE expires_at > %s AND is_revoked = FALSE",
                (now,)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM guest_users WHERE expires_at > ? AND is_revoked = 0",
                (now.isoformat(),)
            )
        active_count = cur.fetchone()[0]
        if active_count >= MAX_CONCURRENT_GUESTS:
            logger.warning(
                f"Capacity full: active guests ({active_count}/{MAX_CONCURRENT_GUESTS}), IP '{ip_address}', guest '{cleaned_name}' rejected"
            )
            return False, {
                "error": "capacity_full",
                "message": f"Demo capacity full ({active_count}/{MAX_CONCURRENT_GUESTS} active sessions). Please try again shortly."
            }

        # 3. Create Token and Record
        guest_id = f"gst_{secrets.token_hex(6)}"
        raw_token = f"key_{secrets.token_urlsafe(28)}"
        token_hash = hash_token(raw_token)

        if _USE_POSTGRES:
            cur.execute("""
                INSERT INTO guest_users 
                (id, nickname, api_token_hash, session_quota, sessions_used, ip_address, created_at, expires_at, is_revoked)
                VALUES (%s, %s, %s, %s, 0, %s, %s, %s, FALSE)
            """, (guest_id, cleaned_name, token_hash, GUEST_SESSION_LIMIT, ip_address, now, expires_at))
        else:
            cur.execute("""
                INSERT INTO guest_users 
                (id, nickname, api_token_hash, session_quota, sessions_used, ip_address, created_at, expires_at, is_revoked)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0)
            """, (guest_id, cleaned_name, token_hash, GUEST_SESSION_LIMIT, ip_address, now.isoformat(), expires_at.isoformat()))

        conn.commit()
        logger.info(
            f"Guest created: guest_id='{guest_id}', nickname='{cleaned_name}', ip='{ip_address}', quota={GUEST_SESSION_LIMIT}, engine='{info['engine']}'"
        )
        return True, {
            "guest_id": guest_id,
            "nickname": cleaned_name,
            "token": raw_token,
            "session_quota": GUEST_SESSION_LIMIT,
            "expires_at": expires_at.isoformat(),
            "ttl_hours": GUEST_TTL_HOURS
        }
    finally:
        conn.close()


def validate_guest_token(raw_token: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
    """Validate bearer token, check expiration and session quotas with detailed logging."""
    if not raw_token:
        logger.warning(f"Auth failed: missing token, ip='{ip_address}'")
        return {"valid": False, "reason": "missing_token"}

    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    conn = _get_connection()
    try:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute("""
                SELECT id, nickname, session_quota, sessions_used, expires_at, is_revoked
                FROM guest_users
                WHERE api_token_hash = %s
            """, (token_hash,))
        else:
            cur.execute("""
                SELECT id, nickname, session_quota, sessions_used, expires_at, is_revoked
                FROM guest_users
                WHERE api_token_hash = ?
            """, (token_hash,))
        
        row = cur.fetchone()
        if not row:
            logger.warning(f"Auth failed: invalid token, ip='{ip_address}'")
            return {"valid": False, "reason": "invalid_token"}

        if _USE_POSTGRES:
            g_id, nickname, quota, used, expires_at, revoked = row
        else:
            g_id = row["id"]
            nickname = row["nickname"]
            quota = row["session_quota"]
            used = row["sessions_used"]
            expires_at = datetime.fromisoformat(row["expires_at"])
            revoked = bool(row["is_revoked"])

        if revoked:
            logger.warning(f"Auth failed: token revoked for guest_id='{g_id}' ('{nickname}'), ip='{ip_address}'")
            return {"valid": False, "reason": "token_revoked"}

        if expires_at < now:
            logger.warning(f"Auth failed: token expired at {expires_at.isoformat()} for guest_id='{g_id}' ('{nickname}'), ip='{ip_address}'")
            return {"valid": False, "reason": "token_expired"}

        if used >= quota:
            logger.warning(
                f"Auth failed: quota exceeded for guest_id='{g_id}' ('{nickname}'), used={used}/{quota}, ip='{ip_address}'"
            )
            return {
                "valid": False,
                "reason": "quota_exceeded",
                "message": f"Guest demo limit reached ({used}/{quota} sessions). Please clone the open-source repo to continue unlimited."
            }

        return {
            "valid": True,
            "guest_id": g_id,
            "nickname": nickname,
            "session_quota": quota,
            "sessions_used": used,
            "sessions_left": quota - used
        }
    finally:
        conn.close()


def record_session_operation(guest_id: str, session_id: str, tool_name: str, ip_address: Optional[str] = None) -> None:
    """Record an operation and increment session count if it's a new session."""
    conn = _get_connection()
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc)

        # Check if session_id is already logged for this guest
        if _USE_POSTGRES:
            cur.execute(
                "SELECT COUNT(*) FROM guest_session_logs WHERE guest_id = %s AND session_id = %s",
                (guest_id, session_id)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM guest_session_logs WHERE guest_id = ? AND session_id = ?",
                (guest_id, session_id)
            )
        seen_count = cur.fetchone()[0]

        log_id = f"log_{secrets.token_hex(8)}"
        if _USE_POSTGRES:
            cur.execute("""
                INSERT INTO guest_session_logs (id, guest_id, session_id, tool_name, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (log_id, guest_id, session_id, tool_name, now))
            if seen_count == 0:
                cur.execute(
                    "UPDATE guest_users SET sessions_used = sessions_used + 1 WHERE id = %s",
                    (guest_id,)
                )
        else:
            cur.execute("""
                INSERT INTO guest_session_logs (id, guest_id, session_id, tool_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (log_id, guest_id, session_id, tool_name, now.isoformat()))
            if seen_count == 0:
                cur.execute(
                    "UPDATE guest_users SET sessions_used = sessions_used + 1 WHERE id = ?",
                    (guest_id,)
                )

        conn.commit()

        if seen_count == 0:
            logger.info(
                f"Session logged (NEW): guest_id='{guest_id}', session_id='{session_id}', path='{tool_name}', ip='{ip_address}'"
            )
        else:
            logger.info(
                f"Session activity (EXISTING): guest_id='{guest_id}', session_id='{session_id}', path='{tool_name}', ip='{ip_address}'"
            )
    finally:
        conn.close()


def cleanup_expired_guests() -> int:
    """Delete expired guest accounts and their logs."""
    conn = _get_connection()
    now = datetime.now(timezone.utc)
    try:
        cur = conn.cursor()
        if _USE_POSTGRES:
            cur.execute("DELETE FROM guest_users WHERE expires_at < %s", (now,))
        else:
            cur.execute("DELETE FROM guest_users WHERE expires_at < ?", (now.isoformat(),))
        deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
        conn.commit()
        logger.info(f"Purged {deleted} expired guest accounts from database.")
        return deleted
    finally:
        conn.close()


# Initialize database upon import
try:
    init_db()
except Exception:
    pass
