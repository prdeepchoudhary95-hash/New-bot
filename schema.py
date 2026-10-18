"""Versioned schema migrations. Har migration sirf ek baar chalta hai (schema_version table se track)."""

MIGRATIONS = [
    (
        1,
        """
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE users (
    tg_id             BIGINT PRIMARY KEY,
    username          TEXT,
    first_name        TEXT NOT NULL DEFAULT '',
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    referrer_id       BIGINT REFERENCES users(tg_id) ON DELETE SET NULL,
    referral_rewarded BOOLEAN NOT NULL DEFAULT FALSE,
    joined_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    is_banned         BOOLEAN NOT NULL DEFAULT FALSE,
    balance           BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
    total_earned      BIGINT NOT NULL DEFAULT 0 CHECK (total_earned >= 0),
    total_withdrawn   BIGINT NOT NULL DEFAULT 0 CHECK (total_withdrawn >= 0),
    CONSTRAINT users_no_self_ref CHECK (referrer_id IS NULL OR referrer_id <> tg_id)
);
CREATE INDEX idx_users_referrer ON users (referrer_id);
CREATE INDEX idx_users_last_active ON users (last_active_at);

CREATE TABLE transactions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    amount        BIGINT NOT NULL CHECK (amount <> 0),
    kind          TEXT NOT NULL CHECK (kind IN (
        'referral','daily_bonus','task_reward','promo',
        'withdraw_hold','withdraw_refund','admin_credit','admin_debit')),
    ref_key       TEXT,
    note          TEXT,
    balance_after BIGINT NOT NULL CHECK (balance_after >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tx_unique_ref UNIQUE (user_id, kind, ref_key)
);
CREATE INDEX idx_tx_user ON transactions (user_id, id DESC);
CREATE INDEX idx_tx_created ON transactions (created_at DESC);

CREATE TABLE referrals (
    referred_id BIGINT PRIMARY KEY REFERENCES users(tg_id) ON DELETE RESTRICT,
    referrer_id BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    reward      BIGINT NOT NULL CHECK (reward >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT referrals_no_self CHECK (referred_id <> referrer_id)
);
CREATE INDEX idx_ref_referrer ON referrals (referrer_id, created_at);
CREATE INDEX idx_ref_created ON referrals (created_at);

CREATE TABLE daily_bonuses (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    bonus_date DATE NOT NULL,
    amount     BIGINT NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bonus_once_per_day UNIQUE (user_id, bonus_date)
);

CREATE TABLE withdrawals (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    amount      BIGINT NOT NULL CHECK (amount > 0),
    upi_id      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected','paid')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by BIGINT,
    paid_by     BIGINT
);
CREATE UNIQUE INDEX uq_withdraw_one_active ON withdrawals (user_id)
    WHERE status IN ('pending','approved');
CREATE INDEX idx_withdraw_status ON withdrawals (status, id);
CREATE INDEX idx_withdraw_user ON withdrawals (user_id, id DESC);

CREATE TABLE tasks (
    id           BIGSERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    instructions TEXT NOT NULL,
    reward       BIGINT NOT NULL CHECK (reward > 0),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE task_submissions (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    user_id     BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    reward      BIGINT NOT NULL CHECK (reward > 0),
    proof_text  TEXT,
    proof_file  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by BIGINT,
    CONSTRAINT proof_present CHECK (proof_text IS NOT NULL OR proof_file IS NOT NULL)
);
CREATE UNIQUE INDEX uq_submission_active ON task_submissions (task_id, user_id)
    WHERE status IN ('pending','approved');
CREATE INDEX idx_sub_status ON task_submissions (status, id);
CREATE INDEX idx_sub_user ON task_submissions (user_id, id DESC);

CREATE TABLE promo_codes (
    code       TEXT PRIMARY KEY,
    reward     BIGINT NOT NULL CHECK (reward > 0),
    max_uses   INTEGER CHECK (max_uses IS NULL OR max_uses > 0),
    used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    expires_at TIMESTAMPTZ,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE promo_redemptions (
    code        TEXT NOT NULL REFERENCES promo_codes(code) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE RESTRICT,
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, user_id)
);

CREATE TABLE admin_log (
    id         BIGSERIAL PRIMARY KEY,
    admin_id   BIGINT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
""",
    ),
]
