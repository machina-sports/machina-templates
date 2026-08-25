#!/usr/bin/env python3
"""Validate the Design Log 030 shadow maintenance contract without running it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / ".machina/maintenance.json"
MAX_CONTRACT_BYTES = 65536
MAX_JSON_DEPTH = 12
BASE_SHA = "3a020f67b43aea2babf3c1808f2e89659d100bc8"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REVIEWER_PATTERN = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SHELL_PROGRAMS = frozenset((
    "bash", "csh", "dash", "fish", "ksh", "powershell", "pwsh", "sh",
    "tcsh", "zsh", "cmd", "cmd.exe",
))
NETWORK_CLIENTS = frozenset((
    "curl", "ftp", "nc", "ncat", "netcat", "rsync", "scp", "sftp",
    "ssh", "telnet", "wget",
))
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
            "python3", "scripts/sync-machina-agent-builder-compat.py", "--check",
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
            "python3", "scripts/check-machina-ai-policy.py", "all",
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
            "python3", "-m", "unittest",
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
    "pilot_context": {
        "selected_by": "Andre",
        "selected_at": "2026-08-14",
        "reviewed_at_base_sha": BASE_SHA,
        "active_conflict": False,
    },
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


class DuplicateKeyError(ValueError):
    """Raised when an object contains a key more than once."""


class CommandLineError(ValueError):
    """Raised for CLI input that must not be echoed by argparse."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CommandLineError("invalid command-line arguments")


def add_reason(reasons, reason):
    if reason not in reasons:
        reasons.append(reason)


def output(outcome, reasons, contract_sha256):
    document = {
        "schema_version": 1,
        "outcome": outcome,
        "reasons": reasons,
        "contract_sha256": contract_sha256,
    }
    sys.stdout.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def read_regular_file(path):
    """Return bytes or a classified error without following a symlink/FIFO."""
    try:
        initial = path.lstat()
    except OSError:
        return None, "unable", "contract cannot be inspected"
    if stat.S_ISLNK(initial.st_mode):
        return None, "rejected", "contract path must not be a symlink"
    if not stat.S_ISREG(initial.st_mode):
        return None, "rejected", "contract path must be a regular file"
    if initial.st_size > MAX_CONTRACT_BYTES:
        return None, "rejected", "contract size exceeds the allowed maximum"

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(str(path), flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            return None, "rejected", "contract path must be a regular file"
        if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
            return None, "rejected", "contract changed while it was inspected"
        if opened.st_size > MAX_CONTRACT_BYTES:
            return None, "rejected", "contract size exceeds the allowed maximum"
        chunks = []
        remaining = MAX_CONTRACT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 16384))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        blob = b"".join(chunks)
        if len(blob) > MAX_CONTRACT_BYTES:
            return None, "rejected", "contract size exceeds the allowed maximum"
        return blob, None, None
    except OSError:
        return None, "unable", "contract cannot be read"
    finally:
        if descriptor is not None:
            os.close(descriptor)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON object key")
        result[key] = value
    return result


def json_depth(value):
    maximum = 1
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        maximum = max(maximum, depth)
        if maximum > MAX_JSON_DEPTH:
            return maximum
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return maximum


def validate_exact_structure(actual, expected, path, reasons):
    """Reject type drift, missing/unknown keys, and any unreviewed value drift."""
    if type(actual) is not type(expected):
        add_reason(reasons, "wrong type at {0}".format(path))
        return
    if isinstance(expected, dict):
        missing = [key for key in expected if key not in actual]
        unknown = [key for key in actual if key not in expected]
        for key in missing:
            add_reason(reasons, "missing required key {0} at {1}".format(key, path))
        if unknown:
            add_reason(reasons, "unknown key at {0}".format(path))
        for key in expected:
            if key in actual:
                child = key if path == "$" else path + "." + key
                validate_exact_structure(actual[key], expected[key], child, reasons)
        return
    if isinstance(expected, list):
        if len(actual) != len(expected):
            add_reason(reasons, "wrong list length at {0}".format(path))
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            validate_exact_structure(
                actual_item, expected_item, "{0}[{1}]".format(path, index), reasons,
            )
        return
    if actual != expected:
        add_reason(reasons, "value must match reviewed shadow contract at {0}".format(path))


def validate_sorted_unique_strings(value, path, reasons):
    if not isinstance(value, list) or not value:
        add_reason(reasons, "{0} must be a nonempty sorted unique string list".format(path))
        return
    if any(not isinstance(item, str) or not item for item in value):
        add_reason(reasons, "{0} must contain only nonempty strings".format(path))
        return
    if value != sorted(value) or len(value) != len(set(value)):
        add_reason(reasons, "{0} must be sorted and unique".format(path))


def validate_argv(argv, path, reasons):
    if not isinstance(argv, list) or not argv:
        add_reason(reasons, "{0} must be a nonempty argv list".format(path))
        return
    for item in argv:
        if not isinstance(item, str) or not item or len(item) > 4096:
            add_reason(reasons, "{0} contains an unsafe argv string".format(path))
            return
        if any(ord(character) < 32 or ord(character) == 127 for character in item):
            add_reason(reasons, "{0} contains an unsafe argv control character".format(path))
            return
    executable = Path(argv[0]).name.lower()
    if executable in SHELL_PROGRAMS:
        add_reason(reasons, "{0} names a forbidden shell program".format(path))
    if executable in NETWORK_CLIENTS:
        add_reason(reasons, "{0} names a forbidden network client".format(path))


def validate_invariants(document):
    reasons = []
    validate_exact_structure(document, EXPECTED_CONTRACT, "$", reasons)
    if not isinstance(document, dict):
        return reasons

    sha = document.get("authorized_base_sha")
    if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
        add_reason(reasons, "authorized_base_sha must be a lowercase 40-character SHA")
    elif sha != BASE_SHA:
        add_reason(reasons, "authorized_base_sha is not the reviewed base")

    pilot_context = document.get("pilot_context")
    if (not isinstance(pilot_context, dict)
            or pilot_context.get("active_conflict") is not False):
        add_reason(reasons, "pilot_context.active_conflict must be false")

    reviewers = document.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers or any(
            not isinstance(item, str) or not REVIEWER_PATTERN.fullmatch(item)
            for item in reviewers):
        add_reason(reasons, "reviewers must contain valid @handle values")
    elif len(reviewers) != len(set(reviewers)):
        add_reason(reasons, "reviewers must be unique")

    validate_sorted_unique_strings(
        document.get("allowed_routines"), "allowed_routines", reasons,
    )
    evidence = document.get("evidence")
    if isinstance(evidence, dict):
        validate_sorted_unique_strings(
            evidence.get("required_fields"), "evidence.required_fields", reasons,
        )

    authority = document.get("authority")
    if not isinstance(authority, dict) or any(
            type(value) is not bool or value for value in authority.values()):
        add_reason(reasons, "authority must contain only false booleans")
    if document.get("prohibited_paths") != ["**"]:
        add_reason(reasons, "prohibited_paths must prohibit all repository paths")

    setup = document.get("setup")
    if isinstance(setup, dict):
        if setup.get("automatic") is not False:
            add_reason(reasons, "setup.automatic must be false")
        validate_argv(setup.get("operator_only_argv"),
                      "setup.operator_only_argv", reasons)

    verification = document.get("verification")
    if not isinstance(verification, list):
        add_reason(reasons, "verification must be a list")
    else:
        for index, entry in enumerate(verification):
            path = "verification[{0}]".format(index)
            if not isinstance(entry, dict):
                add_reason(reasons, "{0} must be an object".format(path))
                continue
            validate_argv(entry.get("argv"), path + ".argv", reasons)
            enabled = entry.get("enabled")
            if enabled is True:
                if entry.get("network_required") is not False:
                    add_reason(reasons, path + ".network_required must be false when enabled")
                if entry.get("secrets_required") is not False:
                    add_reason(reasons, path + ".secrets_required must be false when enabled")
                if "reason" in entry:
                    add_reason(reasons, path + ".reason is only allowed when disabled")
            elif enabled is False:
                if not isinstance(entry.get("reason"), str) or not entry.get("reason"):
                    add_reason(reasons, path + ".reason must be nonempty when disabled")
            else:
                add_reason(reasons, path + ".enabled must be a boolean")
            timeout = entry.get("timeout_seconds")
            if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
                add_reason(reasons, path + ".timeout_seconds must be a positive integer")
    return reasons


def audit(path):
    blob, classification, reason = read_regular_file(path)
    if classification:
        output(classification, [reason], None)
        return 2 if classification == "unable" else 3

    digest = hashlib.sha256(blob).hexdigest()
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        output("rejected", ["contract is not valid UTF-8"], digest)
        return 3
    try:
        document = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except DuplicateKeyError as error:
        output("rejected", [str(error)], digest)
        return 3
    except (ValueError, RecursionError):
        output("rejected", ["contract is not valid bounded JSON"], digest)
        return 3
    if json_depth(document) > MAX_JSON_DEPTH:
        output("rejected", ["contract JSON exceeds the maximum depth"], digest)
        return 3

    reasons = validate_invariants(document)
    if reasons:
        output("rejected", reasons, digest)
        return 3
    output("valid", [], digest)
    return 0


def main(argv=None):
    parser = SafeArgumentParser(
        description="Audit the Design Log 030 shadow maintenance contract.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="contract path (default: repository .machina/maintenance.json)",
    )
    try:
        arguments = parser.parse_args(argv)
    except CommandLineError as error:
        output("unable", [str(error)], None)
        return 2
    return audit(arguments.contract)


if __name__ == "__main__":
    raise SystemExit(main())
