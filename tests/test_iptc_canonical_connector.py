"""The thin shared canonical connector (PR3-D, Amendment B §B15 / plan tasks 9-10).

Run from the repository root:

    python3 tests/test_iptc_canonical_connector.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**What this suite is for.** §B15's PR3-D exit criterion says the shared pyscript
connector "contains no canonical vocabulary or serialization logic". That is a
negative, and negatives rot silently: the connector that starts as four
delegating functions is exactly the file someone later inlines a status-string
table into, because inlining it is always the smaller diff than fixing the seam.
So the no-vocabulary rule is read off the connector's own source and import
graph, not off a review comment.

The second half is §B13. A preflight that refuses *after* the request has gone
out has failed at the only thing it exists to do, so the refusal cases here count
adapter invocations rather than trusting the ordering of statements in a
function. The counter is installed on the package's adapter modules — the real
provider-call surface the connector reaches — and the assertion is exactly zero,
never "at most one".

**Scope honesty.** Nothing here calls a provider. Every rights answer in this
tree is synthetic ``prototype_only`` evidence (§B10), so a refusal proven here is
a proof about the gate, not a licence position.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SUPPORT_PATH = REPO_ROOT / "tests/iptc_canonical_support.py"
_spec = importlib.util.spec_from_file_location("iptc_canonical_support", _SUPPORT_PATH)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


#: The four operations §B15 gives the connector, and nothing else. A fifth
#: command is a seam growing a second job.
DECLARED_COMMANDS = (
    "provider_preflight",
    "canonicalize_event",
    "validate_event",
    "capability_rights_gate",
)

#: The package symbols the connector must reach through rather than reimplement.
DELEGATED_SYMBOLS = (
    "canonical_envelope",
    "check_compatibility",
    "rights_findings",
    "surrogate_resolver",
)

#: The four §B11 provider namespaces. A namespace outside this list is refused.
ALLOWED_PROVIDERS = tuple(sorted(support.FOUR_PROVIDER_LEGS))

#: A property literal from either vocabulary, as a document spells it. Matching
#: on the prefix plus a name is deliberate: the *words* "sport" and "schema"
#: appear in any honest description of this connector, and a matcher that fired
#: on them would be the false-positive generator plan task 1 already forbids.
VOCABULARY_LITERAL = re.compile(r"""["'](?:sport|schema|machina):[A-Za-z]""")


def connector_source() -> str:
    if not support.CONNECTOR_PYSCRIPT.is_file():
        raise AssertionError(
            "PR3-D shared connector pyscript is absent: {0}".format(
                support.CONNECTOR_PYSCRIPT.relative_to(REPO_ROOT)))
    return support.CONNECTOR_PYSCRIPT.read_text(encoding="utf-8")


def connector_declaration() -> dict:
    if not support.CONNECTOR_YAML.is_file():
        raise AssertionError(
            "PR3-D shared connector declaration is absent: {0}".format(
                support.CONNECTOR_YAML.relative_to(REPO_ROOT)))
    return support.read_yaml(support.CONNECTOR_YAML)


def connector_module():
    """The pyscript, executed the way the client-api executor execs it.

    ``core.connector.executor.connector_script`` execs the sidecar in-process
    against the interpreter's own site-packages, so the canonical package is
    registered under its distribution import name first. Loading it any other way
    would prove something about a different environment than production.
    """
    support.canonical_package()
    source_path = support.CONNECTOR_PYSCRIPT
    if not source_path.is_file():
        raise AssertionError(
            "PR3-D shared connector pyscript is absent: {0}".format(
                source_path.relative_to(REPO_ROOT)))
    spec = importlib.util.spec_from_file_location(
        "machina_sports_canonical_connector", source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(module, command: str, **params):
    """Invoke a command the way the executor does, and unwrap it the way a
    workflow task does.

    Two conventions this repository already has, and both are part of the
    contract rather than decoration: the executor passes workflow inputs under
    ``params``, and a task's ``$`` is the stripped ``data`` payload, not the
    ``{status, data}`` envelope. A test that called the function with a flat dict
    and read the envelope directly would pass here and fail in the pod.
    """
    result = getattr(module, command)({"params": params})
    assert set(result) == {"status", "data"}, result
    return result["data"]


def declared_command_values(declaration: dict) -> list:
    return [entry.get("value")
            for entry in declaration.get("connector", {}).get("commands", [])]


def module_functions(source: str) -> set:
    tree = ast.parse(source)
    return {node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


class TestTheConnectorExistsAndIsAPyscript(unittest.TestCase):
    """PR3-D task 9's first requirement, and the one every other case needs."""

    def test_connector_declaration_and_pyscript_exist(self):
        for path in (support.CONNECTOR_YAML, support.CONNECTOR_PYSCRIPT):
            with self.subTest(path=path.name):
                self.assertTrue(
                    path.is_file(),
                    "absent: {0}".format(path.relative_to(REPO_ROOT)))

    def test_the_connector_ships_the_install_manifest_the_convention_requires(self):
        """Every connector directory in this repository carries one, and a
        cross-template reference installs through it. A connector without it is a
        connector no pod can install, which no amount of green unit tests fixes."""
        self.assertTrue(support.CONNECTOR_INSTALL.is_file())
        datasets = support.read_yaml(support.CONNECTOR_INSTALL)["datasets"]
        self.assertEqual([entry["path"] for entry in datasets],
                         [support.CONNECTOR_YAML.name])

    def test_the_declaration_names_the_pyscript_sidecar_it_ships(self):
        """The importer stores one sidecar per connector and execs it by the name
        the declaration gives. A declaration naming a file that is not there is a
        connector that imports clean and fails at the first call."""
        connector = connector_declaration()["connector"]
        self.assertEqual(connector.get("filetype"), "pyscript")
        self.assertEqual(connector.get("filename"),
                         support.CONNECTOR_PYSCRIPT.name)
        self.assertEqual(connector.get("name"), "machina-sports-canonical")


class TestDeclaredCommandsExist(unittest.TestCase):
    """Task 9 case 1. Declaration and implementation are two files, and only a
    test makes them one contract."""

    def test_the_declaration_declares_exactly_the_four_operations(self):
        self.assertEqual(sorted(declared_command_values(connector_declaration())),
                         sorted(DECLARED_COMMANDS))

    def test_every_declared_command_is_a_function_in_the_pyscript(self):
        functions = module_functions(connector_source())
        for command in declared_command_values(connector_declaration()):
            with self.subTest(command=command):
                self.assertIn(command, functions)

    def test_the_pyscript_exposes_no_undeclared_public_command(self):
        """A public function nobody declared is a command the connector answers
        and the declaration does not admit to."""
        public = {name for name in module_functions(connector_source())
                  if not name.startswith("_")}
        self.assertEqual(sorted(public), sorted(DECLARED_COMMANDS))


class TestTheConnectorOwnsNoVocabulary(unittest.TestCase):
    """Task 9 case 2, and the §B15 exit criterion stated as an executable rule.

    The seam exists so there is one place that knows what ``sport:status`` means.
    A connector that also knows is a second place, and two places is the drift
    this programme was opened to remove.
    """

    def test_the_pyscript_contains_no_iptc_property_literal(self):
        offenders = []
        for number, line in enumerate(connector_source().splitlines(), start=1):
            if VOCABULARY_LITERAL.search(line):
                offenders.append("{0}:{1}".format(number, line.strip()))
        self.assertEqual(offenders, [])

    def test_the_pyscript_implements_no_serialization(self):
        """Delegating to ``canonical_envelope`` is the point; defining a second
        one beside it is the failure."""
        defined = module_functions(connector_source())
        for owned_by_the_package in ("canonical_envelope", "event_view",
                                     "sport_schema_graph", "capability_report",
                                     "rights_findings", "check_compatibility"):
            with self.subTest(symbol=owned_by_the_package):
                self.assertNotIn(owned_by_the_package, defined)

    def test_the_pyscript_reads_no_json_resource_from_the_filesystem(self):
        """The JSON resources load from the installed package (task 9's stop
        condition). A connector reaching the filesystem for them is a connector
        that works in the repository and fails in the image."""
        source = connector_source()
        for banned in ("official-property-names.json", "shared-context.json",
                       "__file__"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class TestTheConnectorDelegatesToThePackage(unittest.TestCase):
    """Task 9 case 3, asserted on the import graph rather than by mocking.

    A mock proves the test called what the test set up. Reading the imports and
    the call names proves what the file will do inside ``connector_script``.
    """

    def setUp(self):
        self.source = connector_source()
        self.tree = ast.parse(self.source)

    def imported_roots(self):
        roots = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                roots.append((node.module or "").split(".")[0])
        return roots

    def test_the_connector_imports_the_canonical_package(self):
        self.assertIn(support.PACKAGE_NAME, self.imported_roots())

    def test_the_connector_imports_nothing_from_this_repository(self):
        """``tools.*`` is repository tooling and is not in the image. An import
        of it would pass here and ``ModuleNotFoundError`` in production."""
        for banned in ("tools", "agent_templates", "connectors"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.imported_roots())

    def test_the_delegated_package_symbols_are_actually_called(self):
        called = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    called.add(function.id)
                elif isinstance(function, ast.Attribute):
                    called.add(function.attr)
        for symbol in DELEGATED_SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, called)

    def test_the_crosswalk_is_injected_and_not_embedded(self):
        """§B12: the consumer passes its own crosswalk in. A crosswalk table
        living in the connector would be a second copy of identity, owned by
        the one component forbidden to own any."""
        self.assertNotIn("urn:machina:sports:event:", self.source)


class TestTheConnectorIsNotAServiceOrACli(unittest.TestCase):
    """Task 9 case 5. The sidecar is exec'd in-process by the executor; a
    ``__main__`` block or a loop turns one workflow task into a second lifetime
    inside the API worker."""

    def setUp(self):
        self.source = connector_source()

    def test_there_is_no_main_entrypoint(self):
        self.assertNotIn("__main__", self.source)

    def test_there_is_no_server_or_scheduler_construct(self):
        for banned in ("while True", "asyncio.run", "uvicorn", "Flask",
                       "serve_forever", "schedule.every"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.source)


class TestProviderPreflightRefusesBeforeRetrieval(unittest.TestCase):
    """Task 10 and §B13. The refusal has to cost nothing, and "nothing" is a
    number this suite reads off the adapter surface rather than off the code."""

    def setUp(self):
        self.module = connector_module()
        self.calls = []
        adapters = support.canonical_module("adapters")
        for name in ("api_football", "sportradar_soccer", "stats_perform_opta"):
            adapter = importlib.import_module(
                "{0}.adapters.{1}".format(support.PACKAGE_NAME, name))
            if not hasattr(adapter, "to_observation"):
                continue
            original = adapter.to_observation
            self.addCleanup(setattr, adapter, "to_observation", original)
            setattr(adapter, "to_observation", self._counting(name, original))
        self.assertTrue(adapters is not None)

    def _counting(self, name, original):
        def counted(*arguments, **keywords):
            self.calls.append(name)
            return original(*arguments, **keywords)
        return counted

    def test_production_tier_refuses_every_prototype_only_provider(self):
        for provider in ALLOWED_PROVIDERS:
            with self.subTest(provider=provider):
                result = call(self.module, "provider_preflight",
                              provider=provider, consumer_tier="production",
                              requires=list(support.CANARY_REQUIRES))
                self.assertFalse(result.get("allowed"), result)
                self.assertTrue(result.get("refusals"), result)
                self.assertEqual(self.calls, [])

    def test_zero_provider_calls_are_made_when_the_gate_refuses(self):
        """§B13, and the reason it is a counter rather than a code review: a
        refusal that happens after the request has gone out has failed at the
        only thing it exists to do. The payload here is deliberately valid
        enough to adapt, so a refusal that ran late would be visible."""
        result = call(self.module, "canonicalize_event",
                      provider="api-football", consumer_tier="production",
                      requires=list(support.CANARY_REQUIRES),
                      payload=support.observation("api-football"))
        self.assertFalse(result.get("allowed"), result)
        self.assertIsNone(result.get("envelope"))
        self.assertEqual(self.calls, [])

    def test_an_unknown_capability_name_fails_closed(self):
        result = call(self.module, "provider_preflight",
                      provider="api-football", consumer_tier="prototype",
                      requires=["event.identity",
                                "event.definitely_not_a_capability"])
        self.assertFalse(result.get("allowed"), result)
        self.assertEqual(self.calls, [])

    def test_a_provider_outside_the_allowlist_is_refused(self):
        result = call(self.module, "provider_preflight",
                      provider="some-unlicensed-feed",
                      consumer_tier="prototype",
                      requires=list(support.CANARY_REQUIRES))
        self.assertFalse(result.get("allowed"), result)
        self.assertEqual(self.calls, [])

    def test_a_permitted_combination_is_allowed_at_prototype_tier(self):
        """The gate has to say yes to something. A preflight that refused
        everything would pass every refusal case above and be useless."""
        result = call(self.module, "provider_preflight",
                      provider="api-football", consumer_tier="prototype",
                      requires=list(support.CANARY_REQUIRES),
                      optional=list(support.CANARY_OPTIONAL))
        self.assertTrue(result.get("allowed"), result)
        self.assertEqual(result.get("refusals"), [])

    def test_the_declared_capabilities_are_existing_dotted_names(self):
        """§B9: PR 3 consumes the capability contract, it does not extend it. A
        second spelling of a capability name is a second vocabulary."""
        known = set(support.canonical_module("capabilities").ALL_CAPABILITIES)
        declared = connector_declaration().get("connector", {}).get(
            "capabilities", [])
        self.assertTrue(declared, "the connector declares no capabilities")
        self.assertEqual(sorted(set(declared) - known), [])

    def test_post_render_rights_is_recorded_as_drift_and_does_not_authorize(self):
        """§B13's second line. If the post-render check were the gate, a refused
        combination would already have cost a provider call."""
        result = call(self.module, "capability_rights_gate",
                      envelope=support.read_json(
                          support.CORRECTED_ENVELOPES["api-football"]),
                      consumer_tier="production", stage="post-render",
                      requires=list(support.CANARY_REQUIRES))
        self.assertEqual(result.get("role"), "drift-check")
        self.assertFalse(result.get("authorizes"), result)
        self.assertTrue(result.get("rights_findings"), result)

    def test_validate_event_refuses_an_envelope_that_is_not_the_contract(self):
        """The seam validates once, at the seam (§5.2 of the consumer
        inventory), so a consumer never has to and never gets to."""
        good = call(self.module, "validate_event",
                    envelope=support.read_json(
                        support.CORRECTED_ENVELOPES["api-football"]))
        self.assertTrue(good.get("valid"), good)

        bad = call(self.module, "validate_event",
                   envelope={support.ENVELOPE_KEY: {"schema_version": "made-up",
                                                    "profile": "made-up"}})
        self.assertFalse(bad.get("valid"), bad)


#: The Machina URNs a crosswalk maps equivalent provider identifiers onto. These
#: are a consumer-owned URN scheme, deliberately NOT the package's surrogate
#: stem: §B12 says the consumer passes its **own** crosswalk into an injected
#: resolver rather than the canonical layer learning about provider identity. A
#: resolved identity is therefore recognisable on sight as *not* a surrogate.
CROSSWALK_EVENT_URN = "urn:example:canary:event:synthetic-match-01"
CROSSWALK_COMPETITION_URN = "urn:example:canary:competition:synthetic-league"
CROSSWALK_TEAM_URNS = ("urn:example:canary:team:synthetic-home",
                       "urn:example:canary:team:synthetic-away")

#: The three legs with an in-repo adapter and therefore a provider-native
#: identifier space to cross-walk. sports-skills is excluded here on purpose: its
#: canonical mode is upstream, so it has no in-repo adapter to resolve against
#: and PR3-D may not add one.
CROSSWALKED_PROVIDERS = ("api-football", "sportradar-soccer", "stats-perform-opta")


def crosswalk_for(providers) -> list:
    """A consumer-owned crosswalk, built from what the fixtures observe.

    One entry per resource, each carrying the provider identifiers that denote
    it — the same ``{_id, provider_ids}`` shape
    shape a consumer maintains anyway. The
    identifiers are read off the checked-in observations rather than transcribed,
    so a fixture edit cannot leave this mapping pointing at identifiers nothing
    observes any more.
    """
    events, competitions = {}, {}
    teams = [dict(), dict()]
    for provider in providers:
        identifiers = support.provider_ids(provider)
        events[provider] = identifiers["event"]
        competitions[provider] = identifiers["competition"]
        for ordinal, team in enumerate(identifiers["teams"][:2]):
            teams[ordinal][provider] = team
    entries = [
        {"kind": "event", "urn": CROSSWALK_EVENT_URN, "provider_ids": events},
        {"kind": "competition", "urn": CROSSWALK_COMPETITION_URN,
         "provider_ids": competitions},
    ]
    for ordinal, urn in enumerate(CROSSWALK_TEAM_URNS):
        entries.append({"kind": "team", "urn": urn,
                        "provider_ids": teams[ordinal]})
    return entries


class TestTheInjectedCrosswalkResolvesIdentity(unittest.TestCase):
    """§B12 and plan task 11, exercised through the connector's real call site.

    Nothing here is mocked. Each leg is a checked-in
    ``canonical-observation/1`` document, canonicalized by the real
    ``canonicalize_event`` against the real package serializer, with a
    consumer-owned crosswalk injected. What is asserted is the *output identity*,
    because that is the only place the difference between "the crosswalk was
    injected" and "the crosswalk was reimplemented" becomes visible.

    A mock resolver here would assert that the test called the resolver the test
    installed, which is true of any implementation including one that ignores the
    crosswalk entirely.
    """

    def setUp(self):
        self.module = connector_module()
        self.crosswalk = crosswalk_for(CROSSWALKED_PROVIDERS)
        self.views = {}
        for provider in CROSSWALKED_PROVIDERS:
            result = call(self.module, "canonicalize_event", provider=provider,
                          consumer_tier="prototype",
                          requires=list(support.CANARY_REQUIRES),
                          crosswalk=self.crosswalk,
                          payload=support.observation(provider))
            self.assertTrue(result.get("allowed"), result)
            self.views[provider] = (
                result["envelope"][support.ENVELOPE_KEY]["event_view"])

    def surrogate_marker(self):
        return ":{0}".format(support.canonical_module("ids").SURROGATE_MARKER)

    def test_resolver_equivalent_event_ids_resolve_to_one_machina_urn(self):
        resolved = {provider: view.get("event_id")
                    for provider, view in self.views.items()}
        self.assertEqual(set(resolved.values()), {CROSSWALK_EVENT_URN}, resolved)

    def test_resolver_equivalent_competition_ids_resolve_to_one_machina_urn(self):
        resolved = {provider: (view.get("competition") or {}).get("id")
                    for provider, view in self.views.items()}
        self.assertEqual(set(resolved.values()), {CROSSWALK_COMPETITION_URN},
                         resolved)

    def test_resolver_equivalent_team_ids_resolve_to_one_machina_urn(self):
        resolved = {provider: tuple(sorted(
            participant.get("id")
            for participant in view.get("participants", [])))
            for provider, view in self.views.items()}
        self.assertEqual(set(resolved.values()),
                         {tuple(sorted(CROSSWALK_TEAM_URNS))}, resolved)

    def test_resolver_a_crosswalked_identity_is_not_a_surrogate(self):
        """The negative half. Three legs agreeing on one surrogate would mean the
        resolver hashed the same inputs, not that it honoured the crosswalk."""
        marker = self.surrogate_marker()
        for provider, view in self.views.items():
            with self.subTest(provider=provider):
                self.assertNotIn(marker, view.get("event_id", ""))
                self.assertNotIn(
                    marker, (view.get("competition") or {}).get("id", ""))

    def test_resolver_unmapped_structural_resources_are_marked_surrogates(self):
        """§B12: a surrogate must be recognisable as a surrogate on sight.

        Season, phase and site are structural resources the injected crosswalk
        says nothing about. They must fall back to the package's provider-scoped
        surrogate resolver and keep its marker, never borrow the event's resolved
        identity and never be silently omitted.
        """
        marker = self.surrogate_marker()
        seen = 0
        for provider, view in self.views.items():
            for member in ("season", "phase", "site"):
                identifier = (view.get(member) or {}).get("id")
                if identifier is None:
                    continue
                seen += 1
                with self.subTest(provider=provider, resource=member):
                    self.assertIn(marker, identifier)
        self.assertGreater(seen, 0, "no structural resource was resolved at all, "
                                    "so the surrogate path is unexercised")

    def test_resolver_surrogates_stay_provider_scoped(self):
        """Two providers must not accidentally agree on a surrogate. Agreement is
        what the crosswalk is for, and a surrogate is precisely the case where no
        crosswalk entry exists to justify it."""
        sites = [(view.get("site") or {}).get("id")
                 for view in self.views.values()]
        sites = [identifier for identifier in sites if identifier]
        self.assertEqual(len(set(sites)), len(sites), sites)

    def test_resolver_declares_its_strategy_rather_than_the_default_one(self):
        """Provenance reads the strategy off the resolver it was handed. An
        injected crosswalk resolver that reported the bare surrogate strategy
        would make the document claim identities were minted when they were
        looked up."""
        result = call(self.module, "canonicalize_event", provider="api-football",
                      consumer_tier="prototype",
                      requires=list(support.CANARY_REQUIRES),
                      crosswalk=self.crosswalk,
                      payload=support.observation("api-football"))
        provenance = result["envelope"][support.ENVELOPE_KEY]["provenance"]
        rendered = repr(provenance)
        self.assertIn("crosswalk", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
