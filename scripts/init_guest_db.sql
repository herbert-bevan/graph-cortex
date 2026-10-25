-- Initialization schema for GraphCortex Guest Auth & Quota Engine in PostgreSQL

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

-- Fast lookup indexes
CREATE INDEX IF NOT EXISTS idx_guest_token_hash ON guest_users(api_token_hash);
CREATE INDEX IF NOT EXISTS idx_guest_expires_at ON guest_users(expires_at);
CREATE INDEX IF NOT EXISTS idx_guest_ip ON guest_users(ip_address, created_at);
CREATE INDEX IF NOT EXISTS idx_session_guest_id ON guest_session_logs(guest_id);
