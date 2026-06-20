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
