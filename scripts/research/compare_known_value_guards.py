"""Compare frozen and current output guards on public synthetic regression vectors."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
CHILD='''import json,sys,logging
logging.disable(logging.CRITICAL)
sys.path.insert(0,sys.argv[1])
from promption.output_guard import guard_response
fixture=json.load(sys.stdin)
rows=[dict(id=row["id"],label=row["label"],blocked=guard_response(row["text"],protected_values=[fixture["secret"]]).action=="BLOCK") for row in fixture["rows"]]
print(json.dumps(rows))
'''


def run(baseline,output):
    fixture=(ROOT/'data/calibration/protected_value_vectors.json').read_text()
    results={}
    for name,library in [('baseline_160',baseline),('current_170',ROOT)]:
        child=subprocess.run([sys.executable,'-c',CHILD,str(library.resolve())],input=fixture,
                             text=True,capture_output=True,cwd='/tmp',check=True)
        rows=json.loads(child.stdout)
        counts=Counter(('TP' if row['blocked'] else 'FN') if row['label'] else
                       ('FP' if row['blocked'] else 'TN') for row in rows)
        results[name]={'counts':{key:counts[key] for key in ['TP','FP','FN','TN']},'rows':rows}
    summary={'kind':'conditional_synthetic_output_guard_regression','external_api_calls':0,
             'limitation':'Known synthetic outputs are injected directly into the output guard, without sampling a language model. No natural attack-success estimate.',
             'results':results}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,indent=2))
    print(json.dumps({key:value['counts'] for key,value in results.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.baseline,args.output)
