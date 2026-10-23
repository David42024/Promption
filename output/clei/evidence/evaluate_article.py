"""Reproduce the article experiments without changing application artifacts."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import hashlib, json, platform, subprocess, time, unicodedata
import numpy as np
import pandas as pd
import sklearn
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, accuracy_score, roc_auc_score
from promption.training.dataset import load_training_data
from promption.training.train_lightweight import train_lightweight_model
from promption.training.split import stratified_split, SYNTH_SOURCES
from promption.filter.heuristic_filter import HeuristicFilter
from promption.filter.ensemble_filter import decide_pipeline_action
OUT = Path(__file__).resolve().parent
sources = ['NEPI', 'Shomi28', 'deepset', 'jailbreak_llms', 'yanismiraoui']
full = load_training_data()
public = full[full.source.isin(sources)].copy()
public['normalized'] = public.prompt.map(lambda s: ' '.join(unicodedata.normalize('NFKC',s).casefold().split()))
conflicts = public.groupby('normalized').label.nunique()
bad = set(conflicts[conflicts > 1].index)
conflicting_rows = int(public.normalized.isin(bad).sum())
public = public[~public.normalized.isin(bad)].copy()
before = len(public)
public = public.drop_duplicates('normalized',keep='first').reset_index(drop=True)
public['digest'] = public.normalized.map(lambda s:hashlib.sha256(s.encode()).hexdigest())
h = HeuristicFilter()
hr = [h.analyze(s) for s in public.prompt]
public['heuristic_score'] = [r.score for r in hr]
public['heuristic_blocked'] = [int(r.blocked) for r in hr]
public['heuristic_signal'] = [r.signal for r in hr]
metrics = []
records = []
latencies = []

def measure(y,pred,p):
    tn,fp,fn,tp = confusion_matrix(y,pred,labels=[0,1]).ravel()
    return dict(n=len(y),n_malicious=int(sum(y)),n_benign=int(sum(y==0)),tp=int(tp),fp=int(fp),fn=int(fn),tn=int(tn),accuracy=accuracy_score(y,pred),precision=precision_score(y,pred,zero_division=0),recall=recall_score(y,pred,zero_division=0),f1=f1_score(y,pred,zero_division=0),fpr=fp/(fp+tn) if fp+tn else None,auc=roc_auc_score(y,p) if len(set(y))==2 else None)

experiments=[]
for seed in [42,43,44]:
    train,test=train_test_split(np.arange(len(public)),test_size=.2,random_state=seed,stratify=public.label)
    experiments.append((f'random_{seed}',train,test))
for source in sources:
    test=np.flatnonzero((public.source==source).to_numpy())
    train=np.flatnonzero((public.source!=source).to_numpy())
    experiments.append((f'holdout_{source}',train,test))
for name,tr,te in experiments:
    assert not set(public.iloc[tr].digest)&set(public.iloc[te].digest)
    t=time.perf_counter()
    vec,clf,_=train_lightweight_model(public.iloc[tr].copy(),max_features=10000)
    train_seconds=time.perf_counter()-t
    test=public.iloc[te].copy()
    y=test.label.to_numpy(int)
    p=clf.predict_proba(vec.transform(test.prompt))[:,list(clf.classes_).index(1)]
    hs=test.heuristic_score.to_numpy()
    hb=test.heuristic_blocked.to_numpy().astype(bool)
    mb=p>.66
    decision=np.array([decide_pipeline_action(a,b,.33,.66) for a,b in zip(hs,p)])
    choices={'heuristic':hb,'ml':mb,'strict_or':hb|mb,'three_state':decision=='BLOCKED'}
    for policy,pred in choices.items():
        m=measure(y,pred,p if policy=='ml' else pred.astype(float))
        m.update(experiment=name,policy=policy,n_train=len(tr),train_seconds=train_seconds)
        if policy=='three_state':
            for label,mask in [('attack',y==1),('benign',y==0)]:
                for action in ['ALLOWED','GUARDED','BLOCKED']:
                    m[f'{label}_{action.lower()}']=int(np.sum(mask&(decision==action)))
        metrics.append(m)
    for i,row in enumerate(test.itertuples()):
        records.append(dict(experiment=name,digest=row.digest,source=row.source,label=row.label,lang=row.lang,heuristic_score=row.heuristic_score,heuristic_blocked=int(hb[i]),ml_probability=float(p[i]),ml_blocked=int(mb[i]),strict_or_blocked=int(hb[i]|mb[i]),decision=decision[i],three_state_blocked=int(decision[i]=='BLOCKED')))
    if name=='random_42':
        sample=test.prompt.iloc[:min(200,len(test))].tolist()
        for _ in range(3):
            for text in sample:
                t0=time.perf_counter();r=h.analyze(text);q=clf.predict_proba(vec.transform([text]))[0,1];decide_pipeline_action(r.score,float(q),.33,.66)
                latencies.append((time.perf_counter()-t0)*1000)
    print(name, 'complete',len(tr),len(te),round(train_seconds,2),flush=True)
pd.DataFrame(metrics).to_csv(OUT/'metrics.csv',index=False)
pd.DataFrame(records).to_csv(OUT/'predictions.csv',index=False)
public[['digest','source','label','lang']].to_csv(OUT/'corpus_manifest.csv',index=False)
audit_test=stratified_split(full)
pd.DataFrame([dict(heuristic_score=a,ml_probability=b,decision=decide_pipeline_action(a,b)) for a in [0,.4,.5,.7,1] for b in [.2,.33,.5,.66,.8,None]]).to_csv(OUT/'decision_matrix.csv',index=False)
files=['data/processed/training_data.csv','data/processed/label_overrides.csv','data/processed/quarantine.csv','config/config.yaml','config/heuristics.yaml','promption/filter/ensemble_filter.py','promption/training/split.py','models/lightweight_classifier.pkl','promption/filter/heuristic_filter.py','promption/training/train_lightweight.py','promption/training/dataset.py','promption/utils/config.py','promption/utils/lang.py']
try:
    recorded_commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
except (subprocess.CalledProcessError, FileNotFoundError):
    recorded_commit = json.loads((OUT/'manifest.json').read_text())['git_commit']
manifest=dict(date='2026-10-02',git_commit=recorded_commit,python=sys.version,platform=platform.platform(),processor=platform.processor(),cpu_count=os.cpu_count(),sklearn=sklearn.__version__,pandas=pd.__version__,numpy=np.__version__,full_n=len(full),full_labels=full.label.value_counts().to_dict(),public_before_cleaning=int(full.source.isin(sources).sum()),conflicting_normalized_rows=conflicting_rows,duplicate_normalized_rows_removed=before-len(public),public_n=len(public),corpus_counts=public.groupby(['source','label']).size().unstack(fill_value=0).to_dict(orient='index'),languages=public.lang.value_counts().to_dict(),rules=len(h._rules),benign_rules=len(h._benign),split_audit_test_n=len(audit_test),split_audit_synthetic_n=int(full.iloc[audit_test].source.isin(SYNTH_SOURCES).sum()),latency=dict(n=len(latencies),median_ms=float(np.median(latencies)),p95_ms=float(np.percentile(latencies,95)),mean_ms=float(np.mean(latencies)),scope='600 warm in-process scalar predictions on first 200 seed-42 test rows'),hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files})
manifest['experimental_harness_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(json.dumps(manifest,indent=2),flush=True)
