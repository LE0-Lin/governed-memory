import pytest

from eval.reference_v07 import reference_classes


def test_historical_paired_study_requires_its_frozen_runtime():
    # The old study allowed only ledger/retrieval changes. Later releases changed
    # other runtime files, so reproduce the old measurements from their release tag.
    with pytest.raises(ValueError, match="shared reference source changed: src/"):
        reference_classes()
