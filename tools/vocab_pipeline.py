#!/usr/bin/env python3
"""Coordinator tooling for vocabulary question authoring."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
VOCAB_DIR = REPO_ROOT / "static" / "English" / "Vocabulary"
QUESTIONS_PATH = VOCAB_DIR / "questions.json"
WORD_BANK_PATH = VOCAB_DIR / "word_bank.txt"
QUALITY_BLOCKLIST_PATH = VOCAB_DIR / "quality_blocklist.txt"

QUESTION_TYPES = {
    "word_meaning": {
        "prompt_keys": set(),
        "question_template": lambda target: f'What does "{target}" mean?',
    },
    "reverse_meaning": {
        "prompt_keys": {"meaning"},
        "question_template": lambda target: "Which word matches the meaning given?",
    },
    "fill_in_blank": {
        "prompt_keys": {"sentence"},
        "question_template": lambda target: "Which word best completes the sentence?",
    },
    "alternative_word": {
        "prompt_keys": {"sentence"},
        "question_template": (
            lambda target: f'Which word could best replace "{target}" without changing the meaning?'
        ),
    },
    "part_of_speech": {
        "prompt_keys": {"sentence"},
        "question_template": (
            lambda target: f'In this sentence, what part of speech is "{target}"?'
        ),
    },
}
DEFAULT_TYPE_ORDER = [
    "word_meaning",
    "reverse_meaning",
    "fill_in_blank",
    "alternative_word",
    "part_of_speech",
]
ID_PATTERN = re.compile(r"^eng-vocab-(\d+)$")


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Vocabulary question bank must be a JSON array.")
    return data


def load_word_bank(path: Path = WORD_BANK_PATH) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_quality_blocklist(path: Path = QUALITY_BLOCKLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip().casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def count_target_words(questions: Iterable[dict]) -> Counter:
    counter: Counter[str] = Counter()
    for question in questions:
        target = question.get("target_word")
        if isinstance(target, str) and target.strip():
            counter[target.strip()] += 1
    return counter


def format_question_id(number: int) -> str:
    return f"eng-vocab-{number:04d}"


def parse_question_id(question_id: str) -> int:
    match = ID_PATTERN.fullmatch(question_id)
    if not match:
        raise ValueError(f"Invalid question id: {question_id}")
    return int(match.group(1))


def next_question_number(questions: Iterable[dict]) -> int:
    highest = 0
    for question in questions:
        question_id = question.get("id")
        if not isinstance(question_id, str):
            continue
        match = ID_PATTERN.fullmatch(question_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def next_backup_path(word_bank_path: Path = WORD_BANK_PATH) -> Path:
    pattern = re.compile(re.escape(word_bank_path.name) + r"\.backup\.(\d+)$")
    highest = 0
    for candidate in word_bank_path.parent.iterdir():
        match = pattern.fullmatch(candidate.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return word_bank_path.with_name(f"{word_bank_path.name}.backup.{highest + 1:02d}")


def rebalance_word_bank(
    questions_path: Path = QUESTIONS_PATH,
    word_bank_path: Path = WORD_BANK_PATH,
) -> dict:
    questions = load_questions(questions_path)
    usage = count_target_words(questions)
    original_words = load_word_bank(word_bank_path)
    retained_words = [word for word in original_words if usage[word] < 2]

    backup_path = next_backup_path(word_bank_path)
    shutil.copyfile(word_bank_path, backup_path)

    new_content = ""
    if retained_words:
        new_content = "\n".join(retained_words) + "\n"
    word_bank_path.write_text(new_content, encoding="utf-8")

    return {
        "backup_path": str(backup_path.relative_to(REPO_ROOT)),
        "original_non_empty_entries": len(original_words),
        "retained_entries": len(retained_words),
        "removed_entries": len(original_words) - len(retained_words),
    }


def parse_count_arguments(raw_counts: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_count in raw_counts:
        if "=" not in raw_count:
            raise ValueError(f"Invalid count '{raw_count}'. Use question_type=count.")
        question_type, raw_value = raw_count.split("=", 1)
        question_type = question_type.strip()
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"Unsupported question type: {question_type}")
        try:
            count = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid count '{raw_count}'.") from exc
        if count < 0:
            raise ValueError("Counts must be non-negative.")
        counts[question_type] = count

    missing = [question_type for question_type in DEFAULT_TYPE_ORDER if question_type not in counts]
    if missing:
        raise ValueError(
            "Missing counts for question types: " + ", ".join(missing)
        )
    return counts


def build_assignment_packet(counts: dict[str, int], seed: int) -> dict:
    questions = load_questions()
    available_words = load_word_bank()
    blocked_words = load_quality_blocklist()
    safe_words = [word for word in available_words if word.casefold() not in blocked_words]
    total_requested = sum(counts.values())
    if total_requested > len(safe_words):
        raise ValueError(
            f"Requested {total_requested} target words but only {len(safe_words)} safe words remain after re-balance."
        )

    shuffled_words = list(safe_words)
    random.Random(seed).shuffle(shuffled_words)

    next_id = next_question_number(questions)
    cursor = 0
    allocations = []
    for question_type in DEFAULT_TYPE_ORDER:
        count = counts[question_type]
        target_words = shuffled_words[cursor : cursor + count]
        reserved_ids = [
            format_question_id(next_id + index) for index in range(count)
        ]
        allocations.append(
            {
                "question_type": question_type,
                "count": count,
                "starting_id": reserved_ids[0] if reserved_ids else None,
                "reserved_ids": reserved_ids,
                "target_words": target_words,
            }
        )
        cursor += count
        next_id += count

    return {
        "question_bank": str(QUESTIONS_PATH.relative_to(REPO_ROOT)),
        "word_bank": str(WORD_BANK_PATH.relative_to(REPO_ROOT)),
        "quality_blocklist": str(QUALITY_BLOCKLIST_PATH.relative_to(REPO_ROOT)),
        "seed": seed,
        "blocked_words_count": len(blocked_words),
        "allocations": allocations,
    }


def validate_question(question: dict, expected_type: str, allowed_ids: set[str], allowed_targets: set[str]) -> list[str]:
    errors: list[str] = []
    required_fields = {
        "id",
        "type",
        "target_word",
        "prompt",
        "question",
        "choices",
        "explanation",
    }
    missing = sorted(required_fields - question.keys())
    if missing:
        return [f"Missing fields: {', '.join(missing)}"]

    question_id = question["id"]
    if not isinstance(question_id, str) or not ID_PATTERN.fullmatch(question_id):
        errors.append("Question id must match eng-vocab-XXXX.")
    elif allowed_ids and question_id not in allowed_ids:
        errors.append(f"Question id {question_id} is outside the reserved range.")

    target_word = question["target_word"]
    if not isinstance(target_word, str) or not target_word.strip():
        errors.append("target_word must be a non-empty string.")
    elif allowed_targets and target_word not in allowed_targets:
        errors.append(f"target_word '{target_word}' is not assigned to this batch.")
    blocked_words = load_quality_blocklist()
    if isinstance(target_word, str) and target_word.casefold() in blocked_words:
        errors.append(f"target_word '{target_word}' is blocked for quality review.")

    question_type = question["type"]
    if question_type != expected_type:
        errors.append(f"type must be {expected_type}.")

    prompt = question["prompt"]
    if not isinstance(prompt, dict):
        errors.append("prompt must be an object.")
    else:
        expected_keys = QUESTION_TYPES[expected_type]["prompt_keys"]
        actual_keys = set(prompt.keys())
        if actual_keys != expected_keys:
            errors.append(
                f"prompt keys must be {sorted(expected_keys)} for {expected_type}."
            )
        if "meaning" in expected_keys and not isinstance(prompt.get("meaning"), str):
            errors.append("prompt.meaning must be a string.")
        if "sentence" in expected_keys and not isinstance(prompt.get("sentence"), str):
            errors.append("prompt.sentence must be a string.")
        if expected_type == "fill_in_blank" and isinstance(prompt.get("sentence"), str):
            if "______" not in prompt["sentence"]:
                errors.append("Fill-in-the-blank sentence must contain ______.")
        if expected_type in {"alternative_word", "part_of_speech"} and isinstance(prompt.get("sentence"), str):
            if isinstance(target_word, str) and target_word.lower() not in prompt["sentence"].lower():
                errors.append("Sentence must contain the target word.")

    question_text = question["question"]
    if not isinstance(question_text, str) or not question_text.strip():
        errors.append("question must be a non-empty string.")
    elif isinstance(target_word, str) and question_text != QUESTION_TYPES[expected_type]["question_template"](target_word):
        errors.append("question text does not match the expected template.")

    explanation = question["explanation"]
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append("explanation must be a non-empty string.")

    choices = question["choices"]
    if not isinstance(choices, list) or len(choices) != 5:
        errors.append("choices must contain exactly 5 entries.")
    else:
        correct_count = 0
        seen_texts: set[str] = set()
        for index, choice in enumerate(choices, start=1):
            if not isinstance(choice, dict):
                errors.append(f"Choice {index} must be an object.")
                continue
            text = choice.get("text")
            correct = choice.get("correct")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"Choice {index} text must be a non-empty string.")
            else:
                key = text.strip().casefold()
                if key in seen_texts:
                    errors.append("Choice texts must be unique within a question.")
                seen_texts.add(key)
            if not isinstance(correct, bool):
                errors.append(f"Choice {index} correct flag must be boolean.")
            elif correct:
                correct_count += 1
        if correct_count != 1:
            errors.append("Each question must have exactly one correct choice.")
        else:
            correct_choice = next(choice["text"] for choice in choices if choice.get("correct") is True)
            if expected_type == "alternative_word":
                if correct_choice.strip().casefold() == target_word.strip().casefold():
                    errors.append("Alternative-word answer must not repeat the target word.")
                sentence = prompt.get("sentence", "") if isinstance(prompt, dict) else ""
                if isinstance(sentence, str) and correct_choice.strip().casefold() in sentence.casefold():
                    errors.append("Alternative-word correct choice should not already appear in the sentence.")
                if len(correct_choice.split()) > 3:
                    errors.append("Alternative-word correct choice should be a concise synonym.")
            if expected_type == "reverse_meaning":
                if correct_choice.strip().casefold() != target_word.strip().casefold():
                    errors.append("Reverse-meaning correct choice must match target_word.")
            if expected_type == "fill_in_blank":
                sentence = prompt.get("sentence", "") if isinstance(prompt, dict) else ""
                if isinstance(sentence, str) and target_word.strip().casefold() in sentence.casefold():
                    errors.append("Fill-in-the-blank sentence should not already contain the target word.")

    if expected_type == "alternative_word" and isinstance(explanation, str):
        lower_explanation = explanation.casefold()
        if "context" not in lower_explanation and "sentence" not in lower_explanation:
            errors.append("Alternative-word explanation must justify the synonym in context.")
    if expected_type == "part_of_speech" and isinstance(explanation, str):
        lower_explanation = explanation.casefold()
        if not any(part in lower_explanation for part in ["noun", "verb", "adjective", "adverb", "preposition", "conjunction", "interjection"]):
            errors.append("Part-of-speech explanation must name the grammatical role.")

    return errors


def validate_batch(batch_path: Path, assignment_path: Path, question_type: str) -> dict:
    if question_type not in QUESTION_TYPES:
        raise ValueError(f"Unsupported question type: {question_type}")

    assignments = json.loads(assignment_path.read_text(encoding="utf-8"))
    allocation = None
    for candidate in assignments.get("allocations", []):
        if candidate.get("question_type") == question_type:
            allocation = candidate
            break
    if allocation is None:
        raise ValueError(f"No allocation found for {question_type}.")

    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(batch, list):
        raise ValueError("Batch file must contain a JSON array.")

    allowed_ids = set(allocation.get("reserved_ids", []))
    allowed_targets = set(allocation.get("target_words", []))
    errors: list[dict] = []
    seen_ids: set[str] = set()

    if len(batch) != allocation.get("count"):
        errors.append(
            {
                "question_index": None,
                "id": None,
                "errors": [
                    f"Batch contains {len(batch)} questions but allocation expects {allocation.get('count')}."
                ],
            }
        )

    for index, question in enumerate(batch, start=1):
        if not isinstance(question, dict):
            errors.append(
                {
                    "question_index": index,
                    "id": None,
                    "errors": ["Question entry must be an object."],
                }
            )
            continue
        question_id = question.get("id")
        question_errors = validate_question(question, question_type, allowed_ids, allowed_targets)
        if isinstance(question_id, str):
            if question_id in seen_ids:
                question_errors.append(f"Duplicate id within batch: {question_id}")
            seen_ids.add(question_id)
        errors.extend(
            {
                "question_index": index,
                "id": question_id,
                "errors": question_errors,
            }
            for question_errors in [question_errors]
            if question_errors
        )

    missing_ids = sorted(allowed_ids - seen_ids, key=parse_question_id)
    if missing_ids:
        errors.append(
            {
                "question_index": None,
                "id": None,
                "errors": ["Missing reserved ids: " + ", ".join(missing_ids)],
            }
        )

    return {
        "batch_path": str(batch_path),
        "question_type": question_type,
        "valid": not errors,
        "validated_count": len(batch),
        "errors": errors,
    }


def merge_batches(batch_paths: list[Path], questions_path: Path = QUESTIONS_PATH) -> dict:
    existing_questions = load_questions(questions_path)
    existing_ids = {question.get("id") for question in existing_questions if isinstance(question.get("id"), str)}
    new_questions: list[dict] = []
    new_ids: set[str] = set()

    for batch_path in batch_paths:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if not isinstance(batch, list):
            raise ValueError(f"Batch {batch_path} must be a JSON array.")
        for question in batch:
            question_id = question.get("id")
            if not isinstance(question_id, str):
                raise ValueError(f"Question in {batch_path} is missing a string id.")
            if question_id in existing_ids:
                raise ValueError(f"Question id {question_id} already exists in questions.json.")
            if question_id in new_ids:
                raise ValueError(f"Question id {question_id} appears in more than one batch.")
            new_ids.add(question_id)
            new_questions.append(question)

    sorted_new_questions = sorted(new_questions, key=lambda item: parse_question_id(item["id"]))
    expected_number = next_question_number(existing_questions)
    for question in sorted_new_questions:
        actual_number = parse_question_id(question["id"])
        if actual_number != expected_number:
            raise ValueError(
                f"Expected next question id {format_question_id(expected_number)} but found {question['id']}."
            )
        expected_number += 1

    merged_questions = existing_questions + sorted_new_questions
    questions_path.write_text(json.dumps(merged_questions, indent=2) + "\n", encoding="utf-8")
    return {
        "merged_count": len(sorted_new_questions),
        "new_total": len(merged_questions),
    }


def cmd_rebalance(args: argparse.Namespace) -> int:
    summary = rebalance_word_bank()
    print(json.dumps(summary, indent=2))
    return 0


def cmd_prepare_run(args: argparse.Namespace) -> int:
    counts = parse_count_arguments(args.count)
    rebalance_summary = rebalance_word_bank()
    packet = build_assignment_packet(counts, args.seed)
    packet["rebalance_summary"] = rebalance_summary
    output_path = Path(args.output)
    output_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "allocations": len(packet["allocations"])}, indent=2))
    return 0


def cmd_validate_batch(args: argparse.Namespace) -> int:
    report = validate_batch(Path(args.batch), Path(args.assignment), args.question_type)
    report_path = Path(args.report) if args.report else None
    rendered = json.dumps(report, indent=2)
    if report_path:
        report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["valid"] else 1


def cmd_merge_batches(args: argparse.Namespace) -> int:
    summary = merge_batches([Path(batch) for batch in args.batch])
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vocabulary authoring pipeline utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rebalance_parser = subparsers.add_parser("rebalance", help="Back up and prune the word bank.")
    rebalance_parser.set_defaults(func=cmd_rebalance)

    prepare_parser = subparsers.add_parser(
        "prepare-run",
        help="Re-balance the word bank and create subagent assignment packets.",
    )
    prepare_parser.add_argument(
        "--count",
        action="append",
        required=True,
        help="Per-type allocation in the form question_type=count.",
    )
    prepare_parser.add_argument(
        "--seed",
        type=int,
        default=8,
        help="Random seed used to shuffle retained words before assignment.",
    )
    prepare_parser.add_argument(
        "--output",
        required=True,
        help="Where to write the assignment packet JSON.",
    )
    prepare_parser.set_defaults(func=cmd_prepare_run)

    validate_parser = subparsers.add_parser(
        "validate-batch",
        help="Validate a generation batch against its assignment packet.",
    )
    validate_parser.add_argument("--batch", required=True, help="Path to the batch JSON file.")
    validate_parser.add_argument(
        "--assignment",
        required=True,
        help="Path to the assignment packet JSON file.",
    )
    validate_parser.add_argument(
        "--question-type",
        required=True,
        choices=DEFAULT_TYPE_ORDER,
        help="Question type handled by this batch.",
    )
    validate_parser.add_argument(
        "--report",
        help="Optional path for the validation report JSON.",
    )
    validate_parser.set_defaults(func=cmd_validate_batch)

    merge_parser = subparsers.add_parser(
        "merge-batches",
        help="Append validated batches into questions.json.",
    )
    merge_parser.add_argument(
        "--batch",
        action="append",
        required=True,
        help="Batch JSON file to merge. Provide once per validated batch.",
    )
    merge_parser.set_defaults(func=cmd_merge_batches)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
