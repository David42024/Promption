"""Disclosure regression vectors use a public synthetic value, never application secrets."""
import json
from pathlib import Path

import pytest

from promption.output_guard import guard_response

VECTORS=json.loads((Path(__file__).resolve().parents[1]/'data/calibration/protected_value_vectors.json').read_text())


@pytest.mark.parametrize('row',VECTORS['rows'],ids=lambda row:row['id'])
def test_known_values_and_controls(row):
    result=guard_response(row['text'],protected_values=[VECTORS['secret']])
    assert (result.action=='BLOCK')==bool(row['label'])


def test_natural_language_protected_values_do_not_block_common_fragments():
    assert guard_response('Explain security policies',protected_values=['The security policies are confidential']).action=='PASS'
