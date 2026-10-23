"""Build deduplicated silver candidates and purged participant holdouts, never train."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from analyze_export import csv_write


def words(value):
    text=''.join(c for c in unicodedata.normalize('NFKD',value).lower() if not unicodedata.combining(c))
    return re.findall(r'\w+',text)


def prepare(folder):
    rows=[json.loads(line) for line in (folder/'etiquetas_provisionales.jsonl').read_text().splitlines()]
    parent=list(range(len(rows)));features=[];buckets=collections.defaultdict(list);exact={}
    def root(i):
        while i!=parent[i]:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    for i,row in enumerate(rows):
        tokens=words(row['prompt']);key=' '.join(tokens)
        if key in exact:union(i,exact[key])
        else:exact[key]=i
        grams={tuple(tokens[j:j+3]) for j in range(len(tokens)-2)} if len(tokens)>=8 else set()
        features.append(grams)
        if not grams:continue
        candidates=collections.Counter(j for gram in grams for j in buckets[gram] if len(buckets[gram])<=250)
        for j,shared in candidates.items():
            other=features[j]
            if shared/max(1,len(grams|other))>=0.8:union(i,j)
        for gram in grams:buckets[gram].append(i)
    family_ids={};families=collections.defaultdict(list)
    for i,row in enumerate(rows):
        rep=root(i);family_ids.setdefault(rep,'F'+hashlib.sha256(rows[rep]['prompt'].encode()).hexdigest()[:12]);row['family_id']=family_ids[rep];families[row['family_id']].append(row)
    ranks={'train':0,'validation':1,'test':2};purged=0;duplicates=0;selected=[];seen={}
    conflicts={family for family,group in families.items() if len({r['injection_label_proposed'] for r in group if r['injection_label_proposed'] in (0,1) and not r['context_required']})>1}
    for row in rows:
        group=families[row['family_id']];earliest=min(ranks[r['participant_split_proposed']] for r in group)
        split=row['participant_split_proposed'];row['split_proposed']=split
        if ranks[split]>earliest:
            row['split_proposed']='purged_family_overlap';purged+=1
        label=row['injection_label_proposed']
        reason=''
        if label not in (0,1):reason='unresolved_label'
        elif row['annotation_confidence']!='high':reason='needs_confidence_review'
        elif row['context_required']:reason='requires_conversation_context'
        elif row['cohort']!='post_reset':reason='pilot_before_reset'
        elif row['family_id'] in conflicts:reason='conflicting_family_labels'
        elif row['split_proposed']=='purged_family_overlap':reason='family_overlap_across_participants'
        elif row['intent_category'] in ['unintelligible','technical_fixture','spam_or_flood']:reason='excluded_intent'
        key=' '.join(words(row['prompt']))
        if not reason and key in seen:reason='duplicate';duplicates+=1
        row['training_candidate_exclusion']=reason
        if not reason:
            seen[key]=row['id']
            selected.append({'id':row['id'],'prompt':row['prompt'],'label':label,'dataset':'Custom' if label else 'Benigno',
              'attack_type':row['intent_category'] if label else 'benign','category':row['intent_category'],
              'source':'human_competition_20261022_silver_pending_review','group_id':row['family_id'],'family_id':row['family_id'],
              'participant_id':row['participant_id'],'split':row['split_proposed'],'annotation_status':'PROVISIONAL_REQUIRES_HUMAN_REVIEW'})
    (folder/'etiquetas_provisionales.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    csv_write(folder/'etiquetas_provisionales.csv',rows)
    csv_write(folder/'candidatos_entrenamiento_NO_GOLD.csv',selected,['id','prompt','label','dataset','attack_type','category','source','group_id','family_id','participant_id','split','annotation_status'])
    csv_write(folder/'revision_prioritaria.csv',sorted(rows,key=lambda r:(r['review_priority'],r['id'])))
    summary={'families':len(families),'conflicting_families':len(conflicts),'family_threshold':'word_trigram_Jaccard>=0.8_or_normalized_exact','split_method':'participant_hash_seed42_70_15_15_then_purge_family_overlap','purged_rows':purged,'duplicate_candidates_removed':duplicates,'single_message_silver_candidates':len(selected),'candidate_splits':dict(collections.Counter(r['split'] for r in selected)),'candidate_labels':dict(collections.Counter(str(r['label']) for r in selected)),'exclusion_reasons':dict(collections.Counter(r['training_candidate_exclusion'] or 'candidate' for r in rows))}
    for split in ['train','validation','test']:
        subset=[r for r in selected if r['split']==split]
        for other in ['train','validation','test']:
            if split==other:continue
            outside=[r for r in selected if r['split']==other]
            assert not {r['participant_id'] for r in subset}&{r['participant_id'] for r in outside}
            assert not {r['family_id'] for r in subset}&{r['family_id'] for r in outside}
    (folder/'preparacion_entrenamiento.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    for path in folder.iterdir():
        if path.is_file():path.chmod(0o600)
    print(json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);prepare(p.parse_args().folder)
