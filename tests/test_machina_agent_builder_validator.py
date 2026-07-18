"""Focused regression tests for the Machina Agent Builder validator."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate-machina-agent-builder.py"
SPEC = importlib.util.spec_from_file_location("machina_validator", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(validator)

SYNC_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync-machina-agent-builder-compat.py"
SYNC_SPEC = importlib.util.spec_from_file_location("machina_sync", SYNC_SCRIPT)
sync = importlib.util.module_from_spec(SYNC_SPEC)
assert SYNC_SPEC.loader
SYNC_SPEC.loader.exec_module(sync)


def write_tree(path: Path, content: bytes) -> None:
    path.mkdir(parents=True)
    (path / "value.bin").write_bytes(content)


def workflow_check(registrations, installed):
    with tempfile.TemporaryDirectory() as temporary:
        check = validator.Validator(Path(temporary))
        check.workflows(Path(temporary), {"workflows": registrations}, installed, "primary")
        return check.errors


class CompatibilityTransactionTests(unittest.TestCase):
    def test_build_rejects_symlinked_canonical_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            destination = root / "destination"
            write_tree(real, b"value")
            linked = root / "canonical"
            linked.symlink_to(real, target_is_directory=True)
            with mock.patch.object(sync, "CANONICAL", linked), self.assertRaisesRegex(
                sync.TreeSafetyError, "canonical root must not be a symlink"
            ):
                sync.build(destination)
            self.assertFalse(destination.exists())

    def test_build_rejects_arbitrary_canonical_symlink_before_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = root / "canonical"
            canonical.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"secret")
            (canonical / "linked.bin").symlink_to(outside)
            with mock.patch.object(sync, "CANONICAL", canonical), mock.patch.object(
                Path, "read_bytes", side_effect=AssertionError("must not read through symlink")
            ), self.assertRaisesRegex(sync.TreeSafetyError, "canonical tree contains symlink"):
                sync.build(root / "destination")

    def test_snapshot_rejects_symlink_root_and_entry_before_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = root / "tree"
            write_tree(tree, b"ordinary")
            linked_root = root / "linked-root"
            linked_root.symlink_to(tree, target_is_directory=True)
            with self.assertRaisesRegex(sync.TreeSafetyError, "snapshot root must not be a symlink"):
                sync.snapshot(linked_root)
            outside = root / "outside.bin"
            outside.write_bytes(b"secret")
            (tree / "linked.bin").symlink_to(outside)
            original = Path.read_bytes

            def guarded_read(path, *args, **kwargs):
                if path.name == "linked.bin":
                    raise AssertionError("must not read through symlink")
                return original(path, *args, **kwargs)

            with mock.patch.object(Path, "read_bytes", new=guarded_read), self.assertRaisesRegex(
                sync.TreeSafetyError, "snapshot tree contains symlink"
            ):
                sync.snapshot(tree)

    def test_copytree_preparation_failure_cleans_artifacts_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "expected"
            first = root / "first-parent" / "first"
            second = root / "second-parent" / "second"
            write_tree(expected, b"new")
            write_tree(first, b"old-first")
            write_tree(second, b"old-second")
            calls = 0

            def fail_second_copytree(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    destination.mkdir()
                    (destination / "partial.bin").write_bytes(b"partial")
                    raise OSError("injected copytree failure")
                return shutil.copytree(source, destination)

            with self.assertRaisesRegex(OSError, "injected copytree failure"):
                sync.transactional_replace(expected, (first, second), copytree=fail_second_copytree)
            self.assertEqual({"value.bin": b"old-first"}, sync.snapshot(first))
            self.assertEqual({"value.bin": b"old-second"}, sync.snapshot(second))
            for destination in (first, second):
                artifacts = list(destination.parent.glob(f".{destination.name}.stage-*"))
                artifacts += list(destination.parent.glob(f".{destination.name}.backup-*"))
                self.assertEqual([], artifacts)

    def test_second_alias_swap_failure_restores_both_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, first, second = root / "expected", root / "first", root / "second"
            write_tree(expected, b"new")
            write_tree(first, b"old-first")
            write_tree(second, b"old-second")
            real_replace, calls = os.replace, 0

            def fail_second_swap(source, destination):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected second swap failure")
                real_replace(source, destination)

            with self.assertRaisesRegex(OSError, "injected"):
                sync.transactional_replace(expected, (first, second), replace=fail_second_swap)
            self.assertEqual({"value.bin": b"old-first"}, sync.snapshot(first))
            self.assertEqual({"value.bin": b"old-second"}, sync.snapshot(second))

    def test_initially_absent_alias_is_absent_after_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, absent, present = root / "expected", root / "absent", root / "present"
            write_tree(expected, b"new")
            write_tree(present, b"old")
            real_replace, calls = os.replace, 0

            def fail(source, destination):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("injected")
                real_replace(source, destination)

            with self.assertRaises(OSError):
                sync.transactional_replace(expected, (absent, present), replace=fail)
            self.assertFalse(absent.exists())
            self.assertEqual({"value.bin": b"old"}, sync.snapshot(present))

    def test_rollback_failure_reports_details_and_chains_transaction_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, first, second = root / "expected", root / "first", root / "second"
            write_tree(expected, b"new")
            write_tree(first, b"old-first")
            write_tree(second, b"old-second")
            real_replace, calls = os.replace, 0

            def fail_second_swap(source, destination):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected transaction failure")
                real_replace(source, destination)

            def fail_first_restore(path):
                if path == first:
                    raise PermissionError("injected rollback failure")
                shutil.rmtree(path)

            with self.assertRaisesRegex(
                RuntimeError,
                r"1 rollback operation\(s\) failed: PermissionError: injected rollback failure",
            ) as raised:
                sync.transactional_replace(
                    expected,
                    (first, second),
                    replace=fail_second_swap,
                    remove_tree=fail_first_restore,
                )
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertEqual("injected transaction failure", str(raised.exception.__cause__))

    def test_cleanup_failure_keeps_committed_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, first, second = root / "expected", root / "first", root / "second"
            write_tree(expected, b"new")
            write_tree(first, b"old-first")
            write_tree(second, b"old-second")

            def cleanup(path):
                if ".backup-" in path.name and any(path.iterdir()):
                    raise OSError("injected cleanup failure")
                shutil.rmtree(path)

            warnings = sync.transactional_replace(expected, (first, second), remove_tree=cleanup)
            self.assertEqual(2, len(warnings))
            self.assertEqual(sync.snapshot(expected), sync.snapshot(first))
            self.assertEqual(sync.snapshot(first), sync.snapshot(second))

    def test_normal_transaction_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, first, second = root / "expected", root / "first", root / "second"
            write_tree(expected, b"new")
            self.assertEqual([], sync.transactional_replace(expected, (first, second)))
            self.assertEqual(sync.snapshot(first), sync.snapshot(second))


class ValidatorRegressionTests(unittest.TestCase):
    def package_with_declared_file(self, root, *, dataset=None, reference=None):
        package = root / "skills/machina-agent-builder"
        package.mkdir(parents=True)
        datasets = "datasets: []\n"
        if dataset is not None:
            datasets = f"datasets:\n  - type: document\n    path: {dataset}\n"
        references = ""
        if reference is not None:
            references = f"  references:\n    - filename: {reference}\n"
        (package / "_install.yml").write_text(
            "setup:\n  value: skills/machina-agent-builder\n  status: available\n  version: '1.2.3'\n" + datasets
        )
        (package / "skill.yml").write_text(
            "skill:\n  name: machina-agent-builder\n  status: available\n  version: '1.2.3'\n"
            + references + "  workflows: []\n"
        )
        return package

    def test_declared_dataset_and_reference_traversal_fail(self):
        for kind in ("dataset", "reference"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                kwargs = {kind: "../../outside.md"}
                package = self.package_with_declared_file(root, **kwargs)
                (root / "outside.md").write_text("outside\n")
                check = validator.Validator(root)
                check.package(package, True)
                self.assertTrue(any("escapes the resolved package root" in item for item in check.errors), check.errors)

    def test_declared_dataset_and_reference_backslashes_fail(self):
        paths = (r"C:\outside.md", r"..\..\outside.md", r"\\server\share\outside.md")
        for kind in ("dataset", "reference"):
            for path in paths:
                with self.subTest(kind=kind, path=path), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    package = self.package_with_declared_file(root, **{kind: path})
                    check = validator.Validator(root)
                    check.package(package, True)
                    self.assertTrue(any("must use POSIX '/' separators" in item for item in check.errors), check.errors)

    def test_canonical_root_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            package = root / validator.CANONICAL_REL
            package.parent.mkdir(parents=True)
            package.symlink_to(outside, target_is_directory=True)
            check = validator.Validator(root)
            self.assertFalse(check.safe_package_tree(package))
            self.assertTrue(any("package root must not be a symlink" in item for item in check.errors), check.errors)

    def test_package_root_resolving_outside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external:
            root = Path(temporary)
            external_skills = Path(external) / "skills"
            (external_skills / "machina-agent-builder").mkdir(parents=True)
            (root / "skills").symlink_to(external_skills, target_is_directory=True)
            package = root / validator.CANONICAL_REL
            check = validator.Validator(root)
            self.assertFalse(check.safe_package_tree(package))
            self.assertTrue(any("resolves outside the repository root" in item for item in check.errors), check.errors)

    def test_canonical_arbitrary_file_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / validator.CANONICAL_REL
            package.mkdir(parents=True)
            outside = root / "outside.bin"
            outside.write_bytes(b"secret")
            (package / "ordinary-link.bin").symlink_to(outside)
            check = validator.Validator(root)
            self.assertFalse(check.safe_package_tree(package))
            self.assertTrue(any("symlinks are not allowed" in item for item in check.errors), check.errors)

    def test_alias_tree_symlink_is_rejected_without_snapshot_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            alias = root / validator.ALIAS_RELS[0]
            alias.mkdir(parents=True)
            outside = root / "outside.bin"
            outside.write_bytes(b"secret")
            (alias / "undeclared-link.bin").symlink_to(outside)
            check = validator.Validator(root)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not snapshot symlink")):
                self.assertFalse(check.safe_package_tree(alias))
            self.assertTrue(any("symlinks are not allowed" in item for item in check.errors), check.errors)

    def test_identity_scan_does_not_read_rejected_package_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / validator.CANONICAL_REL
            package.mkdir(parents=True)
            outside = root / "outside.yml"
            outside.write_text("skill:\n  name: machina-agent-builder\n")
            linked = package / "linked.yml"
            linked.symlink_to(outside)
            check = validator.Validator(root)
            original = Path.read_text

            def guarded_read(path, *args, **kwargs):
                if path == linked:
                    raise AssertionError("must not read rejected package symlink")
                return original(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", new=guarded_read):
                check.identities(excluded=(package,))

    def test_ordinary_nested_package_files_pass_tree_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / validator.CANONICAL_REL / "nested" / "deeper"
            package.mkdir(parents=True)
            (package / "ordinary.bin").write_bytes(b"value")
            check = validator.Validator(root)
            self.assertTrue(check.safe_package_tree(root / validator.CANONICAL_REL))
            self.assertEqual([], check.errors)

    def test_declared_dataset_and_reference_symlink_escape_fail(self):
        for kind in ("dataset", "reference"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = self.package_with_declared_file(root, **{kind: "nested/escape.md"})
                outside = root / "outside.md"
                outside.write_text("outside\n")
                (package / "nested").mkdir()
                (package / "nested/escape.md").symlink_to(outside)
                check = validator.Validator(root)
                check.package(package, True)
                self.assertTrue(any("symlinks are not allowed" in item for item in check.errors), check.errors)

    def test_valid_nested_declared_dataset_and_reference_pass_containment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self.package_with_declared_file(
                root, dataset="nested/data.md", reference="nested/reference.md"
            )
            (package / "nested").mkdir()
            (package / "nested/data.md").write_text("data\n")
            (package / "nested/reference.md").write_text("reference\n")
            check = validator.Validator(root)
            check.package(package, True)
            self.assertFalse(any("resolved package root" in item or "target is missing" in item
                                 for item in check.errors), check.errors)

    def test_absolute_declared_path_fails_before_file_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.md"
            outside.write_text("outside\n")
            package = self.package_with_declared_file(root, dataset=str(outside))
            check = validator.Validator(root)
            check.package(package, True)
            self.assertTrue(any("must be relative" in item for item in check.errors), check.errors)

    def test_missing_canonical_skill_markdown_is_controlled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "skills/machina-agent-builder").mkdir(parents=True)
            check = validator.Validator(root)
            check.frontmatter()
            self.assertTrue(any("canonical guide is missing or unreadable" in item for item in check.errors))

    def test_unreadable_frontmatter_is_controlled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / "skills/machina-agent-builder/SKILL.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("placeholder\n")
            check = validator.Validator(root)
            with mock.patch.object(Path, "read_text", side_effect=PermissionError("injected")):
                check.frontmatter()
            self.assertTrue(any("canonical guide is missing or unreadable" in item for item in check.errors))

    def test_unreadable_markdown_does_not_stop_link_or_policy_loops(self):
        for operation, expected in (("links", "target does not exist"),
                                    ("provider_policy", "SDK-composition-only")):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                bad, good = package / "a-bad.md", package / "z-good.md"
                bad.write_text("bad\n")
                good.write_text("[missing](missing.md)\n```text\nfetch(url)\n```\n")
                original = Path.read_text

                def injected(path, *args, **kwargs):
                    if path.name == bad.name:
                        raise PermissionError("injected")
                    return original(path, *args, **kwargs)

                check = validator.Validator(root)
                with mock.patch.object(Path, "read_text", new=injected):
                    getattr(check, operation)()
                self.assertTrue(any("Markdown file is missing or unreadable" in item for item in check.errors))
                self.assertTrue(any(expected in item for item in check.errors), check.errors)

    def test_unreadable_provider_policy_yaml_is_controlled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "skills/machina-agent-builder/bad.yml"
            target.parent.mkdir(parents=True)
            target.write_text("value: safe\n")
            check = validator.Validator(root)
            with mock.patch.object(Path, "read_text", side_effect=UnicodeError("injected")):
                check.provider_policy()
            self.assertTrue(any("provider-policy YAML file is missing or unreadable" in item
                                for item in check.errors), check.errors)

    def test_unreadable_alias_snapshot_is_controlled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in validator.ALIAS_RELS:
                package = root / relative
                package.mkdir(parents=True)
                (package / "snapshot.bin").write_bytes(b"value")
            check = validator.Validator(root)
            original = Path.read_bytes

            def injected(path, *args, **kwargs):
                if path.name == "snapshot.bin":
                    raise PermissionError("injected")
                return original(path, *args, **kwargs)

            with mock.patch.object(Path, "read_bytes", new=injected):
                check.run(check_sync=False)
            self.assertTrue(any("alias snapshot file is unreadable" in item for item in check.errors), check.errors)

    def test_missing_vertex_fields_fails(self):
        text = """```yaml
tasks:
  - connector:
      name: google-genai
      command: invoke_prompt
```"""
        errors = validator.vertex_errors(text)
        self.assertTrue(any("location: global" in item and "provider: vertex_ai" in item for item in errors))

    def test_valid_vertex_connector_passes(self):
        text = """```yaml
connector:
  name: google-genai
  command: invoke_embedding
  location: global
  provider: vertex_ai
```"""
        self.assertEqual([], validator.vertex_errors(text))

    def test_tilde_yaml_fence_is_validated(self):
        text = """~~~yaml extra-info
connector:
  name: google-genai
  command: invoke_prompt
~~~
"""
        self.assertTrue(any("provider: vertex_ai" in item for item in validator.vertex_errors(text)))

    def test_four_backtick_yaml_fence_is_validated(self):
        text = """````YML tabbed
connector:
  name: google-genai
  command: invoke_prompt
````
"""
        self.assertTrue(any("location: global" in item for item in validator.vertex_errors(text)))

    def test_malformed_yaml_fence_fails(self):
        text = """```yaml
connector: [google-genai
command: invoke_prompt
```
"""
        self.assertTrue(any("invalid YAML" in item for item in validator.vertex_errors(text)))

    def test_valid_longer_yaml_fence_passes(self):
        text = """````yaml linenums=true
connector:
  name: google-genai
  command: invoke_prompt
  location: global
  provider: vertex_ai
`````
"""
        self.assertEqual([], validator.vertex_errors(text))

    def test_unclosed_yaml_fence_is_validated_through_eof(self):
        text = """```yaml
connector:
  name: google-genai
  command: invoke_prompt
"""
        self.assertTrue(any("provider: vertex_ai" in item for item in validator.vertex_errors(text)))

    def test_commonmark_container_code_blocks_are_in_document_order(self):
        text = "> ```yaml\n> first: true\n> ```\n\n- item\n\n      second: true\n"
        self.assertEqual(
            [("fenced", "yaml", "first: true\n"), ("indented", "", "second: true\n")],
            list(validator.active_code_blocks(text)),
        )

    def test_nested_container_and_unclosed_fence_are_active(self):
        text = "> - item\n>\n>   ~~~~text\n>   command curl \"$URL\"\n"
        self.assertEqual(
            [("fenced", "text", 'command curl "$URL"\n')],
            list(validator.active_code_blocks(text)),
        )

    def test_nested_benign_container_code_passes_provider_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / validator.CANONICAL_REL
            package.mkdir(parents=True)
            (package / "example.md").write_text(
                "> - example\n>\n>       result = sdk.resources.list()\n"
            )
            check = validator.Validator(root)
            check.provider_policy()
            self.assertEqual([], check.errors)

    def test_blockquote_and_list_code_bypasses_fail_provider_policy(self):
        examples = (
            "> ```text\n> curl $URL\n> ```\n",
            ">     curl $URL\n",
            "- example\n\n      curl $URL\n",
            "- example\n\n  ```text\n  curl $URL\n  ```\n",
            "> - example\n>\n>   ```text\n>   curl $URL\n>   ```\n",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(example)
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in error for error in check.errors), check.errors)

    def test_unclosed_generic_fence_is_checked_by_provider_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "example.md").write_text("```text\nyour-api-key\n")
            check = validator.Validator(root)
            check.provider_policy()
            self.assertTrue(any("unsafe credential" in item for item in check.errors), check.errors)

    def test_indented_vertex_command_missing_fields_fails(self):
        text = """Example:\n\n    connector:\n      name: google-genai\n      command: invoke_prompt\n"""
        self.assertTrue(any("provider: vertex_ai" in item for item in validator.vertex_errors(text)))

    def test_unknown_indented_non_yaml_block_is_ignored(self):
        text = """Example:\n\n    if (ready) {\n        render();\n    }\n"""
        self.assertEqual([], validator.vertex_errors(text))

    def test_indented_benign_snippet_passes_provider_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "example.md").write_text("Example:\n\n    result = sdk.resources.list()\n")
            check = validator.Validator(root)
            check.provider_policy()
            self.assertEqual([], check.errors)

    def test_indented_policy_markers_and_credentials_fail(self):
        examples = ("MACHINA_CLIENT_URL", 'api_key: "..."')
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"Example:\n\n    {example}\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(check.errors)

    def test_unsafe_credential_example_fails_with_vertex_vault_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "example.md").write_text("```python\nkey = 'your-api-key'\n```\n")
            check = validator.Validator(root)
            check.provider_policy()
            self.assertTrue(any("Vertex" in item and "Vault" in item for item in check.errors))

    def test_direct_client_api_markers_fail_with_sdk_composition_guidance(self):
        for marker in ("MACHINA_CLIENT_URL", "X-Api-Token"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```typescript\nconst value = '{marker}'\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_legitimate_connector_endpoint_operation_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "example.md").write_text(
                "```python\n{mcp}connector_endpoint(item_id='abc', data={'endpoint': '/health'})\n```\n"
            )
            check = validator.Validator(root)
            check.provider_policy()
            self.assertEqual([], check.errors)

    def test_raw_http_primitives_fail_sdk_composition_policy(self):
        examples = (
            "fetch(url)",
            "axios.post(endpoint, data)",
            "requests.get(url)",
            "httpx.request(method, url)",
            "urllib.request.urlopen(url)",
            "curl $SERVICE_URL",
            "aiohttp.ClientSession()",
            "urllib3.PoolManager()",
            "http.client.HTTPSConnection(host)",
            "new XMLHttpRequest()",
            "got.get(url)",
            "undici.request(url)",
            "http.request(url)",
            "https.get(url)",
            "requests.Session()",
            "httpx.Client()",
            "httpx.AsyncClient()",
            "wget https://example.test/data",
            "superagent.post(url)",
            "ky.get(url)",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_raw_http_aliased_imports_and_requires_fail_sdk_composition_policy(self):
        examples = (
            "import requests as r",
            "from httpx import Client as C",
            "import aiohttp as ah",
            "from urllib import request as urlrequest",
            "import urllib3 as pool",
            "const client = require('axios')",
            'const gotClient = require("got")',
            "import { request as send } from 'undici'",
            "const superClient = require('superagent')",
            "import kyClient from 'ky'",
            "const httpClient = require('node:http')",
            "import httpsClient from 'node:https'",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_raw_http_identifiers_fail_through_indirection(self):
        examples = (
            'const send = globalThis["fetch"]; send(url)',
            'const send = axios["get"]; send(url)',
            "const send = fetch",
            "client = requests",
            "const { get: send } = axios",
            'const send = window["fetch"]',
            "const send = self.fetch",
            'const send = globalThis["axios"][method]',
            "const { request: send } = await import('undici')",
            "const client = await import('node:http')",
            "client = __import__('httpx')",
            "module = __import__('urllib.request')",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_computed_module_loader_calls_fail_sdk_composition_policy(self):
        examples = (
            'const moduleName = ["ax","ios"].join(""); const client = await import(moduleName); client.get(endpoint);',
            "const client = require(packageName);",
            "client = __import__(module_name)",
            'await import("ax" + "ios")',
            "const client = require('./' + moduleName)",
            "const client = await import(`@scope/${name}`)",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("computed module-loader call" in item for item in check.errors), check.errors)

    def test_simple_literal_nonprohibited_module_loader_calls_pass(self):
        examples = (
            'const sdk = await import("@machina/sdk")',
            'const local = require("./local-module")',
            'module = __import__("json")',
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_raw_http_identifier_substrings_are_allowed(self):
        examples = (
            "fetch_result = sdk_call",
            "prefetch = sdk_call",
            "axios_adapter = sdk_call",
            "requests_cache = sdk_call",
            "curl_command = sdk_call",
            "scurl = sdk_call",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_shell_and_powershell_http_clients_fail_for_nonliteral_urls(self):
        examples = (
            'curl "https://example.test/data"',
            "wget '$SERVICE_URL'",
            'curl "${SERVICE_URL}"',
            "Invoke-WebRequest -Uri $endpoint",
            "Invoke-RestMethod -Uri 'https://example.test/data'",
            "command curl $endpoint",
            "env wget https://example.test/data",
            "& curl '$endpoint'",
            "$(curl \"$endpoint\")",
            "sudo env MODE=test wget $endpoint",
            "MODE=test curl $endpoint",
            "/usr/bin/env -i /usr/bin/wget $endpoint",
            "nohup curl $endpoint",
            "& 'curl' $endpoint",
            "iwr $endpoint",
            "irm -Uri https://example.test/data",
            "if ready; then curl $endpoint; fi",
            "exec /opt/bin/wget $endpoint",
            "builtin \\curl $endpoint",
            "'/opt/bin/iwr' $endpoint",
            'value="$(irm $endpoint)"',
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_shell_http_client_identifier_substrings_are_allowed(self):
        examples = ("curl_command = sdk_call", "scurl = sdk_call", "wget_result = sdk_call", "firm = sdk_call")
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_powershell_and_windows_http_surfaces_fail_sdk_composition_policy(self):
        examples = (
            "$client = New-Object System.Net.WebClient",
            "$client = New-Object Net.WebClient",
            "$client = [System.Net.WebClient]::new()",
            "$client = [Net.WebClient]::new()",
            "$client = New-Object System.Net.Http.HttpClient",
            "$client = [Net.Http.HttpClient]::new()",
            "$request = [System.Net.WebRequest]::Create($uri)",
            "$request = [Net.HttpWebRequest]::Create($uri)",
            "Start-BitsTransfer -Source $uri -Destination $path",
            "& Start-BitsTransfer -Source $uri -Destination $path",
            "Import-Module BitsTransfer",
            "Import-Module -Name 'BitsTransfer'",
            "bitsadmin /transfer job $uri $path",
            "BITSADMIN.EXE /DOWNLOAD job $uri $path",
            "$client.DownloadString($uri)",
            "$result = $client.DownloadFile($uri, $path)",
            "$result = $client.UploadString($uri, $body)",
            "$result = $client.UploadFile($uri, $path)",
            "$stream = $client.OpenRead($uri)",
            "$invoke = $client.DownloadString; & $invoke $uri",
            "$result = $client.'DownloadString'($uri)",
            "$client.GetAsync($uri)",
            "$client.PostAsync($uri, $body)",
            "$client.PutAsync($uri, $body)",
            "$client.DeleteAsync($uri)",
            "$client.PatchAsync($uri, $body)",
            "$client.SendAsync($message)",
            "$client.GetStringAsync($uri)",
            "$client.GetByteArrayAsync($uri)",
            "$client.GetStreamAsync($uri)",
            "$request.GetResponse()",
            "$request.GetResponseAsync()",
            "$method = $client.'GetAsync'",
            "$method = $request.(\"GetResponse\")",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```powershell\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_powershell_and_windows_http_identifier_substrings_are_allowed(self):
        examples = (
            "webclient_adapter = sdk_call",
            "httpclient_factory = sdk_call",
            "bitsadmin_result = sdk_call",
            "start_bitstransfer_result = sdk_call",
            "download_file_result = sdk_call",
            "downloadstring_result = sdk_call",
            "open_read_result = sdk_call",
            "get_async_result = sdk_call",
            "get_response_handler = sdk_call",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```powershell\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_ordinary_windows_downloader_and_url_handler_surfaces_fail(self):
        examples = (
            "certutil -urlcache -split -f https://example.test/a a.exe",
            r"'C:\Windows\System32\certutil.exe' -verifyctl -f https://example.test/a a.exe",
            "$result = & CERTUTIL.EXE -URLCACHE -f https://example.test/a a.exe",
            "aria2c https://example.test/a",
            r'"C:\Tools\aria2c.exe" https://example.test/a',
            "$result = cmd /c ARIA2C.EXE https://example.test/a",
            "mshta https://example.test/a.hta",
            r'"C:\Windows\System32\mshta.exe" javascript:alert(1)',
            "$result = & MSHTA.EXE vbscript:Execute(\"x\")",
            "regsvr32 /s /n /u /i:https://example.test/a.sct scrobj.dll",
            r'"C:\Windows\System32\regsvr32.exe" /i:https://example.test/a.sct scrobj.dll',
            "$result = cmd /c REGSVR32.EXE /s /i:https://example.test/a.sct scrobj.dll",
            "rundll32 url.dll,FileProtocolHandler https://example.test/a",
            r'"C:\Windows\System32\rundll32.exe" url.dll,FileProtocolHandler https://example.test/a',
            "$result = & RUNDLL32.EXE url.dll,FileProtocolHandler https://example.test/a",
            "ftp ftp://example.test/a",
            r'"C:\Windows\System32\ftp.exe" -s:commands.txt example.test',
            "$result = cmd /c FTP.EXE -n example.test",
            "tftp example.test GET payload.exe",
            r'"C:\Windows\System32\tftp.exe" example.test PUT payload.exe',
            "$result = & TFTP.EXE -i example.test GET payload.exe",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```powershell\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_variable_driven_windows_downloader_and_url_handler_surfaces_fail(self):
        examples = {
            "certutil": (
                "certutil -urlcache -f $URL out.exe",
                "certutil -verifyctl %URL%",
                "certutil -urlcache -f ${URL} out.exe",
            ),
            "aria2c": (
                "aria2c $URL",
                'aria2c.exe "%URL%"',
                "aria2c ${URL}",
            ),
            "mshta": (
                "mshta $URL",
                'mshta.exe "%SCRIPT_URL%"',
                "mshta ${URL}",
            ),
            "regsvr32": (
                "regsvr32 /i:$URL scrobj.dll",
                'regsvr32 /i:"%URL%" scrobj.dll',
                "regsvr32 /i:${URL} scrobj.dll",
            ),
            "rundll32": (
                "rundll32 url.dll,FileProtocolHandler $URL",
                'rundll32.exe url.dll,FileProtocolHandler "%URL%"',
                "rundll32 url.dll,FileProtocolHandler ${URL}",
            ),
            "ftp": ("ftp $HOST", "ftp.exe %HOST%", "ftp ${HOST}"),
            "tftp": ("tftp $HOST GET payload.exe", "tftp.exe %HOST% PUT payload.exe", "tftp ${HOST} GET payload.exe"),
        }
        for command, command_examples in examples.items():
            for example in command_examples:
                with self.subTest(command=command, example=example), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    package = root / validator.CANONICAL_REL
                    package.mkdir(parents=True)
                    (package / "example.md").write_text(f"```powershell\n{example}\n```\n")
                    check = validator.Validator(root)
                    check.provider_policy()
                    self.assertTrue(any("SDK-composition-only" in item for item in check.errors), check.errors)

    def test_benign_windows_utility_forms_are_allowed(self):
        examples = {
            "certutil": ("certutil -hashfile local.bin SHA256", "certutil -dump local.cer"),
            "aria2c": ("aria2c --version", "aria2c.exe --help"),
            "mshta": ("mshta local.hta", "mshta.exe C:\\tools\\local.hta"),
            "regsvr32": ("regsvr32 local.dll", "regsvr32 /u local.dll"),
            "rundll32": ("rundll32 shell32.dll,Control_RunDLL", "rundll32 local.dll,EntryPoint"),
        }
        for command, command_examples in examples.items():
            for example in command_examples:
                with self.subTest(command=command, example=example), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    package = root / validator.CANONICAL_REL
                    package.mkdir(parents=True)
                    (package / "example.md").write_text(f"```powershell\n{example}\n```\n")
                    check = validator.Validator(root)
                    check.provider_policy()
                    self.assertEqual([], check.errors)

    def test_ordinary_windows_downloader_identifier_substrings_are_allowed(self):
        examples = (
            "certutil_result = sdk_call",
            "aria2c_adapter = sdk_call",
            "mshta_template = sdk_call",
            "regsvr32_result = sdk_call",
            "rundll32_handler = sdk_call",
            "ftp_client_result = sdk_call",
            "tftp_result = sdk_call",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / validator.CANONICAL_REL
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_url_openapi_and_git_literals_are_allowed(self):
        examples = (
            "const docs = 'https://example.test/openapi.json'",
            "openapi: https://example.test/openapi.yaml",
            "git clone https://example.test/repository.git",
        )
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```text\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertEqual([], check.errors)

    def test_connector_authoring_paths_allow_raw_http_primitives(self):
        examples = (
            "requests.get(url)",
            "certutil -urlcache -f https://example.test/a a.exe",
            "const client = await import(moduleName)",
            "client = __import__(module_name)",
        )
        for relative in ("schemas/connector.md", "references/connectors.md"):
            for example in examples:
                with self.subTest(relative=relative, example=example), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    target = root / "skills/machina-agent-builder" / relative
                    target.parent.mkdir(parents=True)
                    target.write_text(f"```text\n{example}\n```\n")
                    check = validator.Validator(root)
                    check.provider_policy()
                    self.assertEqual([], check.errors)

    def test_credential_ellipsis_assignments_fail_for_supported_key_forms(self):
        examples = ('api_key: "..."', '"api-key": "..."', "'token': '...'", "password = '...'",
                    '"secret": ...', "credential: ...")
        for example in examples:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "example.md").write_text(f"```yaml\n{example}\n```\n")
                check = validator.Validator(root)
                check.provider_policy()
                self.assertTrue(any("generic ellipsis placeholder" in item for item in check.errors), check.errors)

    def test_redacted_secret_and_unassigned_credential_variable_are_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "example.md").write_text(
                "```python\ncreate_secrets(data={'api_key': '[REDACTED]'})\n"
                "api_key = vault_context\nprint(api_key)\n```\n"
            )
            check = validator.Validator(root)
            check.provider_policy()
            self.assertEqual([], check.errors)

    def test_trigger_words_only_in_body_do_not_satisfy_frontmatter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / "skills/machina-agent-builder/SKILL.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("---\nname: machina-agent-builder\ndescription: Build things.\n---\n"
                             + " ".join(validator.TRIGGERS))
            check = validator.Validator(root)
            check.frontmatter()
            self.assertTrue(any("frontmatter description" in item for item in check.errors))

    def test_canonical_identity_collision_outside_package_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collision = root / "other/skill.yml"
            collision.parent.mkdir()
            collision.write_text("skill:\n  name: machina-agent-builder\n")
            check = validator.Validator(root)
            check.identities()
            self.assertTrue(any("owned only by" in item for item in check.errors))

    def test_path_traversal_link_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / "skills/machina-agent-builder/SKILL.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("[escape](../../outside.md)\n")
            (root / "outside.md").write_text("outside")
            check = validator.Validator(root)
            check.links()
            self.assertTrue(any("escapes the canonical package" in item for item in check.errors))

    def test_container_inline_traversal_link_fails(self):
        self.assert_reference_escape("> - [escape](../../outside.md)\n")

    def test_inline_image_traversal_fails(self):
        self.assert_reference_escape("![escape](../../outside.png)\n")

    def test_reference_image_traversal_fails(self):
        self.assert_reference_escape("![escape][target]\n\n[target]: ../../outside.png\n")

    def test_inline_image_symlink_escape_fails(self):
        self.assert_image_symlink_escape("![escape](linked/secret.png)\n")

    def test_reference_image_symlink_escape_fails(self):
        self.assert_image_symlink_escape("![escape][target]\n\n[target]: linked/secret.png\n")

    def assert_image_symlink_escape(self, markdown):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / validator.CANONICAL_REL
            package.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "secret.png").write_bytes(b"image")
            (package / "linked").symlink_to(outside, target_is_directory=True)
            (package / "SKILL.md").write_text(markdown)
            check = validator.Validator(root)
            check.links()
            self.assertTrue(any("escapes the canonical package" in item for item in check.errors), check.errors)

    def test_allowed_external_schemes_and_anchor_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / validator.CANONICAL_REL / "SKILL.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("[web](https://example.test) [http](http://example.test) [mail](mailto:a@example.test) [anchor](#section)\n")
            check = validator.Validator(root)
            check.links()
            self.assertEqual([], check.errors)

    def test_disallowed_uri_schemes_and_windows_drive_links_fail(self):
        destinations = ("file:///tmp/a", "data:text/plain,a", "javascript:alert(1)", "ftp://example.test/a", "C:/outside.md", r"C:\outside.md")
        for destination in destinations:
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                guide = root / validator.CANONICAL_REL / "SKILL.md"
                guide.parent.mkdir(parents=True)
                guide.write_text(f"[bad](<{destination}>)\n")
                check = validator.Validator(root)
                check.links()
                self.assertTrue(any("not allowed" in item or "Windows drive" in item for item in check.errors), check.errors)

    def assert_reference_escape(self, link):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guide = root / "skills/machina-agent-builder/SKILL.md"
            guide.parent.mkdir(parents=True)
            guide.write_text(link)
            check = validator.Validator(root)
            check.links()
            self.assertTrue(any("escapes the canonical package" in item for item in check.errors), check.errors)

    def test_reference_style_traversal_fails(self):
        self.assert_reference_escape("[escape][target]\n\n[target]: ../../outside.md 'title'\n")

    def test_unused_escaped_label_reference_definition_fails(self):
        self.assert_reference_escape("[unused\\] label]: ../../outside.md\n")

    def test_matching_escaped_label_reference_fails(self):
        self.assert_reference_escape(
            "[escape][unused\\] label]\n\n[unused\\] label]: ../../outside.md\n"
        )

    def test_percent_encoded_reference_traversal_fails(self):
        self.assert_reference_escape("[escape][]\n\n[escape]: %2e%2e/%2e%2e/outside.md\n")

    def test_angle_bracket_reference_traversal_fails(self):
        self.assert_reference_escape("[escape]\n\n[escape]: <../../outside.md> \"title\"\n")

    def test_multiline_plain_reference_traversal_fails(self):
        self.assert_reference_escape("[escape][target]\n\n[target]:\n  ../../outside.md 'title'\n")

    def test_multiline_angle_reference_traversal_fails(self):
        self.assert_reference_escape("[escape][target]\n\n[target]:\n  <../../outside.md> \"title\"\n")

    def test_multiline_percent_encoded_reference_traversal_fails(self):
        self.assert_reference_escape("[escape][target]\n\n[target]:\n  %2e%2e/%2e%2e/outside.md\n")

    def test_valid_multiline_internal_reference_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "target.md").write_text("target\n")
            (package / "SKILL.md").write_text("[target][ref]\n\n[ref]:\n  target.md 'title'\n")
            check = validator.Validator(root)
            check.links()
            self.assertEqual([], check.errors)

    def test_symlink_escape_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (root / "outside").mkdir()
            (root / "outside/secret.md").write_text("secret")
            (package / "linked").symlink_to(root / "outside", target_is_directory=True)
            (package / "SKILL.md").write_text("[escape][x]\n\n[x]: linked/secret.md\n")
            check = validator.Validator(root)
            check.links()
            self.assertTrue(any("escapes the canonical package" in item for item in check.errors))

    def test_version_mismatch_fails(self):
        self.assertTrue(any("must be equal" in item for item in self.package_version_errors("1.2.3", "1.2.4")))

    def test_missing_version_fails(self):
        self.assertTrue(any("strict SemVer" in item for item in self.package_version_errors(None, "1.2.3")))

    def test_malformed_version_fails(self):
        self.assertTrue(any("strict SemVer" in item for item in self.package_version_errors("v1.2", "v1.2")))

    def package_version_errors(self, setup_version, skill_version):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            (package / "workflows").mkdir(parents=True)
            setup_line = "" if setup_version is None else f"  version: '{setup_version}'\n"
            (package / "_install.yml").write_text("setup:\n  value: skills/machina-agent-builder\n  status: available\n" + setup_line + "datasets: []\n")
            (package / "skill.yml").write_text(f"skill:\n  name: machina-agent-builder\n  status: available\n  version: '{skill_version}'\n  workflows: []\n")
            check = validator.Validator(root)
            check.package(package, True)
            return check.errors

    def test_empty_workflows_fails(self):
        self.assertTrue(any("nonempty" in item for item in workflow_check([], {})))

    def test_unregistered_entrypoint_fails(self):
        errors = workflow_check([{"name": "typo"}], {"primary": (Path("flow"), {"inputs": {}, "outputs": {}})})
        self.assertTrue(any("unregistered" in item for item in errors))

    def test_duplicate_registration_fails(self):
        flow = {"inputs": {}, "outputs": {}}
        errors = workflow_check([{"name": "primary", "inputs": {}, "outputs": {}}] * 2, {"primary": (Path("flow"), flow)})
        self.assertTrue(any("duplicate registrations" in item for item in errors))

    def test_input_mismatch_fails(self):
        errors = workflow_check([{"name": "primary", "inputs": {"wrong": "x"}, "outputs": {}}],
                                {"primary": (Path("flow"), {"inputs": {"actual": "x"}, "outputs": {}})})
        self.assertTrue(any("input keys" in item for item in errors))

    def test_output_reference_mismatch_fails(self):
        errors = workflow_check([{"name": "primary", "inputs": {}, "outputs": {"x": "$.get('wrong')"}}],
                                {"primary": (Path("flow"), {"inputs": {}, "outputs": {"actual": "x"}})})
        self.assertTrue(any("actual workflow output" in item for item in errors))

    def test_installed_workflow_not_exposed_fails(self):
        installed = {name: (Path(name), {"inputs": {}, "outputs": {}}) for name in ("primary", "secondary")}
        errors = workflow_check([{"name": "primary", "inputs": {}, "outputs": {}}], installed)
        self.assertTrue(any("not exposed" in item for item in errors))

    def test_non_mapping_workflow_registration_fails_cleanly(self):
        errors = workflow_check(["bad-entry"], {"primary": (Path("flow"), {"inputs": {}, "outputs": {}})})
        self.assertTrue(any("must be a mapping" in item for item in errors))

    def test_non_mapping_manifest_entries_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            package.mkdir(parents=True)
            (package / "SKILL.md").write_text("guide\n")
            (package / "_install.yml").write_text(
                "setup:\n  value: skills/machina-agent-builder\n  status: available\n  version: '1.2.3'\n"
                "datasets:\n  - bad-dataset\n"
            )
            (package / "skill.yml").write_text(
                "skill:\n  name: machina-agent-builder\n  status: available\n  version: '1.2.3'\n"
                "  references:\n    - bad-reference\n  workflows:\n    - bad-workflow\n"
            )
            check = validator.Validator(root)
            check.package(package, True)
            mapping_errors = [item for item in check.errors if "must be a mapping" in item]
            self.assertEqual(3, len(mapping_errors), check.errors)

    def test_malformed_package_shapes_fail_cleanly(self):
        cases = (
            ("[]\n", "{}\n", "top-level document must be a mapping"),
            ("setup: []\ndatasets: []\n", "skill: []\n", "setup must be a mapping"),
            ("setup: {}\ndatasets:\n  - type: workflow\n    path: 42\n", "skill: {}\n", "path must be a nonempty string"),
            ("setup: {}\ndatasets: []\n", "skill:\n  references:\n    - filename: 42\n", "filename must be a nonempty string"),
        )
        for install, manifest, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "skills/machina-agent-builder"
                package.mkdir(parents=True)
                (package / "_install.yml").write_text(install)
                (package / "skill.yml").write_text(manifest)
                check = validator.Validator(root)
                check.package(package, True)
                self.assertTrue(any(expected in item for item in check.errors), check.errors)

    def test_non_mapping_workflow_document_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "skills/machina-agent-builder"
            (package / "workflows").mkdir(parents=True)
            (package / "_install.yml").write_text(
                "setup: {}\ndatasets:\n  - type: workflow\n    path: workflows/bad.yml\n"
            )
            (package / "skill.yml").write_text("skill: {}\n")
            (package / "workflows/bad.yml").write_text("[]\n")
            check = validator.Validator(root)
            check.package(package, True)
            self.assertTrue(any("workflow document must be a mapping" in item for item in check.errors), check.errors)

    def test_run_handles_non_mapping_manifests_and_missing_alias_guides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (validator.CANONICAL_REL, *validator.ALIAS_RELS):
                package = root / relative
                package.mkdir(parents=True)
                (package / "_install.yml").write_text("[]\n")
                (package / "skill.yml").write_text("[]\n")
            (root / validator.CANONICAL_REL / "SKILL.md").write_text(
                "---\nname: machina-agent-builder\ndescription: test\n---\n"
            )
            check = validator.Validator(root)
            errors = check.run(check_sync=False)
            self.assertTrue(any("top-level document must be a mapping" in item for item in errors), errors)
            self.assertTrue(any("legacy guide is missing or unreadable" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
