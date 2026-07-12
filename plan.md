# Plan: Vocabulary MCQ Pipeline with Mandatory Word-Bank Rebalance

## Summary
Use a coordinator agent, five type-specialist generation subagents, and one shared validation agent for `static/English/Vocabulary/`. Before every new question-generation run, the coordinator must perform the existing "Questions Re-balance" procedure: back up `word_bank.txt`, then remove any word that already appears `2` or more times as a `target_word` in `questions.json`. Generation then uses only the retained word bank so overused words stop receiving new questions.

The shared validator reviews each subagent batch before anything is merged. The coordinator owns preprocessing, word assignment, ID reservation, final merge, and post-merge validation.

## Key Changes
- Make re-balance a mandatory first step before every generation run.
  - Create the next backup file for `static/English/Vocabulary/word_bank.txt`
  - Count `target_word` usage from `static/English/Vocabulary/questions.json`
  - Remove any word from `word_bank.txt` whose exact word-bank entry already appears `2+` times as `target_word`
  - Preserve original order for retained entries and keep one item per line
  - Report retained and removed counts after each re-balance
- Use one coordinator agent to control the run.
  - Inputs: `word_bank.txt`, `questions.json`, local `AGENTS.md`, `Question_instruction.txt`
  - Responsibilities: run re-balance, compute current candidate pool, assign non-overlapping target words, reserve sequential IDs, collect outputs, route all batches through validation, merge accepted questions, and run final JSON validation
- Use five generation subagents with fixed question-type ownership.
  - Type 1 agent: `word_meaning`
  - Type 2 agent: `reverse_meaning`
  - Type 3 agent: `fill_in_blank`
  - Type 4 agent: `alternative_word`
  - Type 5 agent: `part_of_speech`
- Add one shared validation agent.
  - Reviews each batch independently from the generator that produced it
  - Checks schema compliance, exact type mapping, single-correct-answer rule, Year 8 suitability, assigned-word compliance, and quality of distractors/explanations
  - Rejects invalid questions rather than repairing them silently
- Define generation output strictly as JSON-ready question objects.
  - Required fields: `id`, `type`, `target_word`, `prompt`, `question`, `choices`, `explanation`
  - Exactly `5` choices and exactly `1` correct choice
  - No `level` or `difficulty`
  - `target_word` must stay canonical even if the stem uses a derived form in the sentence
- Define merge behavior.
  - Only validator-approved questions are eligible for merge
  - Coordinator appends approved items to the top-level array in `static/English/Vocabulary/questions.json`
  - Coordinator runs `python3 -m json.tool static/English/Vocabulary/questions.json` after merge

## Public Interfaces / Contracts
- Re-balance contract:
  - Input: current `word_bank.txt` and `questions.json`
  - Output: updated `word_bank.txt`, next numeric backup file, and a short summary of original, retained, and removed entry counts
- Coordinator assignment packet:
  - `question_type`, `target_words`, `starting_id`, and the local authoring rules relevant to that type
- Generator output contract:
  - Raw array of question objects only, ready for validation
- Validator output contract:
  - For each submitted question: `accept` or `reject`, plus a short reason for each rejection
- Merge contract:
  - Final `questions.json` remains a raw JSON array with unique sequential IDs

## Test Plan
- Re-balance test:
  - Confirm a new backup file is created using the next suffix
  - Confirm every retained word appears `0` or `1` times as `target_word`
  - Confirm every removed word appears `2+` times as `target_word`
- Assignment test:
  - Confirm no retained word is assigned to more than one generation subagent in the same run
  - Confirm assigned words come only from the post-rebalance `word_bank.txt`
- Validation test:
  - Every accepted question has all required fields
  - Every accepted question has exactly `5` choices and exactly `1` correct answer
  - Every accepted question matches its assigned type schema and uses an assigned `target_word`
  - Rejected questions are excluded from merge
- Merge test:
  - IDs are sequential from the current max ID onward
  - `python3 -m json.tool static/English/Vocabulary/questions.json` passes after append

## Assumptions
- Re-balance uses exact string matching between `word_bank.txt` entries and `target_word` values, consistent with the existing local instructions.
- Re-balance happens before every generation run, not only as an occasional maintenance task.
- The shared validator is separate from both the coordinator and the generation agents.
- If validation rejects a question, it is dropped from the batch unless a later run regenerates it explicitly.
