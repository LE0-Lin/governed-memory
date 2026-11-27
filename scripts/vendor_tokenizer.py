"""Refresh the pinned, MIT-licensed tokenizer asset for network-free example runs."""

import hashlib
import json
import urllib.request
from pathlib import Path

import tiktoken

DESTINATION = Path(__file__).resolve().parents[1] / "src/governed_memory/data"
EXPECTED_HASH = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"


def main():
    blob = urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(blob).hexdigest() != EXPECTED_HASH:
        raise ValueError("tokenizer checksum mismatch")
    encoding = tiktoken.get_encoding("cl100k_base")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / "cl100k_base.tiktoken").write_bytes(blob)
    (DESTINATION / "cl100k_base.json").write_text(
        json.dumps(
            {
                "name": "cl100k_base",
                "pattern": encoding._pat_str,
                "special_tokens": encoding._special_tokens,
                "sha256": EXPECTED_HASH,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Verified tokenizer asset: {EXPECTED_HASH}")


if __name__ == "__main__":
    main()
