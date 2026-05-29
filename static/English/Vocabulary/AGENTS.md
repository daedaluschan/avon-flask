# Vocabulary Question Authoring Instructions (Local Scope)

These instructions apply to files under `static/English/Vocabulary/`.

## Source Material
- Use `word_bank.txt` as the source of tested vocabulary words.
- Tested word (or clear derivative) must come from `word_bank.txt`.
- Distractors/synonyms can come from inside or outside the word bank.

## Output Target
- Add new questions to `questions.json` (do not replace existing questions).
- Output must follow the repository JSON schema defined in the root `AGENTS.md`.
- Top level of `questions.json` must remain a raw JSON array.

## Word Selection
- Select words randomly, preferring words used least often so far.
- Reusing the same target word is allowed when the question itself is different.
- Derived forms are allowed when clearly linked to a word-bank base word.

## Maintaining `word_bank.txt`
- When asked to add new words or phrases to `word_bank.txt`, first check whether each item already exists in the word bank using a case-insensitive comparison.
- Only append items that are not already present case-insensitively. For example, if `chasms` already exists, do not append `Chasms`.
- Whenever adding words or phrases to `word_bank.txt`, also remove any duplicate word-bank entries case-insensitively, preserving the first occurrence and original order of retained entries.
- After editing `word_bank.txt`, validate that it contains no duplicate non-empty entries case-insensitively. A short Python script using `str.casefold()` is recommended for this check.
- Keep one vocabulary item per line.

## Question Type Selection Default
- If the user does not specify question type(s), produce a mixed question set that includes a mixture of all 5 defined types.

## Supported Question Types and JSON Mapping
1. **Type 1: Word Meaning MCQ**
   - `type`: `word_meaning`
   - `target_word`: tested word
   - `prompt`: `{}`
   - `question`: `What does "<word>" mean?`

2. **Type 2: Reverse Meaning MCQ**
   - `type`: `reverse_meaning`
   - `target_word`: correct answer word
   - `prompt`: `{ "meaning": "..." }`
   - `question`: `Which word matches the meaning given?`

3. **Type 3: Fill in the Blank MCQ**
   - `type`: `fill_in_blank`
   - `target_word`: correct answer word
   - `prompt`: `{ "sentence": "...______..." }`
   - `question`: `Which word best completes the sentence?`

4. **Type 4: Alternative Word MCQ**
   - `type`: `alternative_word`
   - `target_word`: replaceable word in sentence
   - `prompt`: `{ "sentence": "..." }`
   - `question`: `Which word could best replace "<target_word>" without changing the meaning?`

5. **Type 5: Part of Speech MCQ**
   - `type`: `part_of_speech`
   - `target_word`: analysed word
   - `prompt`: `{ "sentence": "..." }`
   - `question`: `In this sentence, what part of speech is "<target_word>"?`

## MCQ Construction Rules
- Exactly 5 choices per question.
- Exactly 1 choice has `"correct": true`.
- Shuffle answer order so the correct option is not fixed to one position.
- Preserve user-provided option order only when converting from a provided plain-text MCQ set.
- Keep language suitable for Year 8 learners.

## Required Fields Per Question
Each new question object must include:
- `id` (sequential and unique, e.g. `eng-vocab-00xx`)
- `type`
- `target_word`
- `prompt`
- `question`
- `choices` (`[{"text":"...","correct":true/false}, ...]`)
- `explanation` (brief, useful reason)

## Guardrails
- Do not add `level` or `difficulty` unless schema intentionally changes.
- Do not put `target_word` inside `prompt`.
- If `target_word` cannot be inferred confidently from input, skip that question and report it.

## Validation
After editing `questions.json`, run:
- `python3 -m json.tool static/English/Vocabulary/questions.json`

## "Words Census" Procedure
When the user asks for the "words census" exercise, compute how often vocabulary words are used as `target_word` values in `questions.json`, including zero-usage words from `word_bank.txt`.

1. Load `static/English/Vocabulary/questions.json` and count occurrences of each non-empty `target_word`.
2. Load `static/English/Vocabulary/word_bank.txt`, trim whitespace, and ignore empty lines.
3. Build a unique word-bank list (de-duplicate exact duplicates while preserving first appearance order for reporting).
4. For each unique word-bank entry, look up its count from the `target_word` counts; if absent, treat as `0`.
5. Produce a histogram summary of how many word-bank entries appear `0`, `1`, `2`, `3`, ... times.
6. Report supporting totals:
   - non-empty word-bank lines
   - unique word-bank entries
   - total questions
   - unique `target_word` values in questions
   - number of `target_word` values not present in `word_bank.txt`
7. If requested, also provide:
   - the full list of zero-usage word-bank entries
   - the full list of `target_word` values that are outside `word_bank.txt`

Recommended implementation: use a short Python script with `collections.Counter` for reproducible counting.

## "Questions Re-balance" Procedure
When the user asks for "Questions Re-balance", rebalance the candidate vocabulary list so future question generation focuses on words that appear zero or one time in `questions.json`.

1. Create a backup of `word_bank.txt` using the next numeric suffix format: `word_bank.txt.backup.02`, then `.03`, `.04`, and so on (do not keep reusing `.01`).
2. Load `static/English/Vocabulary/questions.json` and count occurrences of each non-empty `target_word`.
3. Load `static/English/Vocabulary/word_bank.txt`, trim whitespace, and ignore empty lines.
4. Remove from `word_bank.txt` any word that already appears **2 or more times** as a `target_word` in `questions.json`.
5. Keep words with usage counts of `0` or `1` so future question generation is biased toward underused vocabulary.
6. Preserve one word per line and keep the original order of retained entries.
7. Report a short post-change summary with concrete counts:
   - original non-empty word-bank entries
   - retained entries
   - removed entries

Recommended implementation: use a short Python script with `collections.Counter` and perform deterministic filtering based on exact string matches.

## Database Usage for Adaptive Vocabulary (Neon/Postgres)

This project now uses PostgreSQL (Neon) for adaptive vocabulary weighting and profile-based practice behavior.

### Connection
- Database connection is provided via environment variable `DATABASE_URL`.
- `DATABASE_URL` should be the full connection string, including `sslmode=require` for Neon.
- Do not hardcode credentials in source files.

### Where DB logic is used
- Profile loading, active profile resolution, weighted sampling state lookup, and feedback persistence are handled in `app.py`.
- Question content still comes from `questions.json`; DB stores learner/profile state and answer history only.

### Schema overview
The following tables are expected:

1. `vocab_profiles`
   - One row per selectable profile (for example: `jinny`, `dd`, `guest`).
   - Important fields:
     - `profile_key` (unique profile identifier)
     - `display_name` (UI label)
     - `is_guest` (guest profile bypasses adaptive writes)
     - `is_default` (single default profile)

2. `vocab_word_state`
   - One row per `(profile_id, target_word)` adaptive state.
   - Important fields:
     - `weight` in `{0.5, 1.0, 2.0, 4.0}`
     - `consecutive_correct`
     - `last_answered_at`
   - `UNIQUE (profile_id, target_word)` ensures one state row per word per profile.

3. `vocab_answer_events`
   - Append-only event history per word outcome.
   - Important fields:
     - `profile_id`
     - `target_word`
     - `was_correct`
     - `submitted_at`
     - optional `quiz_id`

### How to rebuild schema from SQL files
From repository root:

1. Apply base schema:
   - `migrations/001_create_vocab_adaptive_tables.sql`
2. Apply baseline seed profiles:
   - `migrations/002_seed_vocab_profiles.sql`

Example:
- `psql "$DATABASE_URL" -f migrations/001_create_vocab_adaptive_tables.sql`
- `psql "$DATABASE_URL" -f migrations/002_seed_vocab_profiles.sql`

### Seed expectations
- Seeded profiles should include:
  - `jinny` (default)
  - `dd`
  - `guest`
- Do not pre-populate `vocab_word_state` for every `target_word`; state rows are created lazily on first recorded submission.
