import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.answers import Answers, Resolver
from lumen_installer.errors import InvalidInputError


class AnswersTests(unittest.TestCase):
    def test_loads_version_one_nested_answers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "answers.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "answers": {"timezone": "UTC", "uid": 1000},
                    }
                ),
                encoding="utf-8",
            )

            answers = Answers.load(path)

        self.assertEqual(answers.schema_version, 1)
        self.assertEqual(answers.get("timezone"), "UTC")
        self.assertEqual(answers.get("uid"), 1000)

    def test_rejects_invalid_json_and_unknown_schema_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                Answers.load(invalid)

            version = Path(temporary) / "version.json"
            version.write_text(
                json.dumps({"schema_version": 2, "answers": {}}),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError):
                Answers.load(version)

            numeric_version = Path(temporary) / "numeric-version.json"
            numeric_version.write_text(
                json.dumps({"schema_version": 1.0, "answers": {}}),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError):
                Answers.load(numeric_version)

    def test_resolver_uses_cli_environment_answers_then_prompt(self):
        answers = Answers(1, {"setting": "from-answers"})
        resolver = Resolver()

        self.assertEqual(
            resolver.get(
                "setting",
                {"setting": "from-cli"},
                {"LUMEN_SETTING": "from-env"},
                answers,
                lambda name: "from-prompt",
            ),
            "from-cli",
        )
        self.assertEqual(
            resolver.get(
                "setting",
                {},
                {"LUMEN_SETTING": "from-env"},
                answers,
                lambda name: "from-prompt",
            ),
            "from-env",
        )
        self.assertEqual(
            resolver.get("setting", {}, {}, answers, lambda name: "from-prompt"),
            "from-answers",
        )
        self.assertEqual(
            resolver.get("missing", {}, {}, {}, lambda name: "from-prompt"),
            "from-prompt",
        )

    def test_resolver_accepts_case_insensitive_answer_keys(self):
        answers = Answers(1, {"root_path": "/srv/media", "Downloads_Path": "/srv/downloads"})
        resolver = Resolver(noninteractive=True)

        self.assertEqual(resolver.get("ROOT_PATH", {}, {}, answers, None), "/srv/media")
        self.assertEqual(resolver.get("DOWNLOADS_PATH", {}, {}, answers, None), "/srv/downloads")

    def test_secret_answer_resolves_only_an_environment_reference(self):
        secret = "do-not-put-this-in-a-report"
        answers = Answers(1, {"password": {"env": "QBT_PASSWORD"}})
        resolver = Resolver()

        self.assertEqual(
            resolver.get(
                "password",
                {},
                {"QBT_PASSWORD": secret},
                answers,
                None,
            ),
            secret,
        )
        report = resolver.last_report
        self.assertEqual(report["name"], "password")
        self.assertEqual(report["source"], "answers")
        self.assertEqual(report["environment_variable"], "QBT_PASSWORD")
        self.assertNotIn(secret, repr(report))
        self.assertNotIn("value", report)

    def test_secret_answer_cannot_be_stored_as_a_plain_json_value(self):
        resolver = Resolver()

        with self.assertRaises(InvalidInputError):
            resolver.get(
                "password",
                {},
                {},
                Answers(1, {"password": "inline-secret"}),
                None,
            )

    def test_noninteractive_missing_required_value_is_invalid_input(self):
        resolver = Resolver(noninteractive=True)

        with self.assertRaises(InvalidInputError) as context:
            resolver.get("required", {}, {}, {}, lambda name: "should-not-run")

        self.assertEqual(context.exception.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
