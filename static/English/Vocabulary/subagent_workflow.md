# Vocabulary Subagent Workflow

Use this workflow whenever generating new vocabulary questions for `static/English/Vocabulary/questions.json`.

## Agent Roles

### 1. Coordinator Agent
- Run the mandatory re-balance step before every generation run.
- Back up `word_bank.txt` using the next `word_bank.txt.backup.NN` suffix.
- Remove any word from `word_bank.txt` that already appears `2` or more times as a `target_word` in `questions.json`.
- Create one assignment packet per question type with non-overlapping `target_words` and reserved IDs.
- Send every generation batch to the validator agent before merge.
- Merge only validator-approved batches back into `questions.json`.

### 2. Generation Agents
- Use one generator per question type:
  - `word_meaning`
  - `reverse_meaning`
  - `fill_in_blank`
  - `alternative_word`
  - `part_of_speech`
- Follow the local rules in `AGENTS.md` and `Question_instruction.txt`.
- Generate only for the assigned `target_words`.
- Return a raw JSON array of question objects with reserved IDs.

### 3. Shared Validator Agent
- Review each generation batch independently from the generator that produced it.
- Reject any question that fails schema, type mapping, assigned-word compliance, or single-correct-answer checks.
- Reject any question whose sentence or explanation is unclear for Year 8 learners.
- Reject any question using a blocked target from `quality_blocklist.txt`.
- For Type 4 questions, reject loose or borderline synonyms that are not clearly interchangeable in that sentence.
- Do not merge or rewrite questions directly; return a validation report to the coordinator.

## CLI Workflow

From repo root:

```bash
python3 tools/vocab_pipeline.py prepare-run \
  --count word_meaning=10 \
  --count reverse_meaning=10 \
  --count fill_in_blank=10 \
  --count alternative_word=10 \
  --count part_of_speech=10 \
  --output /tmp/vocab-assignments.json
```

Validate each subagent batch:

```bash
python3 tools/vocab_pipeline.py validate-batch \
  --assignment /tmp/vocab-assignments.json \
  --question-type word_meaning \
  --batch /tmp/word-meaning-batch.json \
  --report /tmp/word-meaning-report.json
```

Merge approved batches:

```bash
python3 tools/vocab_pipeline.py merge-batches \
  --batch /tmp/word-meaning-batch.json \
  --batch /tmp/reverse-meaning-batch.json
python3 -m json.tool static/English/Vocabulary/questions.json >/dev/null
```

## Validation Expectations
- `questions.json` stays a top-level raw JSON array.
- Every new question includes `id`, `type`, `target_word`, `prompt`, `question`, `choices`, and `explanation`.
- Every new question has exactly `5` choices and exactly `1` correct answer.
- Type-specific `question` text must match the standard template from the local instructions.
- `alternative_word` and `part_of_speech` sentences must contain the `target_word`.
- `fill_in_blank` sentences must include `______`.
- `alternative_word` explanations must justify the answer in context, not just state that it is similar.
