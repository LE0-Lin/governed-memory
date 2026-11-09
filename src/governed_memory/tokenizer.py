import json
from functools import lru_cache
from pathlib import Path

import tiktoken
from tiktoken.load import load_tiktoken_bpe


@lru_cache(maxsize=1)
def encoding():
    directory = Path(__file__).parent / "data"
    config = json.loads((directory / "cl100k_base.json").read_text(encoding="utf-8"))
    return tiktoken.Encoding(
        name=config["name"],
        pat_str=config["pattern"],
        special_tokens=config["special_tokens"],
        mergeable_ranks=load_tiktoken_bpe(
            str(directory / "cl100k_base.tiktoken"), expected_hash=config["sha256"]
        ),
    )
