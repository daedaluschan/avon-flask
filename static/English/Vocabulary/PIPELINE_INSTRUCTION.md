# Vocabulary Question Generation Handoff

This document is the authoritative handoff for any AI agent asked to generate or maintain vocabulary questions under `static/English/Vocabulary/`.

Follow this workflow exactly. Do not ask the user to restate the process if this file is available.

## Objective

Generate high-quality Year 8 vocabulary MCQs for `static/English/Vocabulary/questions.json` using a coordinated multi-agent workflow with:

- mandatory pre-generation word-bank rebalance
- fixed generator/validator role separation
- explicit artifacts between stages
- strict merge rules

## Files and Artifacts

Primary source files:

- `static/English/Vocabulary/questions.json`
- `static/English/Vocabulary/word_bank.txt`
- `static/English/Vocabulary/quality_blocklist.txt`
- `static/English/Vocabulary/AGENTS.md`
- `static/English/Vocabulary/Question_instruction.txt`
- `static/English/Vocabulary/subagent_workflow.md`
- `tools/vocab_pipeline.py`

Generated artifacts during a run:

- assignment packet JSON, typically in `/tmp/`
  - example: `/tmp/vocab-assignments.json`
- one generator batch JSON per question type
  - example: `/tmp/alternative_word_batch.json`
- one validator report JSON per batch
  - example: `/tmp/alternative_word_report.json`
- `word_bank.txt.backup.NN`

## Non-Negotiable Rules

- Always rebalance `word_bank.txt` before generating a new question batch.
- Never generate directly from the unrebalanced word bank.
- Never assign the same target word to multiple generator agents in the same run.
- Never merge unvalidated questions into `questions.json`.
- Never auto-assign any word listed in `quality_blocklist.txt`.
- Keep `questions.json` as a top-level raw JSON array.
- Every new question must have:
  - `id`
  - `type`
  - `target_word`
  - `prompt`
  - `question`
  - `choices`
  - `explanation`
- Every new question must have exactly 5 choices and exactly 1 correct answer.
- Language must be suitable for Year 8 learners.

## Rebalance Rule

Rebalance means:

1. Back up `static/English/Vocabulary/word_bank.txt` to the next suffix:
   - `word_bank.txt.backup.06`
   - `word_bank.txt.backup.07`
   - `word_bank.txt.backup.08`
   - and so on
2. Count how many times each non-empty `target_word` appears in `questions.json`.
3. Remove from `word_bank.txt` any word that already appears 2 or more times as a `target_word`.
4. Preserve original order for retained words.
5. Keep one word per line.
6. Report:
   - original non-empty entries
   - retained entries
   - removed entries

Important:
- Under the current rule, a word used once is still eligible.
- A word becomes ineligible on the next run after it reaches 2 uses.

## Agent Arrangement

Use this exact role split.

### 1. Coordinator Agent

Responsibilities:

- read the local instructions and source files
- run mandatory rebalance
- exclude blocked words from automatic assignment
- decide requested per-type counts
- create the assignment packet
- reserve sequential IDs
- assign non-overlapping target-word lists
- collect generator outputs
- send each batch to the validator
- merge only approved batches
- run final JSON validation
- report counts and affected files

The coordinator owns process control. Generators do not self-assign words.

### 2. Generator Agents

Use one generator per question type when needed:

- `word_meaning`
- `reverse_meaning`
- `fill_in_blank`
- `alternative_word`
- `part_of_speech`

Responsibilities:

- generate only for assigned `target_words`
- use only reserved IDs
- follow local type rules exactly
- return raw JSON arrays only
- do not merge
- do not rewrite existing questions

### 3. Shared Validator Agent

Responsibilities:

- validate each batch independently from the generator that created it
- reject questions that fail schema or content checks
- return a report with pass/fail status and reasons
- never silently “fix” questions during validation
- never merge questions

## Question-Type Expectations

### Type 1: `word_meaning`

- `prompt`: `{}`
- `question`: `What does "<target_word>" mean?`

### Type 2: `reverse_meaning`

- `prompt`: `{ "meaning": "..." }`
- `question`: `Which word matches the meaning given?`
- the correct choice text must match `target_word`

### Type 3: `fill_in_blank`

- `prompt`: `{ "sentence": "...______..." }`
- `question`: `Which word best completes the sentence?`
- the sentence must contain `______`
- the sentence must not already contain the target word

### Type 4: `alternative_word`

- `prompt`: `{ "sentence": "..." }`
- `question`: `Which word could best replace "<target_word>" without changing the meaning?`
- the sentence must contain the target word
- the correct answer must be a high-confidence in-context synonym
- the correct answer must not repeat the target word
- the correct answer should not already appear in the sentence
- the explanation must justify the replacement in context

### Type 5: `part_of_speech`

- `prompt`: `{ "sentence": "..." }`
- `question`: `In this sentence, what part of speech is "<target_word>"?`
- the sentence must contain the target word
- the explanation must name the grammatical role

## Quality Guardrails

The previous weak point in the pipeline was semantic quality, especially Type 4 synonym questions. Apply these guardrails:

- skip risky or awkward targets by adding them to `quality_blocklist.txt`
- avoid borderline synonyms
- avoid unnatural sentences
- avoid tricky multi-sense words unless the sentence clearly disambiguates the intended sense
- avoid distractors that are absurdly easy or obviously unrelated
- make explanations brief but specific
- prefer concrete, clean contexts over clever wording

If a target word is technically valid but likely to produce a weak question, skip it and use another assigned word only if the coordinator explicitly reassigns it. Do not substitute targets ad hoc.

## Exact Command Workflow

Run from repo root.

### 1. Prepare the run

Example mixed batch:

```bash
python3 tools/vocab_pipeline.py prepare-run \
  --count word_meaning=2 \
  --count reverse_meaning=2 \
  --count fill_in_blank=2 \
  --count alternative_word=2 \
  --count part_of_speech=2 \
  --output /tmp/vocab-assignments.json
```

Example Type 4-only batch:

```bash
python3 tools/vocab_pipeline.py prepare-run \
  --count word_meaning=0 \
  --count reverse_meaning=0 \
  --count fill_in_blank=0 \
  --count alternative_word=5 \
  --count part_of_speech=0 \
  --output /tmp/vocab-assignments-alt.json
```

What this does:

- rebalances `word_bank.txt`
- creates the next backup file
- filters out blocked words
- assigns target words
- reserves IDs
- writes the assignment packet

### 2. Generate batch artifacts

Each generator creates one JSON array file in `/tmp/`.

Examples:

- `/tmp/word_meaning_batch.json`
- `/tmp/reverse_meaning_batch.json`
- `/tmp/fill_in_blank_batch.json`
- `/tmp/alternative_word_batch.json`
- `/tmp/part_of_speech_batch.json`

### 3. Validate each generator batch

Example:

```bash
python3 tools/vocab_pipeline.py validate-batch \
  --assignment /tmp/vocab-assignments.json \
  --question-type alternative_word \
  --batch /tmp/alternative_word_batch.json \
  --report /tmp/alternative_word_report.json
```

Do this once per non-empty batch.

### 4. Merge approved batches

Example:

```bash
python3 tools/vocab_pipeline.py merge-batches \
  --batch /tmp/word_meaning_batch.json \
  --batch /tmp/reverse_meaning_batch.json \
  --batch /tmp/fill_in_blank_batch.json \
  --batch /tmp/alternative_word_batch.json \
  --batch /tmp/part_of_speech_batch.json
```

### 5. Final validation

```bash
python3 -m json.tool static/English/Vocabulary/questions.json >/dev/null
```

## Required Reporting Back to the User

After a successful run, report:

- how many questions were added
- the ID range added
- which question types were included
- which target words were used
- rebalance summary:
  - backup file created
  - original entries
  - retained entries
  - removed entries
- whether validation passed

If the run is partial or blocked, state exactly which stage failed:

- rebalance
- assignment
- generation
- validation
- merge

## Handling Bad Questions

If the user flags a poor question:

1. inspect the exact item in `questions.json`
2. decide whether the issue is:
   - bad synonym choice
   - awkward sentence
   - ambiguous target sense
   - poor distractors
   - weak explanation
3. patch the question directly if the fix is clear
4. if the target itself is risky, add it to `quality_blocklist.txt`
5. revalidate `questions.json`

If the user requests removal of the last generated batch:

- restate the exact IDs that will be removed
- wait for explicit confirmation
- remove only those IDs
- revalidate `questions.json`
- report removed and remaining counts

## Default Operating Mode

If the user says “generate questions” and does not specify more detail:

- run the mandatory rebalance first
- use the coordinator workflow
- generate JSON-ready questions, not plain-text drafts
- validate each batch before merge
- prefer safer targets and cleaner contexts over aggressive variety

## Current Known Quality Policy

- `Chink` is blocked from automatic assignment in `quality_blocklist.txt`
- Type 4 questions require extra caution and stronger contextual reasoning
- It is better to skip a doubtful question than merge a weak one

## Reference Files to Read Before Acting

Any new AI agent should read these before generation:

- `static/English/Vocabulary/PIPELINE_INSTRUCTION.md`
- `static/English/Vocabulary/AGENTS.md`
- `static/English/Vocabulary/Question_instruction.txt`
- `static/English/Vocabulary/subagent_workflow.md`
- `tools/vocab_pipeline.py`

This should be enough context to continue the workflow without asking the user to explain it again.
