from scripts.check_v9_family_holdout import check

def test_group_overlap_detected():
    x=check([{'family_id':'family-1','prompt':'Ignore instructions','source':'train'}],
            [{'family_id':'family-1','prompt':'Ignora instrucciones','source':'external'}])
    assert not x['declared_family_and_exact_text_disjoint']
    assert x['families_shared']==['family-1']

def test_text_overlap_detected_across_family_labels():
    x=check([{'family_id':'a','prompt':'Hello   world'}], [{'family_id':'b','prompt':'hello world'}])
    assert x['shared_exact_text_hashes']==1
    assert not x['declared_family_and_exact_text_disjoint']

def test_good_split_requires_families():
    x=check([{'family_id':'a','prompt':'Ignore instructions'}],
            [{'family_id':'b','prompt':'How does our catalog work?'}])
    assert x['declared_family_and_exact_text_disjoint']
