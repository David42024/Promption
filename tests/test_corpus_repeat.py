"""The repeated study must carry overlapping call IDs and outstanding reservations."""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/research'))
_previous_logging_disable = logging.root.manager.disable
import prepare_corpus_repeat as repeat
logging.disable(_previous_logging_disable)


def test_all_prior_ledgers_count_even_when_call_identifiers_overlap(tmp_path,monkeypatch):
    monkeypatch.setattr(repeat.shared,'ROOT',tmp_path)
    paths=[]
    for i,cost in enumerate([.2,.6]):
        path=tmp_path/f'prior_{i}.jsonl'
        path.write_text(json.dumps({'kind':'reserved','call':1,'reserved_usd':cost+.1})+'\n'+
                        json.dumps({'kind':'settled','call':1,'charged_upper_usd':cost})+'\n')
        paths.append(path)
    destination=tmp_path/'combined.jsonl'
    total,sources=repeat.combine_ledgers(paths,destination)
    assert abs(total-.8)<1e-9 and len(sources)==2
    rows=[json.loads(line) for line in destination.read_text().splitlines()]
    assert len({r['call'] for r in rows})==2
    assert {r['source_call'] for r in rows}=={1}


def test_unsettled_prior_calls_keep_their_full_reservation(tmp_path,monkeypatch):
    monkeypatch.setattr(repeat.shared,'ROOT',tmp_path)
    path=tmp_path/'pending.jsonl';path.write_text(json.dumps({'kind':'reserved','call':1,'reserved_usd':.8})+'\n')
    total,_=repeat.combine_ledgers([path],tmp_path/'combined.jsonl')
    assert total==.8
