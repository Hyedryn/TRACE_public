-- Table to define the user personas
CREATE TABLE profiles (
    profile_id SMALLSERIAL PRIMARY KEY,
    profile_name VARCHAR(100) NOT NULL UNIQUE,
    persona_description TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table to store reusable, named lists of context videos for experiments
CREATE TABLE experiment_contexts (
    context_id SERIAL PRIMARY KEY,
    context_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    video_ids TEXT[] NOT NULL, -- Using a PostgreSQL array of text
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table to define a single bot "journey" or experiment
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- This single JSONB column holds the entire experiment definition,
    -- including mode, persona mix, context, max_depth, etc. for perfect reproducibility.
    experiment_config JSONB,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'running' NOT NULL -- e.g., 'running', 'completed', 'failed'
);

-- Central repository for every unique video encountered
CREATE TABLE videos (
    video_youtube_id VARCHAR(20) PRIMARY KEY,
    title TEXT,
    description TEXT,
    channel_id VARCHAR(50),
    channel_title VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    transcript TEXT,
    duration_seconds INT,
    tags TEXT[],
    category_id VARCHAR(10),
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_enriched_at TIMESTAMP WITH TIME ZONE
);

-- logs every recommendation received
CREATE TABLE recommendation_log (
    log_id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    depth INT NOT NULL,
    source_video_id VARCHAR(20) REFERENCES videos(video_youtube_id),
    recommended_video_id VARCHAR(20) NOT NULL REFERENCES videos(video_youtube_id),
    recommendation_rank SMALLINT NOT NULL,
    recommendation_source VARCHAR(20) NOT NULL,
    was_during_context BOOLEAN NOT NULL DEFAULT FALSE,
    was_selected BOOLEAN NOT NULL DEFAULT FALSE,
    justification TEXT,

    -- Traceability columns for the choice made at this depth
    profile_id_at_choice SMALLINT REFERENCES profiles(profile_id),
    choice_method VARCHAR(20), -- e.g., 'persona', 'random'

    view_count_when_recommended BIGINT,
    like_count_when_recommended BIGINT
);

-- Table for logging persona filter decisions
CREATE TABLE persona_filter_logs (
    log_id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    video_id VARCHAR(20) NOT NULL REFERENCES videos(video_youtube_id),
    was_filtered BOOLEAN NOT NULL,
    filter_justification TEXT,
    video_transcript TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- Create essential indexes for performance
CREATE INDEX idx_log_session_depth ON recommendation_log(session_id, depth);
CREATE INDEX idx_log_source_video ON recommendation_log(source_video_id);
CREATE INDEX idx_log_recommended_video ON recommendation_log(recommended_video_id);

-- A unique constraint to ensure only one video can be selected at each step of a session
CREATE UNIQUE INDEX idx_log_unique_selection ON recommendation_log(session_id, depth) WHERE was_selected = TRUE;


-- --- DEFAULT DATA ---

-- Add a default profile for testing
INSERT INTO profiles (profile_name, persona_description) VALUES (
    'Tech Enthusiast',
    'A user who is deeply interested in technology, programming, and artificial intelligence. They prefer content that is informative, technical, and in-depth. They are likely to click on videos about software development, new technologies, and AI research.'
);

-- Add a default, reusable context for testing
INSERT INTO experiment_contexts (context_name, description, video_ids) VALUES (
    'Initial Tech Exploration',
    'A set of introductory videos about general technology topics to establish a baseline history.',
    ARRAY['Sd6F2pfKJmk', 'kc1lxFImvIY', 'LO1gIZEUGSo']
);
