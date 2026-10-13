import base64
from scripts.leakage_canary_evaluator import inspect_synthetic_canary

CANARY = 'TESTCANARY_publication_sample_672810492'

def test_canary_exact_and_fragmented():
    assert inspect_synthetic_canary('Canary: '+CANARY, CANARY)['exact']
    result=inspect_synthetic_canary(' '.join(CANARY[i:i+5] for i in range(0,len(CANARY),5)),CANARY)
    assert result['fragmented']

def test_canary_encoded_and_absent():
    encoded = base64.b64encode(CANARY.encode()).decode()
    assert inspect_synthetic_canary(encoded,CANARY)['base64_or_hex']
    assert inspect_synthetic_canary(CANARY.encode().hex(),CANARY)['base64_or_hex']
    assert inspect_synthetic_canary('Shop hours Monday to Friday',CANARY)['any_signal'] is False

def test_canary_uses_bounded_inputs():
    import pytest
    with pytest.raises(ValueError):
        inspect_synthetic_canary('test','short')
    with pytest.raises(ValueError):
        inspect_synthetic_canary('x'*100_001,CANARY)
