#!/usr/bin/env python3
"""Validate the canonical Machina Agent Builder package and its aliases."""

from __future__ import annotations

import re
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    import yaml
except ImportError:
    print("error: PyYAML 6.0.2 is required", file=sys.stderr)
    raise SystemExit(2)
try:
    from markdown_it import MarkdownIt
except ImportError:
    print("error: markdown-it-py 3.0.0 is required", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REL = Path("skills/machina-agent-builder")
ALIAS_RELS = (Path("skills/mkn-constructor"), Path("mkn-constructor"))
TRIGGERS = ("create", "scaffold", "update", "validate", "analyze", "trace", "debug", "install",
            "maintain", "agents", "agent templates", "workflows", "connectors", "prompts", "mappings",
            "documents", "skills", "mcp-backed")
ORDER = {"connector": 0, "document": 1, "documents": 1, "prompt": 2, "prompts": 2,
         "mapping": 3, "mappings": 3, "workflow": 4, "agent": 5, "skill": 6}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
                    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
                    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")


def first_frontmatter(text: str) -> tuple[object | None, str | None]:
    """Return the actual leading YAML frontmatter document and an error."""
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        return None, "must begin with a --- delimited YAML frontmatter block"
    try:
        return yaml.safe_load(match.group(1)), None
    except yaml.YAMLError as exc:
        return None, f"frontmatter is invalid YAML: {exc}"


MARKDOWN = MarkdownIt("commonmark")
# Preserve unsafe-scheme destinations so the validator can report a controlled
# policy error instead of markdown-it silently dropping their tokens.
MARKDOWN.validateLink = lambda _url: True


def active_code_blocks(text: str):
    """Yield CommonMark code blocks as ``(kind, info, content)`` tuples."""
    for token in MARKDOWN.parse(text):
        if token.type == "fence":
            yield "fenced", token.info.strip(), token.content
        elif token.type == "code_block":
            yield "indented", "", token.content


def yaml_fences(text: str):
    for kind, info, block in active_code_blocks(text):
        first_token = info.split(None, 1)[0].lower() if info else ""
        if kind == "fenced" and first_token in {"yaml", "yml"}:
            yield block


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def vertex_errors(text: str) -> list[str]:
    """Check active YAML examples, ignoring connector definitions without command."""
    failures = []
    yaml_blocks = []
    for kind, info, block in active_code_blocks(text):
        first_token = info.split(None, 1)[0].lower() if info else ""
        if kind == "fenced" and first_token in {"yaml", "yml"}:
            yaml_blocks.append(("YAML fence", block, True))
        elif kind == "indented":
            yaml_blocks.append(("indented code block", block, False))
    for fence_number, (label, block, explicitly_yaml) in enumerate(yaml_blocks, 1):
        try:
            docs = list(yaml.safe_load_all(block))
        except yaml.YAMLError as exc:
            if explicitly_yaml:
                failures.append(f"{label} {fence_number} is invalid YAML: {exc}")
            continue
        for doc in docs:
            for node in walk(doc):
                if not isinstance(node, dict) or node.get("name") != "google-genai" or "command" not in node:
                    continue
                missing = []
                if node.get("location") != "global":
                    missing.append("location: global")
                if node.get("provider") != "vertex_ai":
                    missing.append("provider: vertex_ai")
                if missing:
                    failures.append(f"{label} {fence_number} google-genai command {node.get('command')!r} "
                                    f"must include {', '.join(missing)} in the same connector mapping")
    return failures


def markdown_destinations(text: str):
    """Extract rendered links and all CommonMark reference definitions."""
    env = {}
    tokens = MARKDOWN.parse(text, env)
    for token in tokens:
        candidates = token.children or (token,)
        for child in candidates:
            attribute = {"link_open": "href", "image": "src"}.get(child.type)
            if attribute is not None:
                destination = child.attrGet(attribute)
                if destination is not None:
                    yield destination
    for reference in env.get("references", {}).values():
        href = reference.get("href")
        if href is not None:
            yield href


class Validator:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.canonical = self.root / CANONICAL_REL
        self.aliases = tuple(self.root / item for item in ALIAS_RELS)
        self.errors: list[str] = []

    def error(self, path: Path, message: str) -> None:
        try:
            shown = path.absolute().relative_to(self.root)
        except ValueError:
            shown = path
        self.errors.append(f"{shown}: {message}")

    def safe_package_tree(self, path: Path) -> bool:
        """Reject unsafe package roots/entries without traversing symlinks."""
        if path.is_symlink():
            self.error(path, "package root must not be a symlink")
            return False
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
        except FileNotFoundError:
            self.error(path, "package directory is missing; run the compatibility sync")
            return False
        except (OSError, RuntimeError) as exc:
            self.error(path, f"package root cannot be resolved safely: {exc}")
            return False
        except ValueError:
            self.error(path, "package root resolves outside the repository root")
            return False
        if not resolved.is_dir():
            self.error(path, "package directory is missing; run the compatibility sync")
            return False

        safe = True
        pending = [path]
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        item = Path(entry.path)
                        if entry.is_symlink():
                            self.error(item, "symlinks are not allowed in package trees")
                            safe = False
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(item)
            except OSError as exc:
                self.error(directory, f"package tree is unreadable: {exc}")
                safe = False
        return safe

    def load(self, path: Path):
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            self.error(path, f"invalid YAML: {exc}")
            return None

    def read_text(self, path: Path, purpose: str = "text file") -> str | None:
        """Read validator-owned UTF-8 text without aborting the validation run."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self.error(path, f"{purpose} is missing or unreadable: {exc}")
            return None

    def package_file(self, package: Path, relative: str, owner: Path, field: str) -> Path | None:
        """Resolve a declared package file and enforce the package boundary first."""
        if "\\" in relative:
            self.error(owner, f"{field} must use POSIX '/' separators: {relative!r}")
            return None
        candidate = Path(relative)
        if candidate.is_absolute():
            self.error(owner, f"{field} must be relative to the package: {relative!r}")
            return None
        boundary = package.resolve()
        try:
            resolved = (package / candidate).resolve()
            resolved.relative_to(boundary)
        except (OSError, RuntimeError) as exc:
            self.error(owner, f"{field} cannot be resolved safely: {relative!r}: {exc}")
            return None
        except ValueError:
            self.error(owner, f"{field} escapes the resolved package root: {relative!r}")
            return None
        if not resolved.is_file():
            self.error(owner, f"{field} target is missing or not a file: {relative!r}")
            return None
        return resolved

    def package(self, path: Path, canonical: bool, *, tree_safe: bool | None = None) -> None:
        if tree_safe is None:
            tree_safe = self.safe_package_tree(path)
        if not tree_safe:
            return
        install = self.load(path / "_install.yml")
        manifest = self.load(path / "skill.yml")
        if not isinstance(install, dict):
            self.error(path / "_install.yml", f"top-level document must be a mapping, found {type(install).__name__}")
            install = {}
        if not isinstance(manifest, dict):
            self.error(path / "skill.yml", f"top-level document must be a mapping, found {type(manifest).__name__}")
            manifest = {}
        setup, skill = install.get("setup", {}), manifest.get("skill", {})
        if not isinstance(setup, dict):
            self.error(path / "_install.yml", f"setup must be a mapping, found {type(setup).__name__}")
            setup = {}
        if not isinstance(skill, dict):
            self.error(path / "skill.yml", f"skill must be a mapping, found {type(skill).__name__}")
            skill = {}
        slug = "machina-agent-builder" if canonical else "mkn-constructor"
        expected = {"setup.value": (setup.get("value"), f"skills/{slug}"),
                    "skill.name": (skill.get("name"), slug)}
        for field, (actual, wanted) in expected.items():
            if actual != wanted:
                self.error(path, f"{field} must be {wanted!r}, found {actual!r}")
        for field, value in (("setup.status", setup.get("status")), ("skill.status", skill.get("status"))):
            if value != "available":
                self.error(path, f"{field} must be schema-valid 'available', found {value!r}")
        versions = (("setup.version", setup.get("version")), ("skill.version", skill.get("version")))
        for field, version in versions:
            if not isinstance(version, str) or not version or not SEMVER.fullmatch(version):
                self.error(path, f"{field} must be a nonempty strict SemVer string, found {version!r}")
        if setup.get("version") != skill.get("version"):
            self.error(path, "setup.version and skill.version must be equal")
        if not canonical:
            title = f"{setup.get('title', '')} {skill.get('title', '')}".lower()
            descriptions = f"{setup.get('description', '')} {skill.get('description', '')}".lower()
            guide_text = self.read_text(path / "SKILL.md", "legacy guide")
            guide = guide_text.lower() if guide_text is not None else ""
            if "deprecated" not in title:
                self.error(path, "legacy setup/skill titles must mark this as deprecated")
            if "deprecated compatibility alias" not in descriptions or "machina-agent-builder" not in descriptions:
                self.error(path, "legacy descriptions must say deprecated compatibility alias and name machina-agent-builder")
            if "deprecated" not in guide or "machina-agent-builder" not in guide:
                self.error(path / "SKILL.md", "legacy guide must contain a deprecation notice naming machina-agent-builder")
        datasets = install.get("datasets")
        installed_workflows = {}
        if not isinstance(datasets, list):
            self.error(path / "_install.yml", "datasets must be a list")
        else:
            ranks = []
            for index, dataset in enumerate(datasets):
                if not isinstance(dataset, dict):
                    self.error(path / "_install.yml", f"datasets[{index}] must be a mapping, found {type(dataset).__name__}")
                    continue
                dtype, relative = dataset.get("type"), dataset.get("path")
                if dtype not in ORDER:
                    self.error(path / "_install.yml", f"datasets[{index}].type unsupported: {dtype!r}")
                    continue
                ranks.append(ORDER[dtype])
                if not isinstance(relative, str) or not relative:
                    self.error(path / "_install.yml", f"datasets[{index}].path must be a nonempty string, found {relative!r}")
                else:
                    resolved = self.package_file(path, relative, path / "_install.yml", f"datasets[{index}].path")
                    if resolved is None:
                        continue
                    if dtype != "workflow":
                        continue
                    document = self.load(resolved)
                    if not isinstance(document, dict):
                        self.error(resolved, f"workflow document must be a mapping, found {type(document).__name__}")
                        document = {}
                    flow = document.get("workflow", {})
                    name = flow.get("name") if isinstance(flow, dict) else None
                    if not isinstance(name, str) or not name:
                        self.error(resolved, "workflow.name must be a nonempty string")
                    elif name in installed_workflows:
                        self.error(path / "_install.yml", f"duplicate installed workflow name: {name!r}")
                    else:
                        installed_workflows[name] = (resolved, flow)
            if ranks != sorted(ranks):
                self.error(path / "_install.yml", "datasets must be dependency-ordered")
        references = skill.get("references", [])
        if not isinstance(references, list):
            self.error(path / "skill.yml", "skill.references must be a list")
            references = []
        for index, reference in enumerate(references):
            if not isinstance(reference, dict):
                self.error(path / "skill.yml", f"skill.references[{index}] must be a mapping, found {type(reference).__name__}")
                continue
            filename = reference.get("filename")
            if not isinstance(filename, str) or not filename:
                self.error(path / "skill.yml", f"skill.references[{index}].filename must be a nonempty string, found {filename!r}")
            else:
                self.package_file(path, filename, path / "skill.yml", f"skill.references[{index}].filename")
        self.workflows(path, skill, installed_workflows, f"{slug}-check-setup")

    def workflows(self, path: Path, skill: dict, installed: dict, primary: str) -> None:
        registrations = skill.get("workflows")
        if not isinstance(registrations, list) or not registrations:
            self.error(path / "skill.yml", "skill.workflows must be a nonempty list")
            return
        names = [item.get("name") if isinstance(item, dict) else None for item in registrations]
        for index, item in enumerate(registrations):
            if not isinstance(item, dict):
                self.error(path / "skill.yml", f"skill.workflows[{index}] must be a mapping, found {type(item).__name__}")
        string_names = [name for name in names if isinstance(name, str)]
        if len(string_names) != len(set(string_names)):
            self.error(path / "skill.yml", "skill.workflows contains duplicate registrations")
        if primary not in installed:
            self.error(path / "_install.yml", f"expected primary workflow is not installed: {primary!r}")
        registered = set(string_names)
        installed_names = set(installed)
        for name in sorted(registered - installed_names):
            self.error(path / "skill.yml", f"unregistered workflow entrypoint: {name!r}")
        for name in sorted(installed_names - registered):
            self.error(path / "skill.yml", f"installed workflow is not exposed: {name!r}")
        for registration in registrations:
            if not isinstance(registration, dict) or registration.get("name") not in installed:
                continue
            name = registration["name"]
            flow = installed[name][1]
            skill_inputs, actual_inputs = registration.get("inputs"), flow.get("inputs")
            if not isinstance(skill_inputs, dict) or not isinstance(actual_inputs, dict) or set(skill_inputs) != set(actual_inputs):
                self.error(path / "skill.yml", f"workflow {name!r} skill input keys must exactly match workflow input keys")
            mappings, actual_outputs = registration.get("outputs"), flow.get("outputs")
            if not isinstance(mappings, dict) or not isinstance(actual_outputs, dict):
                self.error(path / "skill.yml", f"workflow {name!r} outputs must be mappings")
                continue
            referenced = []
            for exposed, expression in mappings.items():
                match = re.fullmatch(r"\$\.get\((['\"])([^'\"]+)\1(?:,\s*.*)?\)", expression) if isinstance(expression, str) else None
                if not match or match.group(2) not in actual_outputs:
                    self.error(path / "skill.yml", f"workflow {name!r} output {exposed!r} must $.get(...) an actual workflow output")
                else:
                    referenced.append(match.group(2))
            if sorted(referenced) != sorted(actual_outputs) or len(referenced) != len(set(referenced)):
                self.error(path / "skill.yml", f"workflow {name!r} must expose every actual workflow output exactly once")

    def frontmatter(self) -> None:
        path = self.canonical / "SKILL.md"
        text = self.read_text(path, "canonical guide")
        if text is None:
            return
        data, problem = first_frontmatter(text)
        if problem:
            self.error(path, problem)
            return
        if not isinstance(data, dict) or set(data) != {"name", "description"}:
            self.error(path, "frontmatter must contain exactly name and description")
            return
        if data.get("name") != "machina-agent-builder":
            self.error(path, "frontmatter name must be 'machina-agent-builder'")
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            self.error(path, "frontmatter description must be a nonempty string")
            return
        lowered = description.lower()
        for term in TRIGGERS:
            if term not in lowered:
                self.error(path, f"frontmatter description is missing discovery trigger {term!r}")

    def identities(self, excluded: tuple[Path, ...] = ()) -> None:
        allowed = {
            "setup.value": {"skills/machina-agent-builder": {CANONICAL_REL / "_install.yml"},
                            "skills/mkn-constructor": {item / "_install.yml" for item in ALIAS_RELS}},
            "skill.name": {"machina-agent-builder": {CANONICAL_REL / "skill.yml"},
                           "mkn-constructor": {item / "skill.yml" for item in ALIAS_RELS}},
            "workflow.name": {"machina-agent-builder-check-setup": {CANONICAL_REL / "workflows/check-setup.yml"},
                              "mkn-constructor-check-setup": {item / "workflows/check-setup.yml" for item in ALIAS_RELS}},
        }
        for path in sorted((*self.root.rglob("*.yml"), *self.root.rglob("*.yaml"))):
            if any(path == package or package in path.parents for package in excluded):
                continue
            relative = path.relative_to(self.root)
            try:
                data = yaml.safe_load(path.read_text())
            except (OSError, UnicodeError, yaml.YAMLError):
                # Identity ownership is intentionally independent of unrelated YAML validity.
                continue
            if not isinstance(data, dict):
                continue
            candidates = (("setup.value", data.get("setup", {}).get("value") if isinstance(data.get("setup"), dict) else None),
                          ("skill.name", data.get("skill", {}).get("name") if isinstance(data.get("skill"), dict) else None),
                          ("workflow.name", data.get("workflow", {}).get("name") if isinstance(data.get("workflow"), dict) else None))
            for field, value in candidates:
                if value in allowed[field] and relative not in allowed[field][value]:
                    expected = ", ".join(map(str, sorted(allowed[field][value])))
                    self.error(path, f"{field} identity {value!r} is owned only by: {expected}")

    def links(self) -> None:
        boundary = self.canonical.resolve()
        for path in sorted(self.canonical.rglob("*.md")):
            text = self.read_text(path, "Markdown file")
            if text is None:
                continue
            for raw in markdown_destinations(text):
                target = unquote(raw).split("#", 1)[0]
                if not target:
                    continue
                if re.match(r"^[A-Za-z]:[\\/]", target):
                    self.error(path, f"local Markdown link must not use a Windows drive path: {raw!r}")
                    continue
                scheme = re.match(r"^([a-z][a-z0-9+.-]*):", target, re.I)
                if scheme:
                    if scheme.group(1).lower() not in {"http", "https", "mailto"}:
                        self.error(path, f"Markdown link URI scheme is not allowed: {raw!r}")
                    continue
                if Path(target).is_absolute():
                    self.error(path, f"local Markdown link must not be absolute: {raw!r}")
                    continue
                resolved = (path.parent / target).resolve()
                try:
                    resolved.relative_to(boundary)
                except ValueError:
                    self.error(path, f"local Markdown link escapes the canonical package: {raw!r}")
                    continue
                if not resolved.exists():
                    self.error(path, f"local Markdown link target does not exist: {raw!r}")

    def provider_policy(self) -> None:
        banned = re.compile(r"openai|gpt(?:-|\b)|machina-ai", re.I)
        unsafe_secret = re.compile(r"GOOGLE_GENAI_API_KEY|sk-\.\.\.|your-api-key", re.I)
        direct_client_api = re.compile(r"MACHINA_CLIENT_URL|X-Api-Token", re.I)
        remote_operand = (r'''[\'"]?(?:https?://|ftp://|\$(?:[A-Za-z_][A-Za-z0-9_]*'''
                          r'''|\{[A-Za-z_][A-Za-z0-9_]*\})|%[A-Za-z_][A-Za-z0-9_]*%)[\'"]?''')
        raw_http = re.compile(
            rf"(?imx)"
            r"(?<![A-Za-z0-9_])"
            r"(?:fetch|axios|requests|httpx|aiohttp|urllib3?|got|ky|superagent|undici|XMLHttpRequest)"
            r"(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])http\s*\.\s*client(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])node:https?(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])https?(?![A-Za-z0-9_]|://)|"
            r"(?<![A-Za-z0-9_])(?:curl|wget|iwr|irm)(?![A-Za-z0-9_])|"
            r"\bInvoke-(?:WebRequest|RestMethod)\b|"
            r"(?<![A-Za-z0-9_])(?:System\.)?Net\."
            r"(?:WebClient|Http\.HttpClient|WebRequest|HttpWebRequest)(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])(?:Start-BitsTransfer|Import-Module(?:\s+-Name)?\s+['\"]?BitsTransfer['\"]?)"
            r"(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])bitsadmin(?:\.exe)?(?![A-Za-z0-9_])"
            r"[^\r\n]*(?:/transfer|/download)(?![A-Za-z0-9_])|"
            r"(?<![A-Za-z0-9_])certutil(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*-(?:urlcache|verifyctl)(?![A-Za-z0-9_])[^\r\n]*{remote_operand}|"
            r"(?<![A-Za-z0-9_])aria2c(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*{remote_operand}|"
            r"(?<![A-Za-z0-9_])mshta(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*(?:{remote_operand}|(?:java|vb)script:)|"
            r"(?<![A-Za-z0-9_])regsvr32(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*/i:\s*{remote_operand}|"
            r"(?<![A-Za-z0-9_])rundll32(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*url\.dll\s*,\s*FileProtocolHandler\s+{remote_operand}|"
            r"(?<![A-Za-z0-9_])ftp(?:\.exe)?(?![A-Za-z0-9_])['\"]?\s+"
            rf"(?:-[^\s\r\n]+\s+)*(?:{remote_operand}|[A-Za-z0-9][^\s\r\n]*)|"
            r"(?<![A-Za-z0-9_])tftp(?:\.exe)?(?![A-Za-z0-9_])"
            rf"[^\r\n]*?(?:{remote_operand}|[A-Za-z0-9][^\s\r\n]*)\s+(?:get|put)\s+[^\r\n]+|"
            r"\.\s*['\"]?(?:DownloadString|DownloadFile|UploadString|UploadFile|OpenRead)"
            r"['\"]?(?![A-Za-z0-9_])|"
            r"\.\s*(?:\(\s*)?['\"]?(?:GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync|SendAsync|"
            r"GetStringAsync|GetByteArrayAsync|GetStreamAsync|GetResponse|GetResponseAsync)"
            r"['\"]?(?:\s*\))?(?![A-Za-z0-9_])|"
            r"\bwget\s*\("
        )
        credential_ellipsis = re.compile(
            r'''(?im)(?:["']?(?:api[_-]key|token|password|secret|credential)["']?)'''
            r'''\s*(?::|=)\s*(?:["']\.\.\.["']|\.\.\.)(?!\.)'''
        )
        computed_module_loader = re.compile(
            r'''(?x)(?<![A-Za-z0-9_])(?:import|require|__import__)\s*\(\s*'''
            r'''(?!(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*(?:,|\)))'''
            r'''(?=\S)'''
        )

        def computed_loader_match(block: str):
            for candidate in computed_module_loader.finditer(block):
                line_prefix = block[block.rfind("\n", 0, candidate.start()) + 1:candidate.start()]
                if not re.match(r"^\s*(?:#|//)", line_prefix):
                    return candidate
            return None
        for path in sorted(self.canonical.rglob("*.md")):
            text = self.read_text(path, "Markdown file")
            if text is None:
                continue
            for failure in vertex_errors(text):
                self.error(path, failure)
            connector_authoring = path.relative_to(self.canonical).as_posix() in {
                "schemas/connector.md", "references/connectors.md"
            }
            for number, (kind, _, block) in enumerate(active_code_blocks(text), 1):
                label = f"active {kind} code block {number}"
                match = banned.search(block)
                if match:
                    self.error(path, f"{label} contains banned provider term {match.group(0)!r}")
                secret = unsafe_secret.search(block)
                if secret:
                    self.error(path, f"{label} contains obsolete or unsafe credential example {secret.group(0)!r}; use Vertex TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL / TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID Vault references and [REDACTED] values")
                client_api = direct_client_api.search(block)
                if client_api:
                    self.error(path, f"{label} violates SDK-composition-only policy with direct Client API token/proxy marker {client_api.group(0)!r}; use existing MCP/SDK resources or explicitly reject unsupported intents")
                primitive = None if connector_authoring else raw_http.search(block)
                if primitive:
                    self.error(path, f"{label} violates SDK-composition-only policy with raw HTTP client primitive {primitive.group(0)!r}; use existing MCP/SDK resources or explicitly reject unsupported intents")
                computed_loader = None if connector_authoring else computed_loader_match(block)
                if computed_loader:
                    self.error(path, f"{label} violates SDK-composition-only policy with computed module-loader call {computed_loader.group(0).strip()!r}; module-loader arguments must be simple string literals")
                placeholder = credential_ellipsis.search(block)
                if placeholder:
                    self.error(path, f"{label} assigns a generic ellipsis placeholder to a credential-bearing field; credentials must use Vault-backed context variables, with [REDACTED] reserved for create_secrets examples")
        for path in sorted((*self.canonical.rglob("*.yml"), *self.canonical.rglob("*.yaml"))):
            text = self.read_text(path, "provider-policy YAML file")
            if text is None:
                continue
            match = banned.search(text)
            if match:
                self.error(path, f"manifest contains banned provider term {match.group(0)!r}")

    def run(self, check_sync: bool = True) -> list[str]:
        package_safety = {path: self.safe_package_tree(path) for path in (self.canonical, *self.aliases)}
        self.package(self.canonical, True, tree_safe=package_safety[self.canonical])
        for alias in self.aliases:
            self.package(alias, False, tree_safe=package_safety[alias])
        canonical_manifest = self.load(self.canonical / "skill.yml") if package_safety[self.canonical] else None
        canonical_skill = canonical_manifest.get("skill") if isinstance(canonical_manifest, dict) else None
        canonical_version = canonical_skill.get("version") if isinstance(canonical_skill, dict) else None
        for alias in self.aliases:
            if not package_safety[alias]:
                continue
            alias_manifest = self.load(alias / "skill.yml")
            alias_skill = alias_manifest.get("skill") if isinstance(alias_manifest, dict) else None
            alias_version = alias_skill.get("version") if isinstance(alias_skill, dict) else None
            if alias_version != canonical_version:
                self.error(alias / "skill.yml", f"alias version {alias_version!r} must match canonical version {canonical_version!r}")
        if package_safety[self.canonical]:
            self.frontmatter()
        unsafe_packages = tuple(path for path, safe in package_safety.items() if not safe)
        self.identities(excluded=unsafe_packages)
        if package_safety[self.canonical]:
            self.links()
            self.provider_policy()
        if check_sync:
            sync = subprocess.run([sys.executable, str(self.root / "scripts/sync-machina-agent-builder-compat.py"), "--check"],
                                  cwd=self.root, text=True, capture_output=True)
            if sync.returncode:
                self.error(self.root / "scripts/sync-machina-agent-builder-compat.py",
                           sync.stderr.strip() or "compatibility parity check failed")
        if all(package_safety[path] for path in self.aliases):
            snapshots = []
            for path in self.aliases:
                snapshot = {}
                for item in path.rglob("*"):
                    if not item.is_file():
                        continue
                    try:
                        snapshot[str(item.relative_to(path))] = item.read_bytes()
                    except OSError as exc:
                        self.error(item, f"alias snapshot file is unreadable: {exc}")
                snapshots.append(snapshot)
            if snapshots[0] != snapshots[1]:
                self.error(self.aliases[1], "legacy trees must be byte-identical")
        return self.errors


def main() -> int:
    errors = Validator(ROOT).run()
    if errors:
        for item in errors:
            print(f"error: {item}", file=sys.stderr)
        print(f"machina-agent-builder validation failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("machina-agent-builder validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
