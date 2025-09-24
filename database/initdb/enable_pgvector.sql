-- This SQL script enables the pgvector extension in PostgreSQL.
-- this runs when docker-compose up is executed
CREATE EXTENSION IF NOT EXISTS vector;

-- Kieli (languages)
CREATE TABLE languages (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name_fi TEXT NOT NULL,
    name_en TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- category & keyword -pohjataulut ja käännökset
CREATE TABLE category (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
);

CREATE TABLE category_translation (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES category(id),
    language TEXT NOT NULL,
    label TEXT NOT NULL
);

CREATE TABLE keyword (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
);

CREATE TABLE keyword_translation (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keyword(id),
    language TEXT NOT NULL,
    label TEXT NOT NULL
);

-- FOR INTERVIEWS, WE COLLECT THESE INFORMATIONS FROM RSS
CREATE TABLE news_contacts (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER REFERENCES canonical_news(id) ON DELETE CASCADE,
    
    name VARCHAR(255),
    title VARCHAR(255),
    organization VARCHAR(255),
    
    phone VARCHAR(50),
    email VARCHAR(255),
    
    contact_type VARCHAR(50) DEFAULT 'spokesperson', -- spokesperson, expert, decision_maker, media_contact
    extraction_context TEXT, -- missä kohtaa alkuperäistä tekstiä löytyi
    is_primary_contact BOOLEAN DEFAULT false,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- MAIN NEWS TABLE
CREATE TABLE canonical_news (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    source_name TEXT,
    source_url TEXT,
    content_hash TEXT UNIQUE,
    content_embedding VECTOR(384),
    published_at TIMESTAMP WITH TIME ZONE, -- When the article was published
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), -- When the article was created in the system
    language TEXT,
    article_type TEXT
);

-- REFERENCES to canonical_news table
CREATE TABLE news_sources (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    source_name TEXT,
    source_url TEXT NOT NULL,
    original_guid TEXT,
    published_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT uq_source_url UNIQUE (source_url),
    article_type TEXT
);

-- Article, used for website to show the news articles
CREATE TABLE news_article (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    version INTEGER,
    lead TEXT,
    summary TEXT,
    status TEXT,
    location_tags JSONB,
    sources JSONB,
    interviews JSONB,
    review_status TEXT,
    author TEXT,
    embedding VECTOR(384),
    body_blocks JSONB,
    enrichment_status VARCHAR(24) DEFAULT 'pending',
    markdown_content TEXT,  -- Alkuperäinen markdown-sisältö kokonaisuutena
    featured BOOLEAN DEFAULT FALSE,  -- Whether this article should be featured on front page
    published_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    original_article_type TEXT DEFAULT NULL,
    interview_decision BOOLEAN DEFAULT FALSE,  -- Whether this article has been interviewed
    required_corrections BOOLEAN DEFAULT FALSE,  -- Whether this article required corrections after review
    revision_count INTEGER DEFAULT 0,  -- Number of times this article has been revised
    categories TEXT[]
    hero_image_url TEXT, -- URL for main image
);

-- EDITOR IN CHIEF NEED TO DECIDE DO WE NEED INTERVIEW... and is it via phone or email
-- IF WE NEED INTERVIEW, WE ALSO NEED QUESTIONS TO ASK
CREATE TABLE editorial_interview_decisions (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    article_id INTEGER REFERENCES news_article(id) ON DELETE CASCADE,
    
    -- PÄÄTOIMITTAJAN PÄÄTÖS (korkean tason)
    interview_needed BOOLEAN NOT NULL,
    interview_method VARCHAR(10), -- 'phone' tai 'email'
    
    -- Yleinen suunta haastattelulle
    target_expertise_areas JSONB, -- ["AI-asiantuntemus", "startup-kokemus", "sääntelyasiat"]
    interview_focus TEXT, -- "Riippumaton näkökulma tiedotteeseen", "Asiantuntija-analyysi"
    
    -- Päätöksen perustelu
    justification TEXT NOT NULL,
    article_type_influence TEXT, -- Miten article_type vaikutti päätökseen
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(canonical_news_id)
);


-- Kategoria- ja avainsanaliitostaulut
CREATE TABLE news_article_category (
    category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    PRIMARY KEY (category_id, article_id)
);

CREATE TABLE news_article_keyword (
    keyword_id INTEGER NOT NULL REFERENCES keyword(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    PRIMARY KEY (keyword_id, article_id)
);

-- EMAIL INTERVIEWS
CREATE TABLE email_interview (
    id SERIAL PRIMARY KEY,
    news_article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    interview_decision_id INTEGER REFERENCES editorial_interview_decisions(id),
    message_id TEXT,
    recipient TEXT,
    subject TEXT,
    sent_at TIMESTAMP,
    status TEXT
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE email_replies (
    id SERIAL PRIMARY KEY,
    uid TEXT,
    email_id INTEGER NOT NULL REFERENCES email_interview(id) ON DELETE CASCADE,
    from_address TEXT,
    in_reply_to TEXT,
    body TEXT,
    received_at TIMESTAMP
);

CREATE TABLE email_questions (
    id SERIAL PRIMARY KEY,
    email_id INTEGER NOT NULL REFERENCES email_interview(id) ON DELETE CASCADE,
    topic TEXT,
    question TEXT,
    position INTEGER
);

-- PHONE INTERVIEWS
CREATE TABLE phone_interview (
    id SERIAL PRIMARY KEY,
    news_article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    interview_decision_id INTEGER REFERENCES editorial_interview_decisions(id),
    to_number TEXT,
    from_number TEXT,
    transcript_json JSONB, -- THIS IS THE ANSWERS FROM DONE INTERVIEW
    status TEXT, -- WHEN INTERVIEW DONE -- THIS SHOULD BE DONE
    created_at TIMESTAMP DEFAULT now(),
    phone_script_json JSONB, -- THIS IS THE INTERVIEW WE ARE GOING TO DO
);

CREATE TABLE phone_interview_attempt (
    id SERIAL PRIMARY KEY,
    phone_interview_id INTEGER NOT NULL REFERENCES phone_interview(id) ON DELETE CASCADE,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT
);

-- FEED CATEGORIES 
CREATE TYPE feed_category AS ENUM (
    'press_release',
    'news',
    'blog',
    'event',
    'decision',
    'other'
);

-- RRS FEEDS! IF we have many feeds, maybe use this rather than file...
CREATE TABLE news_feeds (
    id SERIAL PRIMARY KEY,
    name TEXT,
    extra_info TEXT,
    feed_type TEXT NOT NULL,
    category feed_category NOT NULL,
    origin TEXT,
    url TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT now(),
    modified_at TIMESTAMP DEFAULT now()
);

-- TABLES FOR EDITOR IN CHIEF
CREATE TABLE editorial_reviews (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES news_article(id),  -- Changed to INTEGER and proper reference
    review_data JSONB NOT NULL,        -- Full ReviewedNewsItem as JSON
    status VARCHAR(20) NOT NULL,       -- OK, ISSUES_FOUND, RECONSIDERATION
    reviewer VARCHAR(100) NOT NULL,    -- From editorial_reasoning.reviewer
    initial_decision VARCHAR(10) NOT NULL,  -- ACCEPT, REJECT
    final_decision VARCHAR(10),        -- ACCEPT, REJECT (after reconsideration)
    has_warning BOOLEAN DEFAULT FALSE, -- True if editorial_warning exists
    featured BOOLEAN DEFAULT FALSE,    -- NEW: Whether this article should be featured on front page
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    interview_decision JSONB NOT NULL,  -- JSONB to store interview decision details
    
    
    -- One review per article
    UNIQUE(article_id)
);

-- Optional: Separate table for quick issue lookup
CREATE TABLE editorial_issues (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES editorial_reviews(article_id),
    issue_type VARCHAR(20) NOT NULL,  -- Legal, Accuracy, Ethics, Style, Other
    location TEXT NOT NULL,
    description TEXT NOT NULL,
    suggestion TEXT NOT NULL
);

-- Optional: Table for tracking reasoning steps
CREATE TABLE editorial_reasoning_steps (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES editorial_reviews(article_id),
    step_id INTEGER NOT NULL,
    action VARCHAR(255) NOT NULL,
    observation TEXT NOT NULL,
    result VARCHAR(10) NOT NULL,  -- PASS, FAIL, INFO
    is_reconsideration BOOLEAN DEFAULT FALSE
);

-- EDIT IN CHIEF AGENT PROMPT FRAGMENTS
-- PROMPT MANAGEMENT SYSTEM
-- Eettiset persoonat (core personas)
CREATE TABLE prompt_ethical_personas (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    content TEXT NOT NULL,
    is_system BOOLEAN DEFAULT false, -- TRUE = ei voi poistaa
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE TABLE prompt_fragments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    content TEXT NOT NULL,
    is_system BOOLEAN DEFAULT false, -- TRUE = ei voi poistaa
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- EDIT IN CHIEF AGENT PROMPTS
-- Mikä on pääpersoona (prompt_ethical_personas) 
-- Prompt-kokoonpanot (mitkä fragmentit, missä järjestyksessä)
CREATE TABLE prompt_compositions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    ethical_persona_id INTEGER REFERENCES prompt_ethical_personas(id),
    fragment_ids INTEGER[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Varmista että vain yksi kokoonpano on aktiivinen kerrallaan
CREATE UNIQUE INDEX idx_one_active_composition 
ON prompt_compositions(is_active) WHERE is_active = true;

-- Indeksit prompt management -tauluille
CREATE INDEX idx_prompt_fragments_name ON prompt_fragments(name);
CREATE INDEX idx_prompt_compositions_active ON prompt_compositions(is_active);
CREATE INDEX idx_prompt_compositions_name ON prompt_compositions(name);

-- INDEXES
CREATE INDEX idx_status ON editorial_reviews(status);
CREATE INDEX idx_created_at ON editorial_reviews(created_at);
CREATE INDEX idx_final_decision ON editorial_reviews(final_decision);
CREATE INDEX idx_featured ON editorial_reviews(featured);  -- Index for featured articles in editorial_reviews
CREATE INDEX idx_news_article_featured ON news_article(featured);  -- NEW: Index for featured articles in news_article
CREATE INDEX idx_article_id_issues ON editorial_issues(article_id);
CREATE INDEX idx_issue_type ON editorial_issues(issue_type);
CREATE INDEX idx_article_id_reasoning ON editorial_reasoning_steps(article_id);
CREATE INDEX idx_step_id ON editorial_reasoning_steps(step_id);

-- FOR CATEGORIES
CREATE INDEX idx_news_article_categories ON news_article USING GIN(categories);

-- INTERVIEW DECISION INDEXES
CREATE INDEX idx_interview_decisions_canonical_news ON editorial_interview_decisions(canonical_news_id);
CREATE INDEX idx_interview_decisions_needed ON editorial_interview_decisions(interview_needed);

-- INTERVIEW EXECUTION INDEXES
CREATE INDEX idx_email_interview_decision ON email_interview(interview_decision_id);
CREATE INDEX idx_phone_interview_decision ON phone_interview(interview_decision_id);
CREATE INDEX idx_email_interview_status ON email_interview(status);
CREATE INDEX idx_phone_interview_status ON phone_interview(status);