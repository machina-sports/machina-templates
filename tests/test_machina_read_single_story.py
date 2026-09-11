"""Best-story v4 regressions; synthetic observed-shape fixtures, no provider calls."""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('single_story_fixtures', ROOT / 'tests/test_machina_read_multisport.py')
assert spec and spec.loader
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(f.module, 'now', lambda: f.NOW)


def source(ident, sport, kind, label, text, hours=-1, rank=None):
    if rank is None:
        rank = f.module.RANK_NEWS if kind == 'news headline' else f.module.RANK_RESULT
    url = ('https://news.google.com/rss/articles/' + ident.replace(':', '-') if kind == 'news headline'
           else 'https://www.espn.com/soccer/match/_/gameId/' + hashlib.sha256(ident.encode()).hexdigest()[:9])
    entry = {'id': ident, 'sport': sport, 'kind': kind, 'label': label, 'text': text, 'url': url,
             'observedAt': f.module.iso(f.NOW)}
    if kind == 'news headline':
        entry['publishedAt'] = f.module.iso(f.NOW + f.timedelta(hours=hours))
    return {'source': entry, 'rank': rank, 'sortAt': f.module.iso(f.NOW + f.timedelta(hours=hours))}


def block(*items, snapshots=None):
    return {'status': 'ready', 'items': list(items), 'snapshots': snapshots or []}


def previous(*sources, approved=True):
    return [{'name': 'machina-read-edition', 'value': {
        'schemaVersion': 4, 'generatedAt': f.module.iso(f.NOW), 'publicApproved': approved,
        'sports': [{'id': entry['sport']} for entry in sources], 'sources': list(sources)}}]


def pack(history=None, **overrides):
    params = dict(f.blocks(**overrides), edition_format=4, previous_documents=history or [])
    return f.call('assemble', params)


def candidate(context, anchor_id=None):
    packets = context['candidates']
    return next(packet for packet in packets if anchor_id is None or packet['anchorSourceId'] == anchor_id)


def draft(context, anchor_id=None, extra_refs=None):
    packet = candidate(context, anchor_id)
    anchor_id = packet['anchorSourceId']
    refs = [anchor_id, *(extra_refs or [])]
    return {'selectedAnchorSourceId': anchor_id, 'headline': packet['sources'][0]['label'][:80],
            'body': 'The reported development establishes what happened and why this specific contest matters now.',
            'sourceIds': refs,
            'points': [
                {'text': 'The anchor supports this development without claiming an unsupported wider trend.',
                 'sourceIds': [anchor_id]},
                {'text': 'The available evidence is specific to this subject and this competition.',
                 'sourceIds': [anchor_id]},
            ]}


def finalize(context, story=None, **reply_overrides):
    return f.call('finalize', {'context_pack': context,
                               'model_reply': f.reply(story or draft(context), **reply_overrides)})


def test_default_v4_shortlist_is_broad_bounded_and_contains_coherent_packets():
    context = f.call('assemble', f.blocks())
    assert context['schemaVersion'] == 4
    assert 4 <= len(context['sports']) <= 9
    assert 1 < len(context['candidates']) <= f.module.MAX_STORY_CANDIDATES
    assert sum(len(entry['text']) for packet in context['candidates'] for entry in packet['sources']) <= f.module.TEXT_BUDGET
    assert len(context['prompt'].encode()) <= f.module.PROMPT_BUDGET
    counts = {}
    for packet in context['candidates']:
        sport = packet['sport']['id']
        counts[sport] = counts.get(sport, 0) + 1
        assert packet['sources'][0]['id'] == packet['anchorSourceId']
        assert packet['sources'][0]['kind'] != 'market'
        assert len(packet['sources']) <= 2
        assert {entry['sport'] for entry in packet['sources']} == {sport}
    assert max(counts.values()) <= f.module.MAX_STORY_CANDIDATES_PER_SPORT
    assert len({entry['id'] for entry in context['sources']}) == len(context['sources'])


def test_high_volume_in_one_sport_does_not_erase_shortlist_breadth():
    items = [source(f'news:football:{index}', 'football', 'news headline', f'Football development {index}',
                    f'Reported headline only for Football; football development {index} was reported.', hours=-index)
             for index in range(1, 9)]
    for sport in ('baseball', 'basketball', 'hockey', 'tennis'):
        items.append(source(f'news:{sport}:one', sport, 'news headline', f'{sport} development',
                            f'Reported headline only for {sport}; one current {sport} development was reported.'))
    context = f.call('assemble', {'schedule': block(*items), 'edition_format': 4})
    represented = {packet['sport']['id'] for packet in context['candidates']}
    assert represented == {'football', 'baseball', 'basketball', 'hockey', 'tennis'}
    assert sum(packet['sport']['id'] == 'football' for packet in context['candidates']) == 2


def test_overflow_candidate_slots_do_not_follow_fixed_sport_order():
    items = []
    for index, sport in enumerate(f.SPORT_IDS):
        base = -20 + index
        items.extend([
            source(f'news:{sport}:newer', sport, 'news headline', f'{sport} newer development',
                   f'Reported headline only for {sport}; its newer development was reported.', hours=base + 1),
            source(f'news:{sport}:older', sport, 'news headline', f'{sport} older development',
                   f'Reported headline only for {sport}; its older development was reported.', hours=base),
        ])
    context = f.call('assemble', {'schedule': block(*items), 'edition_format': 4})
    counts = {sport: sum(packet['sport']['id'] == sport for packet in context['candidates']) for sport in f.SPORT_IDS}
    assert all(count >= 1 for count in counts.values())
    assert {sport for sport, count in counts.items() if count == 2} == {'motorsport', 'golf', 'cricket'}


def test_mocked_model_selection_protocol_can_choose_high_stakes_news_over_mundane_other_sport_result():
    mundane = source('event:tennis:mundane', 'tennis', 'event', 'Capital Open: routine first round',
                     'A routine Capital Open first-round match finished with the recorded result.', hours=-1)
    high = source('news:basketball:final', 'basketball', 'news headline',
                  'Summit Bears clinch first national title',
                  'Reported headline only for Basketball; Summit Bears clinch their first national title in the National Final.',
                  hours=-5)
    context = f.call('assemble', {'schedule': block(mundane, high), 'edition_format': 4})
    assert {packet['anchorSourceId'] for packet in context['candidates']} == {
        'event:tennis:mundane', 'news:basketball:final'}
    result = finalize(context, draft(context, 'news:basketball:final'))
    assert result['status'] == 'ready'
    assert result['edition']['sources'][0]['id'] == 'news:basketball:final'
    # The fixture proves selection plumbing and validation, not real model editorial quality.


def test_same_sport_can_win_successive_days_but_exact_source_repeat_is_excluded():
    old = source('news:tennis:old', 'tennis', 'news headline', 'Old tennis development',
                 'Reported headline only for Tennis; Callum Wren reached the Capital Open final.', hours=-6)['source']
    new = source('news:tennis:new', 'tennis', 'news headline', 'New tennis development',
                 'Reported headline only for Tennis; Mateo Salas won the Capital Open title.', hours=-1)
    context = f.call('assemble', {'news_tennis': block(source('news:tennis:old', 'tennis', 'news headline',
                 'Old tennis development', old['text'], hours=-6), new), 'edition_format': 4,
                 'previous_documents': previous(old)})
    assert [packet['anchorSourceId'] for packet in context['candidates']] == ['news:tennis:new']
    assert context['sports'] == [{'id': 'tennis', 'label': 'Tennis'}]


def test_only_repeat_evidence_fails_instead_of_redating_it():
    repeated = source('news:hockey:repeat', 'hockey', 'news headline', 'Repeated final',
                      'Reported headline only for Ice hockey; Glacier Kings won the League Final.', hours=-2)
    result = f.call('assemble', {'news_hockey': block(repeated), 'edition_format': 4,
                                 'previous_documents': previous(repeated['source'])})
    assert result == {'status': 'unavailable', 'reason': 'no_new_story'}


def test_updated_development_with_same_source_id_and_url_is_not_an_exact_repeat():
    old = source('event:football:401', 'football', 'event', 'Championship: Ewood v Steelworks',
                 'Ewood Rovers versus Steelworks United is scheduled and not final.', hours=-5)['source']
    updated = source('event:football:401', 'football', 'event', 'Championship: Ewood v Steelworks',
                     'Ewood Rovers 1-2 Steelworks United is the reported Championship final.', hours=-1)
    context = f.call('assemble', {'football': block(updated), 'edition_format': 4,
                                  'previous_documents': previous(old)})
    assert context['status'] == 'ready'
    assert context['candidates'][0]['anchorSourceId'] == 'event:football:401'


def test_private_or_other_sport_history_does_not_force_rotation():
    tennis = source('news:tennis:current', 'tennis', 'news headline', 'Current tennis final',
                    'Reported headline only for Tennis; Callum Wren won the Capital Open final.', hours=-1)
    private = previous(tennis['source'], approved=False)
    context = f.call('assemble', {'news_tennis': block(tennis), 'edition_format': 4,
                                  'previous_documents': private})
    assert context['candidates'][0]['anchorSourceId'] == 'news:tennis:current'


def test_market_is_attached_only_to_the_same_named_subject_and_remains_optional_to_cite():
    anchor = source('event:baseball:final', 'baseball', 'event', 'Championship: Metro Drakes win',
                    'Metro Drakes won the Pro Baseball Championship final, a completed reported result.', hours=-2)
    kalshi = f.call('compact', {'kind': 'kalshi', 'raw': f.kalshi_response(), 'identities': f.team_catalog()})
    context = f.call('assemble', {'schedule': block(anchor), 'kalshi': kalshi, 'edition_format': 4})
    packet = candidate(context)
    assert [entry['kind'] for entry in packet['sources']] == ['event', 'market']
    assert 'Metro Drakes' in packet['sources'][1]['text']
    assert finalize(context)['status'] == 'ready'  # supplied market is not mandatory
    market_id = packet['sources'][1]['id']
    story = draft(context)
    story['points'][1] = {'text': 'Kalshi quotes the title contract at 0.60, a snapshot rather than a forecast.',
                          'sourceIds': [market_id]}
    assert finalize(context, story)['status'] == 'ready'


def test_unrelated_same_sport_market_is_not_glued_to_an_anchor():
    anchor = source('event:baseball:other', 'baseball', 'event', 'Coast Gulls win',
                    'Coast Gulls won a completed Pro Baseball Championship game.', hours=-1)
    kalshi = f.call('compact', {'kind': 'kalshi', 'raw': f.kalshi_response(), 'identities': f.team_catalog()})
    context = f.call('assemble', {'schedule': block(anchor), 'kalshi': kalshi, 'edition_format': 4})
    assert candidate(context)['sources'] == [anchor['source']]
    assert context['marketSnapshots'] == []


def test_static_market_only_pool_has_no_publishable_candidate():
    kalshi = f.call('compact', {'kind': 'kalshi', 'raw': f.kalshi_response(), 'identities': f.team_catalog()})
    result = f.call('assemble', {'kalshi': kalshi, 'edition_format': 4})
    assert result == {'status': 'unavailable', 'reason': 'insufficient_concrete_development'}


def test_finalizer_strips_selection_metadata_and_keeps_the_existing_public_story_schema():
    context = pack()
    result = finalize(context)
    assert result['status'] == 'ready'
    assert set(result['edition']['story']) == {'headline', 'body', 'sourceIds', 'points'}
    assert 'selectedAnchorSourceId' not in json.dumps(result['edition'])
    assert len(result['edition']['sports']) == 1


def test_finalizer_rejects_source_mixing_between_same_sport_candidates():
    first = source('news:basketball:first', 'basketball', 'news headline', 'First basketball story',
                   'Reported headline only for Basketball; Summit Bears reached the National Final.', hours=-1)
    second = source('news:basketball:second', 'basketball', 'news headline', 'Second basketball story',
                    'Reported headline only for Basketball; Delta Foxes appointed a new head coach.', hours=-2)
    context = f.call('assemble', {'news_basketball': block(first, second), 'edition_format': 4})
    story = draft(context, first['source']['id'], [second['source']['id']])
    assert finalize(context, story)['reason'] == 'unbound_citation'


@pytest.mark.parametrize(('mutation', 'reason'), [
    ('missing_anchor', 'invalid_story_fields'),
    ('unknown_anchor', 'unknown_anchor'),
    ('numeric_citation', 'unbound_citation'),
    ('unknown_citation', 'unbound_citation'),
    ('unsupported_number', 'unsupported_numeric_claim'),
    ('wrong_sport', 'unbound_sport_reference'),
    ('incomplete', 'incomplete_model_reply'),
])
def test_finalizer_rejects_invalid_selection_and_claims(mutation, reason):
    context = pack()
    story = draft(context)
    reply_overrides = {}
    if mutation == 'missing_anchor':
        story.pop('selectedAnchorSourceId')
    elif mutation == 'unknown_anchor':
        story['selectedAnchorSourceId'] = 'event:football:unknown'
    elif mutation == 'numeric_citation':
        story['points'][0]['sourceIds'] = [123]
    elif mutation == 'unknown_citation':
        story['points'][0]['sourceIds'] = ['news:tennis:unknown']
    elif mutation == 'unsupported_number':
        story['points'][0]['text'] = 'This source proves 999 championships.'
    elif mutation == 'wrong_sport':
        selected_sport = candidate(context)['sport']['id']
        wrong = 'NHL' if selected_sport != 'hockey' else 'NBA'
        story['points'][0]['text'] = wrong + ' supplied the decisive context.'
    elif mutation == 'incomplete':
        reply_overrides['finish_reason'] = 'length'
    assert finalize(context, story, **reply_overrides)['reason'] == reason


def test_selected_anchor_must_cite_the_visible_headline_and_body():
    anchor = source('event:baseball:anchor', 'baseball', 'event', 'Metro Drakes win title',
                    'Metro Drakes won the Pro Baseball Championship final.', hours=-2)
    kalshi = f.call('compact', {'kind': 'kalshi', 'raw': f.kalshi_response(), 'identities': f.team_catalog()})
    context = f.call('assemble', {'schedule': block(anchor), 'kalshi': kalshi, 'edition_format': 4})
    story = draft(context)
    story['sourceIds'] = [candidate(context)['sources'][1]['id']]
    assert finalize(context, story)['reason'] == 'missing_anchor_citation'


def test_cache_defaults_to_v4_and_explicit_v3_read_compatibility_remains():
    context = pack()
    value = f.call('finalize', {'context_pack': context, 'model_reply': f.reply(draft(context)),
                                'publish_public': True})['edition']
    record = {'name': 'machina-read-edition', 'value': value}
    hit = f.call('cached', {'documents': [record]})
    assert hit['hit'] and hit['edition']['generatedAt'] == value['generatedAt']
    assert not f.call('cached', {'documents': [record], 'edition_format': 3})['hit']
    legacy = f.pack()
    assert legacy['schemaVersion'] == 3


def test_prompt_requires_model_selection_without_rotation_or_forced_humor():
    text = f.module.SINGLE_STORY_DIRECTIVES
    for phrase in ['Choose the strongest supported current development', 'newsworthiness', 'evidence strength',
                   'supported stakes', 'genuine novelty', 'do not rotate sports', 'selectedAnchorSourceId',
                   'optional short dry punchline', 'Do not tack on a random analogy or force a joke',
                   'related market source is optional context', 'Never impersonate']:
        assert phrase in text
    assert all(word not in text.lower() for word in ['gillis', 'barstool', 'espys', 'soap opera'])
