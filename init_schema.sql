CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    church_name TEXT NOT NULL,
    pastor_name TEXT,
    phone TEXT,
    address TEXT,
    plan TEXT NOT NULL DEFAULT 'starter',
    status TEXT NOT NULL DEFAULT 'trial',
    trial_ends_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    name TEXT NOT NULL DEFAULT '',
    email TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, username)
);

CREATE TABLE IF NOT EXISTS church_info (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS church_about (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vision_title TEXT NOT NULL DEFAULT '',
    vision_content TEXT NOT NULL DEFAULT '',
    mission_content TEXT NOT NULL DEFAULT '',
    pastoral_direction TEXT NOT NULL DEFAULT '',
    serving_people TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sermons (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    pastor TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    youtube_url TEXT
);

CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    views INTEGER NOT NULL DEFAULT 0,
    author TEXT NOT NULL DEFAULT '',
    image_path TEXT
);

CREATE TABLE IF NOT EXISTS news_images (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    news_id INTEGER NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pastoral_images (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    pastoral_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS visions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    youtube_url TEXT NOT NULL,
    date TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS shorts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    youtube_url TEXT NOT NULL,
    date TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS qtys (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    youtube_url TEXT NOT NULL,
    date TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pastoral_posts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    author TEXT NOT NULL DEFAULT '',
    views INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    photo_path TEXT,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_type TEXT NOT NULL,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sermons_tenant ON sermons(tenant_id);
CREATE INDEX IF NOT EXISTS idx_news_tenant ON news(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pastoral_posts_tenant ON pastoral_posts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_comments_tenant_post ON comments(tenant_id, post_type, post_id);
CREATE INDEX IF NOT EXISTS idx_visions_tenant ON visions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_shorts_tenant ON shorts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_qtys_tenant ON qtys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_members_tenant ON members(tenant_id);

CREATE TABLE IF NOT EXISTS invite_codes (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    note TEXT DEFAULT '',
    used_at TIMESTAMP,
    used_by_tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invite_codes_code ON invite_codes(code);

CREATE TABLE IF NOT EXISTS bulletins (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    date DATE NOT NULL,
    image_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS offering_links (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'bank',
    url TEXT NOT NULL DEFAULT '',
    account_info TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bulletins_tenant ON bulletins(tenant_id);
CREATE INDEX IF NOT EXISTS idx_offering_links_tenant ON offering_links(tenant_id);

-- Phase 2: E2EE pastoral planner
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS e2ee_salt TEXT DEFAULT NULL;

CREATE TABLE IF NOT EXISTS congregation_members (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    birth_date DATE,
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    join_date DATE,
    baptism_date DATE,
    cell_group TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    last_contact_date DATE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS counseling_logs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES congregation_members(id) ON DELETE SET NULL,
    encrypted_content TEXT NOT NULL,
    iv TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS donation_receipts (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES congregation_members(id) ON DELETE SET NULL,
    member_name TEXT NOT NULL,
    amount INTEGER NOT NULL,
    year INTEGER NOT NULL,
    receipt_number TEXT,
    issued_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_congregation_tenant ON congregation_members(tenant_id);
CREATE INDEX IF NOT EXISTS idx_counseling_member ON counseling_logs(member_id);
CREATE INDEX IF NOT EXISTS idx_donations_tenant_year ON donation_receipts(tenant_id, year);

-- Billing: 교회별 정기 구독(자동결제)
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'toss',
    plan TEXT NOT NULL DEFAULT 'standard',
    amount INTEGER NOT NULL,
    -- incomplete: 결제수단 미등록 / trialing: 등록됨, 무료체험 중 / active: 정상
    -- past_due: 결제 실패 후 재시도 중 / unpaid: 재시도 모두 실패 / canceled: 해지
    status TEXT NOT NULL DEFAULT 'incomplete',
    customer_key TEXT UNIQUE NOT NULL,
    billing_key TEXT,
    payment_method TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    customer_name TEXT DEFAULT '',
    anchor_day INTEGER,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    next_billing_at TIMESTAMP,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    canceled_at TIMESTAMP,
    -- 서버에서 시작하는 등록(카카오페이) 진행 중 정보
    pending_provider TEXT,
    pending_token TEXT,
    pending_order_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscription_payments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    order_id TEXT UNIQUE NOT NULL,
    amount INTEGER NOT NULL,
    -- done / failed / unknown(네트워크 오류 등으로 결과 미확인. 토스는 같은 order_id 로 재시도, 카카오페이는 수동 확인)
    status TEXT NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    payment_key TEXT,
    failure_code TEXT,
    failure_message TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_next_billing ON subscriptions(next_billing_at) WHERE billing_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscription_payments_tenant ON subscription_payments(tenant_id, created_at DESC);

-- 교회별 사이트 설정(테마·홈 섹션·문구). 버전별로 쌓고 is_active 인 행 하나가 실제 사이트에 쓰인다.
-- source: manual(관리자 직접 수정) / catalog(테마 카탈로그 적용) / ai(Claude 설정안) / rollback
CREATE TABLE IF NOT EXISTS tenant_site_configs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    config JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_site_configs_active ON tenant_site_configs(tenant_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_tenant_site_configs_tenant ON tenant_site_configs(tenant_id, id DESC);

-- 요금제 내림 예약(다음 결제일에 적용)
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS scheduled_plan TEXT;

-- 구독 외 1회 결제(AI 맞춤 제작 셋업비 등). 등록된 자동결제 수단으로 청구한다.
-- status: done / failed / unknown(결과 미확인, 이중결제 방지를 위해 자동 재시도 안 함)
CREATE TABLE IF NOT EXISTS one_time_payments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    order_id TEXT UNIQUE NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL,
    payment_key TEXT,
    failure_code TEXT,
    failure_message TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Claude API 사용 기록(요금제별 월 사용 횟수 제한, 원가 확인)
CREATE TABLE IF NOT EXISTS ai_usage (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_tenant ON ai_usage(tenant_id, kind, created_at);

-- 프리미엄 요금제·셋업비 고객의 맞춤 제작 요청(운영자가 검수·제작)
-- status: open / in_progress / done
CREATE TABLE IF NOT EXISTS custom_requests (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    requested_by TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    admin_note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 교회 사이트 접속 로그(관리자 화면에서 누가 언제 들어왔는지 확인). created_at 은 한국시간.
-- event: page / login / login_fail / logout
CREATE TABLE IF NOT EXISTS access_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    event TEXT NOT NULL,
    user_id INTEGER,
    username TEXT,
    ip TEXT,
    method TEXT,
    path TEXT,
    status INTEGER,
    user_agent TEXT,
    is_bot BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_time ON access_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_user ON access_logs(tenant_id, user_id);
