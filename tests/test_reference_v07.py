import pytest

from eval.reference_v07 import reference_classes


def test_v08_study_rejects_changed_shared_authorization_runtime():
    # That study allowed only ledger/retrieval changes. Run it from its frozen
    # commit; the new full-path study installs complete independent wheels.
    with pytest.raises(ValueError, match="shared reference source changed:.*authorization.py"):
        reference_classes()
