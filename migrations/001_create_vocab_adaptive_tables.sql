CREATE TABLE IF NOT EXISTS vocab_profiles (
  id            BIGSERIAL PRIMARY KEY,
  profile_key   TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  is_guest      BOOLEAN NOT NULL DEFAULT FALSE,
  is_default    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vocab_profiles_single_default
ON vocab_profiles ((is_default))
WHERE is_default = TRUE;

CREATE TABLE IF NOT EXISTS vocab_word_state (
  id                    BIGSERIAL PRIMARY KEY,
  profile_id            BIGINT NOT NULL REFERENCES vocab_profiles(id) ON DELETE CASCADE,
  target_word           TEXT NOT NULL,
  weight                NUMERIC(2,1) NOT NULL DEFAULT 1.0
                        CHECK (weight IN (0.5, 1.0, 2.0, 4.0)),
  consecutive_correct   INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_correct >= 0),
  last_answered_at      TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (profile_id, target_word)
);

CREATE INDEX IF NOT EXISTS idx_vocab_word_state_profile_weight
  ON vocab_word_state (profile_id, weight);

CREATE TABLE IF NOT EXISTS vocab_answer_events (
  id            BIGSERIAL PRIMARY KEY,
  profile_id    BIGINT NOT NULL REFERENCES vocab_profiles(id) ON DELETE CASCADE,
  target_word   TEXT NOT NULL,
  was_correct   BOOLEAN NOT NULL,
  submitted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  quiz_id       TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vocab_answer_events_profile_word_time
  ON vocab_answer_events (profile_id, target_word, submitted_at DESC);
