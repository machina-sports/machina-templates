"""Single-story v4 regressions; synthetic source fixtures, no provider calls."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('single_story_fixtures',ROOT/'tests/test_machina_read_multisport.py')
assert spec and spec.loader
f=importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(f.module,'now',lambda:f.NOW)

def previous(sports, approved=True):
    return [{'name':'machina-read-edition','value':{'schemaVersion':4,'generatedAt':f.module.iso(f.NOW),'publicApproved':approved,'sports':[{'id':s} for s in sports]}}]

def pack(history=None, **overrides):
    return f.call('assemble',dict(f.blocks(**overrides),edition_format=4,previous_documents=history or []))

def draft(context):
    sid=context['sources'][0]['id']
    return {'headline':context['sources'][0]['label'][:80], 'body':'The recorded result establishes this contest, not the outcome of the next one.',
            'sourceIds':[sid], 'points':[{'text':'Read this as evidence about the named contest, not a guarantee of another result.','sourceIds':[sid]},
                                       {'text':'The source does not establish tactics or a wider trend.','sourceIds':[sid]}]}

def test_one_story_one_sport_and_no_unrelated_market_glue():
    p=pack()
    assert p['schemaVersion']==4 and len(p['sports'])==1 and len(p['sources'])==1
    assert {s['sport'] for s in p['sources']}=={p['sports'][0]['id']}
    assert p['marketSnapshots']==[]
    assert p['scope']==p['sports'][0]['label']
    assert len(p['coverage'])==9

def test_successive_generations_rotate_eligible_sports():
    seen=[]
    history=[]
    for _ in range(9):
        p=pack(history)
        seen.append(p['sports'][0]['id'])
        history=previous([seen[-1]])
    assert len(set(seen))==9
    assert all(a!=b for a,b in zip(seen,seen[1:]))

def test_private_history_does_not_change_rotation_and_legacy_mashup_is_avoided():
    first=pack()['sports'][0]['id']
    assert pack(previous([first],False))['sports'][0]['id']==first
    assert pack(previous(['tennis','basketball']))['sports'][0]['id'] not in {'tennis','basketball'}

def test_one_complete_source_can_support_a_valid_private_edition():
    p=pack()
    result=f.call('finalize',{'context_pack':p,'model_reply':f.reply(draft(p))})
    assert result['status']=='ready'
    value=result['edition']
    assert value['schemaVersion']==4 and value['publicApproved'] is False
    assert len(value['sports'])==len(value['sources'])==1

def test_model_cannot_cite_an_unselected_story():
    p=pack(); value=draft(p);value['points'][0]['sourceIds']=['market:polymarket:outside-brief']
    assert f.call('finalize',{'context_pack':p,'model_reply':f.reply(value)})['reason']=='unbound_citation'

def test_cache_separates_v4_from_v3_and_preserves_original_clocks():
    p=pack();value=f.call('finalize',{'context_pack':p,'model_reply':f.reply(draft(p)),'publish_public':True})['edition']
    record={'name':'machina-read-edition','value':value}
    hit=f.call('cached',{'documents':[record],'edition_format':4})
    assert hit['hit'] and hit['edition']['generatedAt']==value['generatedAt'] and hit['edition']['expiresAt']==value['expiresAt']
    assert not f.call('cached',{'documents':[record]})['hit']
    value['schemaVersion']=3
    assert not f.call('cached',{'documents':[record],'edition_format':4})['hit']

def test_story_prompt_is_specific_original_and_not_a_forced_roast():
    text=f.module.SINGLE_STORY_DIRECTIVES
    assert 'central athlete or team and what happened' in text
    assert 'who, the competition' in text
    assert 'optional short dry punchline' in text
    assert 'Do not tack on a random analogy or force a joke' in text
    assert 'same named subject' in text
    assert all(word not in text.lower() for word in ['gillis','barstool','espys','soap opera'])
