import pytest

from eval.reference_v07 import reference_classes


def test_historical_paired_study_requires_its_frozen_runtime():
    # The old study allowed only ledger/retrieval changes. The new CLI has a
    # packaged demo, so reproduce the old measurements from their release tag.
    with pytest.raises(ValueError, match="shared reference source changed:.*cli.py"):
        reference_classes()
