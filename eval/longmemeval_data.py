"""Pinned LongMemEval S input, metadata-only subset selection, and label-free corpus parsing."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from governed_memory.local_models import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    RERANKING_MODEL,
    RERANKING_REVISION,
)

MODEL_PROFILES = {
    "embedding": {"model": EMBEDDING_MODEL, "revision": EMBEDDING_REVISION},
    "reranking": {"model": RERANKING_MODEL, "revision": RERANKING_REVISION},
}
DATASET = "xiaowu0162/longmemeval-cleaned"
REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
FILENAME = "longmemeval_s_cleaned.json"
SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
SEED = "governed-memory-longmemeval-v1"
MANIFEST = Path(__file__).parent / "longmemeval_manifest.json"


def verify_dataset(path: Path):
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
            raise ValueError("LongMemEval data does not match the pinned cleaned-S file")


def records(path: Path):
    import ijson

    with path.open("rb") as stream:
        yield from ijson.items(stream, "item")


def category(record):
    return "abstention" if record["question_id"].endswith("_abs") else record["question_type"]


def freeze_subset(path: Path, destination: Path = MANIFEST):
    if destination.exists():
        raise FileExistsError("the subset is already frozen; do not tune it against outcomes")
    verify_dataset(path)
    groups = defaultdict(list)
    for record in records(path):
        groups[category(record)].append(record["question_id"])
    chosen = []
    for name, ids in sorted(groups.items()):
        ordered = sorted(ids, key=lambda value: hashlib.sha256(f"{SEED}:{value}".encode()).digest())
        chosen.extend({"id": value, "category": name} for value in ordered[:2])
    manifest = {
        "dataset": DATASET,
        "revision": REVISION,
        "file": FILENAME,
        "sha256": SHA256,
        "models": MODEL_PROFILES,
        "seed": SEED,
        "selection": "first two IDs per category ordered by SHA-256(seed:id)",
        "selection_fields": ["question_id", "question_type"],
        "cases": chosen,
        "k": 8,
        "token_budget": 2048,
        "rerank_pool": 50,
        "chunk_wordpieces": 200,
        "chunk_overlap": 40,
        "methods": ["bm25", "learned_hybrid", "learned_hybrid_cross_encoder"],
        "scope": "session-evidence retrieval from full provided S histories; no QA scoring",
    }
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def timestamp(value: str):
    # Benchmark dates omit a zone; UTC is used only as a uniform ordering convention.
    value = re.sub(r"\s+\([^)]*\)", "", value)
    return datetime.strptime(value, "%Y/%m/%d %H:%M").replace(tzinfo=UTC)


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class HistorySession:
    id: str
    date: str
    messages: tuple[Message, ...]


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    category: str
    question: str
    question_date: str
    sessions: tuple[HistorySession, ...]


def retrieval_case(record) -> RetrievalCase:
    """Only these fields cross the retrieval boundary; labels stay in the scoring stage."""
    sessions = []
    for session_id, date, messages in zip(
        record["haystack_session_ids"],
        record["haystack_dates"],
        record["haystack_sessions"],
        strict=True,
    ):
        sessions.append(
            HistorySession(
                session_id,
                date,
                tuple(Message(message["role"], message["content"]) for message in messages),
            )
        )
    return RetrievalCase(
        record["question_id"],
        category(record),
        record["question"],
        record["question_date"],
        tuple(sessions),
    )


@dataclass(frozen=True)
class Chunk:
    id: str
    session_id: str
    date: str
    message_index: int
    start: int
    end: int
    text: str


def chunks(case: RetrievalCase, tokenizer, config):
    result, excluded = [], []
    width, overlap = config["chunk_wordpieces"], config["chunk_overlap"]
    for session in case.sessions:
        if timestamp(session.date) > timestamp(case.question_date):
            excluded.append(session.id)
            continue
        for index, message in enumerate(session.messages):
            offsets = tokenizer(
                message.content,
                add_special_tokens=False,
                return_offsets_mapping=True,
                verbose=False,
            )["offset_mapping"]
            for position in range(0, len(offsets), width - overlap):
                window = offsets[position : position + width]
                start, end = window[0][0], window[-1][1]
                key = f"{case.id}:{session.id}:{index}:{start}:{end}"
                text = f"{session.date} {message.role}: {message.content[start:end]}"
                result.append(
                    Chunk(
                        hashlib.sha256(key.encode()).hexdigest()[:24],
                        session.id,
                        session.date,
                        index,
                        start,
                        end,
                        text,
                    )
                )
                if position + width >= len(offsets):
                    break
    return result, excluded


def selected_cases(path: Path, manifest):
    ids = {item["id"] for item in manifest["cases"]}
    found = set()
    for record in records(path):
        if record["question_id"] in ids:
            found.add(record["question_id"])
            yield retrieval_case(record)
    if found != ids:
        raise ValueError("the dataset is missing frozen question IDs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.download:
        from huggingface_hub import hf_hub_download

        if args.dataset.name != FILENAME:
            raise ValueError(f"the destination file must be named {FILENAME}")
        hf_hub_download(
            DATASET,
            FILENAME,
            repo_type="dataset",
            revision=REVISION,
            local_dir=args.dataset.parent,
            token=False,
        )
    verify_dataset(args.dataset)
    if args.freeze:
        print(json.dumps(freeze_subset(args.dataset), indent=2))
    else:
        print(f"Verified {FILENAME}: {SHA256}")


if __name__ == "__main__":
    main()
