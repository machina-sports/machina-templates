"""CLI contract tests for the Design Log 030 shadow maintenance pilot.

Run from the repository root:

    python3 tests/test_maintenance_contract.py -v
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDITOR = REPO_ROOT / "scripts/audit-maintenance-contract.py"
CONTRACT = REPO_ROOT / ".machina/maintenance.json"
BASE_SHA = "3a020f67b43aea2babf3c1808f2e89659d100bc8"
PILOT_CONTEXT = {
    "selected_by": "Andre",
    "selected_at": "2026-08-14",
    "reviewed_at_base_sha": BASE_SHA,
    "active_conflict": False,
}
REQUIRED_EVIDENCE_FIELDS = [
    "argv",
    "base_sha",
    "duration",
    "exit_code",
    "interpreter",
    "normalized_failure_signature",
    "stderr_sha256",
    "stdout_sha256",
]
SETUP_ARGV = [
    "python3",
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "-r",
    "requirements-iptc-validator.txt",
    "-r",
    "requirements-iptc-build.txt",
]
VERIFICATION = [
    {
        "name": "ai-command-inventory",
        "category": "static_inventory",
        "argv": ["python3", "scripts/check-ai-command-inventory.py"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 30,
        "enabled": True,
    },
    {
        "name": "iptc-suite-list",
        "category": "manifest",
        "argv": ["python3", "tools/iptc/run_test_suites.py", "--list"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 30,
        "enabled": True,
    },
    {
        "name": "agent-builder-compat",
        "category": "generated_compatibility",
        "argv": [
            "python3",
            "scripts/sync-machina-agent-builder-compat.py",
            "--check",
        ],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 60,
        "enabled": True,
    },
    {
        "name": "machina-ai-policy",
        "category": "policy",
        "argv": [
            "python3",
            "scripts/check-machina-ai-policy.py",
            "all",
            "--require-semantic",
        ],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 120,
        "enabled": True,
    },
    {
        "name": "agent-builder-unit",
        "category": "unit",
        "argv": [
            "python3",
            "-m",
            "unittest",
            "tests/test_machina_agent_builder_validator.py",
        ],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 120,
        "enabled": True,
    },
    {
        "name": "agent-builder-validation",
        "category": "validation",
        "argv": ["python3", "scripts/validate-machina-agent-builder.py"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 300,
        "enabled": True,
    },
    {
        "name": "iptc-pin",
        "category": "dependency_pin",
        "argv": ["python3", "-m", "tools.iptc", "--verify-pin"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 300,
        "enabled": True,
    },
    {
        "name": "machina-ai-connector-pytest",
        "category": "connector_tests",
        "argv": ["python3", "-m", "pytest", "connectors/machina-ai/tests"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 300,
        "enabled": False,
        "reason": "exact_dependencies_not_pinned",
    },
    {
        "name": "nvidia-nim-connector-pytest",
        "category": "connector_tests",
        "argv": ["python3", "-m", "pytest", "connectors/nvidia-nim/tests"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 300,
        "enabled": False,
        "reason": "exact_dependencies_not_pinned",
    },
    {
        "name": "iptc-test-suites",
        "category": "test_suite",
        "argv": ["python3", "tools/iptc/run_test_suites.py", "--verbose"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 1800,
        "enabled": True,
    },
    {
        "name": "iptc-check",
        "category": "conformance",
        "argv": ["python3", "-m", "tools.iptc", "--check"],
        "network_required": False,
        "secrets_required": False,
        "timeout_seconds": 1800,
        "enabled": True,
    },
]
EXPECTED_CONTRACT = {
    "schema_version": 1,
    "design_log": "030",
    "repository": "machina-templates",
    "authorized_base_sha": BASE_SHA,
    "mode": "shadow",
    "approved_by": "Andre",
    "approved_at": "2026-08-14",
    "pilot_context": PILOT_CONTEXT,
    "reviewers": ["@antonelli182"],
    "allowed_routines": ["dead_code_evidence", "flaky_test_evidence"],
    "runtime": {"network_allowed": False, "secrets_required": False},
    "authority": {
        "repository_writes": False,
        "fix": False,
        "stage": False,
        "commit": False,
        "push": False,
        "merge": False,
        "deploy": False,
        "rollback": False,
        "external_post": False,
    },
    "concurrency": {"writer_limit_repo": 0, "writer_limit_fleet": 0},
    "repair_pass_limit": 0,
    "evidence": {
        "destination": {
            "os_temp_only": True,
            "repository_paths_allowed": False,
        },
        "required_fields": REQUIRED_EVIDENCE_FIELDS,
    },
    "prohibited_paths": ["**"],
    "setup": {
        "automatic": False,
        "operator_only_argv": SETUP_ARGV,
        "network_required": True,
    },
    "workflow_policy": {
        "reviewed_at_base_sha": BASE_SHA,
        "human_merge_required": True,
        "main_push_side_effects": ["subscriber_webhook"],
        "release_tag_publish": True,
        "workflow_changes_allowed": False,
    },
    "verification": VERIFICATION,
}


def run_auditor(contract: Path | None = None, cwd: Path | None = None):
    command = [sys.executable, str(AUDITOR)]
    if contract is not None:
        command.extend(["--contract", str(contract)])
    return subprocess.run(
        command,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )


def run_auditor_arguments(*arguments, cwd: Path | None = None):
    return subprocess.run(
        [sys.executable, str(AUDITOR), *arguments],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )


def parsed_output(completed: subprocess.CompletedProcess[str]):
    return json.loads(completed.stdout)


class MaintenanceContractCLITests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp = Path(self.temporary_directory.name)

    def write_contract(self, document=None, name="maintenance.json"):
        path = self.temp / name
        path.write_text(
            json.dumps(
                EXPECTED_CONTRACT if document is None else document,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def assert_rejected(self, document):
        path = self.write_contract(document)
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        output = parsed_output(completed)
        self.assertEqual(output["schema_version"], 1)
        self.assertEqual(output["outcome"], "rejected")
        self.assertTrue(output["reasons"])
        self.assertRegex(output["contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(completed.stderr, "")
        return output

    def test_checked_in_contract_is_valid_through_default_cli(self):
        completed = run_auditor()
        self.assertEqual(completed.returncode, 0, completed)
        self.assertEqual(parsed_output(completed)["outcome"], "valid")

    def test_checked_in_contract_has_exact_reviewed_content(self):
        self.assertEqual(json.loads(CONTRACT.read_text(encoding="utf-8")),
                         EXPECTED_CONTRACT)

    def test_valid_output_is_stable_and_hashes_exact_input_bytes(self):
        path = self.write_contract()
        first = run_auditor(path, self.temp)
        second = run_auditor(path, self.temp)
        self.assertEqual(first.returncode, 0, first)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertEqual(
            parsed_output(first),
            {
                "schema_version": 1,
                "outcome": "valid",
                "reasons": [],
                "contract_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
        self.assertNotIn("timestamp", first.stdout.lower())

    def test_duplicate_keys_are_rejected(self):
        path = self.write_contract()
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(
            '  "schema_version": 1,',
            '  "schema_version": 1,\n  "schema_version": 1,',
            1,
        ), encoding="utf-8")
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertIn("duplicate", " ".join(parsed_output(completed)["reasons"]))

    def test_symlink_is_rejected_without_following_it(self):
        target = self.write_contract(name="target.json")
        link = self.temp / "maintenance.json"
        link.symlink_to(target)
        completed = run_auditor(link, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertIn("symlink", " ".join(parsed_output(completed)["reasons"]))

    def test_fifo_nonregular_input_is_rejected_without_blocking(self):
        fifo = self.temp / "maintenance.json"
        os.mkfifo(fifo)
        completed = run_auditor(fifo, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertIn("regular", " ".join(parsed_output(completed)["reasons"]))

    def test_oversized_json_is_rejected(self):
        path = self.temp / "maintenance.json"
        path.write_bytes(b" " * 65537)
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertIn("size", " ".join(parsed_output(completed)["reasons"]))

    def test_deep_json_is_rejected(self):
        path = self.temp / "maintenance.json"
        path.write_text('{"x":' * 20 + "null" + "}" * 20, encoding="utf-8")
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertIn("depth", " ".join(parsed_output(completed)["reasons"]))

    def test_missing_contract_is_structured_unable(self):
        completed = run_auditor(self.temp / "missing.json", self.temp)
        self.assertEqual(completed.returncode, 2, completed)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(
            parsed_output(completed),
            {
                "schema_version": 1,
                "outcome": "unable",
                "reasons": ["contract cannot be inspected"],
                "contract_sha256": None,
            },
        )

    def test_cli_errors_are_structured_and_do_not_echo_values(self):
        marker = "super-secret-cli-value-that-must-not-be-echoed"
        completed = run_auditor_arguments("--unknown", marker, cwd=self.temp)
        self.assertEqual(completed.returncode, 2, completed)
        self.assertEqual(completed.stderr, "")
        output = parsed_output(completed)
        self.assertEqual(output["outcome"], "unable")
        self.assertIsNone(output["contract_sha256"])
        self.assertNotIn(marker, completed.stdout)

    def test_unknown_and_missing_root_fields_are_rejected(self):
        unknown = copy.deepcopy(EXPECTED_CONTRACT)
        unknown["surprise"] = False
        self.assert_rejected(unknown)
        missing = copy.deepcopy(EXPECTED_CONTRACT)
        del missing["repository"]
        self.assert_rejected(missing)

    def test_pilot_context_is_required_exact_and_inactive(self):
        valid = copy.deepcopy(EXPECTED_CONTRACT)
        valid["pilot_context"] = copy.deepcopy(PILOT_CONTEXT)
        completed = run_auditor(self.write_contract(valid), self.temp)
        self.assertEqual(completed.returncode, 0, completed)

        missing = copy.deepcopy(EXPECTED_CONTRACT)
        del missing["pilot_context"]
        self.assert_rejected(missing)

        active = copy.deepcopy(valid)
        active["pilot_context"]["active_conflict"] = True
        output = self.assert_rejected(active)
        self.assertIn("active_conflict", " ".join(output["reasons"]))

        unknown = copy.deepcopy(valid)
        unknown["pilot_context"]["surprise"] = False
        self.assert_rejected(unknown)

        wrong = copy.deepcopy(valid)
        wrong["pilot_context"]["selected_by"] = "Not Andre"
        self.assert_rejected(wrong)

    def test_unknown_and_missing_nested_fields_are_rejected(self):
        unknown = copy.deepcopy(EXPECTED_CONTRACT)
        unknown["runtime"]["surprise"] = False
        self.assert_rejected(unknown)
        missing = copy.deepcopy(EXPECTED_CONTRACT)
        del missing["workflow_policy"]["human_merge_required"]
        self.assert_rejected(missing)

    def test_wrong_types_are_rejected_including_bool_as_integer(self):
        wrong = copy.deepcopy(EXPECTED_CONTRACT)
        wrong["approved_at"] = 20260814
        self.assert_rejected(wrong)
        bool_integer = copy.deepcopy(EXPECTED_CONTRACT)
        bool_integer["repair_pass_limit"] = False
        self.assert_rejected(bool_integer)

    def test_authority_escalation_is_rejected(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["authority"]["fix"] = True
        output = self.assert_rejected(document)
        self.assertIn("authority", " ".join(output["reasons"]))

    def test_unsafe_argv_shell_and_network_clients_are_rejected(self):
        for executable in ("", "sh", "/bin/bash", "curl", "wget"):
            with self.subTest(executable=executable):
                document = copy.deepcopy(EXPECTED_CONTRACT)
                document["verification"][0]["argv"][0] = executable
                output = self.assert_rejected(document)
                self.assertIn("argv", " ".join(output["reasons"]))

    def test_argv_control_characters_are_rejected(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["verification"][0]["argv"][1] = "unsafe\nargument"
        output = self.assert_rejected(document)
        self.assertIn("argv", " ".join(output["reasons"]))

    def test_enabled_verification_cannot_require_network_or_secrets(self):
        for key in ("network_required", "secrets_required"):
            with self.subTest(key=key):
                document = copy.deepcopy(EXPECTED_CONTRACT)
                document["verification"][0][key] = True
                output = self.assert_rejected(document)
                self.assertIn(key, " ".join(output["reasons"]))

    def test_disabled_verification_requires_nonempty_reason(self):
        for reason in (None, ""):
            with self.subTest(reason=reason):
                document = copy.deepcopy(EXPECTED_CONTRACT)
                if reason is None:
                    del document["verification"][7]["reason"]
                else:
                    document["verification"][7]["reason"] = reason
                output = self.assert_rejected(document)
                self.assertIn("reason", " ".join(output["reasons"]))

    def test_invalid_base_sha_is_rejected(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["authorized_base_sha"] = "not-a-sha"
        output = self.assert_rejected(document)
        self.assertIn("authorized_base_sha", " ".join(output["reasons"]))

    def test_routine_escalation_and_unsorted_routines_are_rejected(self):
        escalated = copy.deepcopy(EXPECTED_CONTRACT)
        escalated["allowed_routines"].append("automatic_fix")
        self.assert_rejected(escalated)
        unsorted = copy.deepcopy(EXPECTED_CONTRACT)
        unsorted["allowed_routines"].reverse()
        output = self.assert_rejected(unsorted)
        self.assertIn("sorted", " ".join(output["reasons"]))

    def test_invalid_reviewer_handle_is_rejected(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["reviewers"] = ["antonelli182"]
        output = self.assert_rejected(document)
        self.assertIn("reviewer", " ".join(output["reasons"]))

    def test_weakened_prohibited_paths_are_rejected(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["prohibited_paths"] = ["workflows/**"]
        output = self.assert_rejected(document)
        self.assertIn("prohibited_paths", " ".join(output["reasons"]))

    def test_setup_cannot_be_automatic(self):
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["setup"]["automatic"] = True
        output = self.assert_rejected(document)
        self.assertIn("setup.automatic", " ".join(output["reasons"]))

    def test_output_never_echoes_unknown_secret_values(self):
        marker = "super-secret-value-that-must-not-be-echoed"
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["secret_token"] = marker
        path = self.write_contract(document)
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertNotIn(marker, completed.stdout)
        self.assertNotIn(marker, completed.stderr)

    def test_contract_argv_is_never_executed(self):
        marker = self.temp / "must-not-exist"
        document = copy.deepcopy(EXPECTED_CONTRACT)
        document["verification"][0]["argv"] = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path({0!r}).touch()".format(str(marker)),
        ]
        completed = run_auditor(self.write_contract(document), self.temp)
        self.assertEqual(completed.returncode, 3, completed)
        self.assertFalse(marker.exists())

    def test_audit_does_not_mutate_the_filesystem(self):
        path = self.write_contract()
        sentinel = self.temp / "sentinel.bin"
        sentinel.write_bytes(b"unchanged")
        before = {
            item.name: (item.read_bytes(), item.stat().st_mode, item.stat().st_mtime_ns)
            for item in self.temp.iterdir()
            if item.is_file()
        }
        auditor_before = AUDITOR.read_bytes()
        checked_in_before = CONTRACT.read_bytes()
        completed = run_auditor(path, self.temp)
        self.assertEqual(completed.returncode, 0, completed)
        after = {
            item.name: (item.read_bytes(), item.stat().st_mode, item.stat().st_mtime_ns)
            for item in self.temp.iterdir()
            if item.is_file()
        }
        self.assertEqual(after, before)
        self.assertEqual(AUDITOR.read_bytes(), auditor_before)
        self.assertEqual(CONTRACT.read_bytes(), checked_in_before)


if __name__ == "__main__":
    unittest.main()
