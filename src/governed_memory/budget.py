"""Shared evidence serialization and whole-document token budgeting."""

import json
from dataclasses import asdict

from governed_memory.tokenizer import encoding


def serialize(value) -> str:
    return json.dumps(
        value,
        default=lambda obj: obj.isoformat(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class EvidenceBudget:
    def __init__(self):
        self.encoding = encoding()

    def pack(self, ranked, budget: int, k: int) -> tuple[list[dict], int]:
        result = []
        for item in ranked:
            trial = [*result, asdict(item)]
            if len(self.encoding.encode(serialize(trial), disallowed_special=())) <= budget:
                result = trial
            if len(result) >= k:
                break
        return result, len(self.encoding.encode(serialize(result), disallowed_special=()))
