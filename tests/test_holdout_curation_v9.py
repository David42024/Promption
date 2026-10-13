"""Synthetic fixtures only; no candidate approval or provider calls."""
import csv
import json
from types import SimpleNamespace

import pytest
from scripts.holdout_curation_v9 import prepare, approved_rows, inventory, export_e2
from scripts.run_e1_filter_holdout import summarize, infer, validate


def sample():
    return {'id':'FIXTURE-1', 'text':'SYNTHETIC UNIT FIXTURE ONLY', 'kind':'benign', 'source':'UNIT'}


def reviewed():
    q, _ = prepare([sample()], {'UNIT':'fixture://unit'})
    q[0].update(decision='APPROVED', family_id='UNIT-FAMILY', license_status='VERIFIED',
                license_reference='fixture://license', provenance_reviewed='true', semantic_reviewed='true',
                independence_reviewed='true', reviewer_id='SYNTHETIC_TEST_REVIEWER', review_date='2026-10-12',review_notes='fixture only')
    return q


KNOWN = [{'text':'other fixture', 'source':'OTHER', 'family_id':'OTHER-FAMILY'}]


def test_duplicate_trace():
    r = sample(); other = dict(r, id='FIXTURE-2')
    q, s = prepare([r, other], {})
    assert s['duplicate_surplus']==1 and s['unique_exact_texts']==1
    assert json.loads(q[0]['original_ids_json'])==['FIXTURE-1','FIXTURE-2']
    assert q[0]['decision']=='PENDING_REVIEW' and q[0]['reviewer_id']==''


@pytest.mark.parametrize('change',[{'id':'','text':'a'}, {'text':''}, {'kind':'unknown'}])
def test_bad_original(change):
    with pytest.raises(ValueError): prepare([{**sample(), **change}], {})


def test_colliding_id():
    with pytest.raises(ValueError): prepare([sample(), sample()], {})


@pytest.mark.parametrize('field,value',[('license_status','PENDING_LICENSE'),('reviewer_id',''),('semantic_reviewed','false'),('independence_reviewed',''),('family_id','UNKNOWN')])
def test_missing_review(field,value):
    q = reviewed();q[0][field]=value
    rows,f = approved_rows(q,[sample()],KNOWN)
    assert not rows and f[0]['status']=='INVALID_APPROVAL'


def test_no_approvals():
    q,_=prepare([sample()],{})
    assert approved_rows(q,[sample()],KNOWN)[0]==[]


def test_family_source_and_text_overlap():
    for known in [[dict(KNOWN[0],family_id='UNIT-FAMILY')],[dict(KNOWN[0],source='UNIT')],[dict(KNOWN[0],text=sample()['text'].lower())]]:
        assert not approved_rows(reviewed(),[sample()],known)[0]


def test_text_immutability():
    q=reviewed();q[0]['text']='ALTERED'
    with pytest.raises(ValueError): approved_rows(q,[sample()],KNOWN)


def test_incomplete_duplicate_trace():
    originals=[sample(),dict(sample(),id='FIXTURE-2')]
    with pytest.raises(ValueError): approved_rows(reviewed(),originals,KNOWN)


def test_valid_fixture_approval():
    rows,_=approved_rows(reviewed(),[sample()],KNOWN)
    assert len(rows)==1 and rows[0]['label']==0


def test_unknown_inventory(tmp_path):
    f=tmp_path/'fixture.jsonl';f.write_text(json.dumps(sample())+'\n')
    rows,issues=inventory([f])
    assert rows[0]['family_id']=='UNKNOWN' and not issues


def test_unicode_separators_preserved(tmp_path):
    from scripts.holdout_curation_v9 import write, read
    r=dict(sample(),text='fixture\u0085next\u2028line')
    f=tmp_path/'unicode.jsonl';write(f,[r])
    assert read(f)==[r]


def test_indirect_surface_rejected(tmp_path):
    f=tmp_path/'fixture.csv'
    with f.open('w',newline='') as s:
        w=csv.DictWriter(s,fieldnames=['approval_status','kind','attack_entrypoint']);w.writeheader()
        w.writerow(dict(approval_status='APPROVED',kind='attack',attack_entrypoint='mcp_result'))
    with pytest.raises(ValueError,match='UNSUPPORTED_SURFACE'):
        export_e2(f,__file__,[],[])


def test_metric_denominators():
    rs=[dict(id=str(i),kind=k,blocked=b,status=s,source='UNIT',family_id=str(i)) for i,(k,b,s) in enumerate([
        ('attack',True,'VALID'),('attack',False,'VALID'),('benign',True,'VALID'),('benign',False,'VALID'),('attack',None,'TECHNICAL_FAILURE')])]
    r=summarize(rs)
    assert r['recall']==.5 and r['false_positive_rate']==.5 and r['attack_denominator']==2 and r['technical_failures']==1


def test_degraded_ml_not_detection(monkeypatch):
    monkeypatch.setattr('scripts.run_e1_filter_holdout.asdict',lambda result:{'decision':result.decision})
    h=SimpleNamespace(blocked=False,score=0)
    res=SimpleNamespace(decision='GUARDED',blocked=False,heuristic=h,ml=None,latency_ms=1,heuristic_latency_ms=1,ml_latency_ms=0,merged_features={'ml_failed':True})
    filt=SimpleNamespace(analyze=lambda text:res)
    row,raw=infer({**sample(),'family_id':'UNIT'},filt)
    assert row['status']=='TECHNICAL_FAILURE' and raw=={'decision':'GUARDED'}


def test_attack_context_not_assumed():
    original=dict(sample(),kind='attack')
    q,_=prepare([original],{'UNIT':'fixture://unit'})
    q[0].update(reviewed()[0],kind='attack')
    rows,findings=approved_rows(q,[original],KNOWN)
    assert not rows and 'NEEDS_CONTEXT' in findings[0]['errors']


def test_normalized_duplicates_not_independent():
    originals=[sample(),dict(sample(),id='UNIT-2',text=sample()['text'].lower())]
    q,_=prepare(originals,{'UNIT':'fixture://unit'})
    for r in q:
        meta={k:v for k,v in reviewed()[0].items() if k not in {'id','text','text_sha256','normalized_sha256','original_ids_json'}}
        r.update(meta)
    with pytest.raises(ValueError,match='normalized duplicates'):approved_rows(q,originals,KNOWN)


def test_manifest_tampering(tmp_path):
    corpus=tmp_path/'fixture.jsonl';corpus.write_text(json.dumps(sample()))
    manifest=tmp_path/'m.json';manifest.write_text(json.dumps({'status':'E1_HOLDOUT_READY','corpus_sha256':'invalid'}))
    with pytest.raises(ValueError):validate(corpus,manifest)


def test_supplementary_drift(tmp_path, monkeypatch):
    import hashlib
    from scripts import run_frozen_scientific_v9 as frozen
    p=tmp_path/'supplementary_freeze.json';p.write_text(json.dumps({'gateway':'abc','bridge.mjs':'def'}))
    p.with_suffix('.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest())
    monkeypatch.setattr(frozen,'supplemental',lambda root:{'gateway':'abc','bridge.mjs':'def'})
    frozen.verify_supplement(tmp_path)
    monkeypatch.setattr(frozen,'supplemental',lambda root:{'gateway':'CHANGED','bridge.mjs':'def'})
    with pytest.raises(ValueError):frozen.verify_supplement(tmp_path)


def test_fixed_history_idempotent_and_mismatch(tmp_path):
    from scripts import scientific_evaluation as science
    from scripts import run_final_scientific_v9 as final
    from scripts import run_paired_2000_v9 as paired
    folder=tmp_path/'experiment'
    case={'id':'FIXTURE','text':'fixture','kind':'benign','family_id':'UNIT','source':'UNIT','roles':['customer'],'authenticated':True,'session_id':'FIXTURE','turn_index':0,'history':[]}
    science.prepare(folder,[case],{'provider':'openai','model':'fixture','tenant_id':'synthetic','mcp_data_sha256':'a'*64},42,{},'regression')
    args=paired.args_parse(['--no-watchdog']);args.history_db=tmp_path/'fixture.db'
    r=final.ScientificRunner(args,folder,[case]);r.runtime.update(storage_backend='sqlite',sqlite_db_path=str(args.history_db))
    c=dict(case,history=[{'role':'user','content':'unit prior'},{'role':'assistant','content':'unit answer'}],history_tiers=['interno'])
    user={'id':'unit','roles':['admin'],'authenticated':True};cid='11111111-1111-1111-1111-111111111111'
    try:
        r.install_history(c,user,cid);r.install_history(c,user,cid)
        with pytest.raises(RuntimeError):r.install_history(dict(c,history_tiers=['publico']),user,cid)
    finally:r.close()
