"""Historical decision replay; *never* describe this as an independent evaluation.

Usage: PYTHONPATH=. python scripts/replay_known_benchmark.py PATH_TO_BENCHMARK.csv
The historical ML probabilities are retained; ML is not invoked. A new heuristic
veto can skip ML, but no new probability is inferred for skipped cases.
"""
import sys
import json
import pandas as pd
from promption.filter.heuristic_filter import HeuristicFilter
from promption.utils.config import load_config


def replay(csv_path):
    df=pd.read_csv(csv_path)
    filter_=HeuristicFilter()
    threshold=load_config()['ensemble']['decision_high_threshold']
    decisions=[]
    for row in df.itertuples(index=False):
        h=filter_.analyze(str(row.prompt))
        p=getattr(row, 'ml_probability', None)
        old_ml_done=bool(getattr(row,'ml_executed',False))
        is_high=old_ml_done and pd.notna(p) and float(p)>=threshold
        if h.blocked:
            decision='BLOCKED'
        elif h.signal=='benign' and not h.blocked:
            decision='ALLOWED'
        elif is_high:
            decision='GUARDED' if h.quoted_educational_context else 'BLOCKED'
        else:
            decision='GUARDED'
        decisions.append(decision)
    truth=df.label.astype(int)
    blocks=pd.Series(decisions,index=df.index).eq('BLOCKED')
    result={"notice":"Known-test replay only, using historical ML scores (not independent validation)",
        "cases":len(df),"threshold":threshold,
        "tp":int((blocks&(truth==1)).sum()),"fp":int((blocks&(truth==0)).sum()),
        "fn_of_early_block":int((~blocks&(truth==1)).sum()),
        "tn_of_early_block":int((~blocks&(truth==0)).sum()),
        "blocked_ids":[int(v) for v in df.loc[blocks,'id']]}
    return result

if __name__=='__main__':
    print(json.dumps({k:v for k,v in replay(sys.argv[1]).items() if k!='blocked_ids'},indent=2))
