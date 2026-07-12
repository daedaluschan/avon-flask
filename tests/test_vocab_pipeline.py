import json
import tempfile
import unittest
from pathlib import Path

from tools import vocab_pipeline


class VocabPipelineTests(unittest.TestCase):
    def test_next_backup_path_uses_next_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            word_bank = Path(tmpdir) / "word_bank.txt"
            word_bank.write_text("alpha\n", encoding="utf-8")
            (Path(tmpdir) / "word_bank.txt.backup.01").write_text("alpha\n", encoding="utf-8")
            (Path(tmpdir) / "word_bank.txt.backup.05").write_text("alpha\n", encoding="utf-8")

            next_backup = vocab_pipeline.next_backup_path(word_bank)

            self.assertEqual(next_backup.name, "word_bank.txt.backup.06")

    def test_validate_batch_accepts_well_formed_assignment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            assignment_path = tmp / "assignments.json"
            batch_path = tmp / "batch.json"
            assignment = {
                "allocations": [
                    {
                        "question_type": "word_meaning",
                        "count": 1,
                        "reserved_ids": ["eng-vocab-0351"],
                        "target_words": ["Gorge"],
                    }
                ]
            }
            batch = [
                {
                    "id": "eng-vocab-0351",
                    "type": "word_meaning",
                    "target_word": "Gorge",
                    "prompt": {},
                    "question": 'What does "Gorge" mean?',
                    "choices": [
                        {"text": "A deep narrow valley", "correct": True},
                        {"text": "A type of tiny bird", "correct": False},
                        {"text": "A sudden loud argument", "correct": False},
                        {"text": "A heavy winter coat", "correct": False},
                        {"text": "A slippery sea plant", "correct": False},
                    ],
                    "explanation": "A gorge is a deep narrow valley, often with steep sides.",
                }
            ]
            assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
            batch_path.write_text(json.dumps(batch), encoding="utf-8")

            report = vocab_pipeline.validate_batch(batch_path, assignment_path, "word_meaning")

            self.assertTrue(report["valid"])
            self.assertEqual(report["errors"], [])

    def test_validate_batch_rejects_wrong_target_word(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            assignment_path = tmp / "assignments.json"
            batch_path = tmp / "batch.json"
            assignment = {
                "allocations": [
                    {
                        "question_type": "reverse_meaning",
                        "count": 1,
                        "reserved_ids": ["eng-vocab-0352"],
                        "target_words": ["scramble"],
                    }
                ]
            }
            batch = [
                {
                    "id": "eng-vocab-0352",
                    "type": "reverse_meaning",
                    "target_word": "moor",
                    "prompt": {"meaning": "To move quickly with little control."},
                    "question": "Which word matches the meaning given?",
                    "choices": [
                        {"text": "scramble", "correct": True},
                        {"text": "moor", "correct": False},
                        {"text": "ford", "correct": False},
                        {"text": "cease", "correct": False},
                        {"text": "stalk", "correct": False},
                    ],
                    "explanation": "Scramble means to move quickly or awkwardly.",
                }
            ]
            assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
            batch_path.write_text(json.dumps(batch), encoding="utf-8")

            report = vocab_pipeline.validate_batch(batch_path, assignment_path, "reverse_meaning")

            self.assertFalse(report["valid"])
            error_text = json.dumps(report["errors"])
            self.assertIn("not assigned", error_text)

    def test_validate_batch_rejects_weak_alternative_word_explanation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            assignment_path = tmp / "assignments.json"
            batch_path = tmp / "batch.json"
            assignment = {
                "allocations": [
                    {
                        "question_type": "alternative_word",
                        "count": 1,
                        "reserved_ids": ["eng-vocab-0357"],
                        "target_words": ["lilting"],
                    }
                ]
            }
            batch = [
                {
                    "id": "eng-vocab-0357",
                    "type": "alternative_word",
                    "target_word": "lilting",
                    "prompt": {"sentence": "The song had a lilting rhythm that made everyone smile."},
                    "question": 'Which word could best replace "lilting" without changing the meaning?',
                    "choices": [
                        {"text": "musical", "correct": True},
                        {"text": "silent", "correct": False},
                        {"text": "careless", "correct": False},
                        {"text": "dusty", "correct": False},
                        {"text": "crooked", "correct": False},
                    ],
                    "explanation": "Musical is similar to lilting.",
                }
            ]
            assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
            batch_path.write_text(json.dumps(batch), encoding="utf-8")

            report = vocab_pipeline.validate_batch(batch_path, assignment_path, "alternative_word")

            self.assertFalse(report["valid"])
            error_text = json.dumps(report["errors"])
            self.assertIn("in context", error_text)


if __name__ == "__main__":
    unittest.main()
