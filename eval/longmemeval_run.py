"""Frozen retrieval-only comparison. Save predictions before opening score labels."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from rank_bm25 import BM25Okapi

from eval.longmemeval_data import MANIFEST, MODEL_PROFILES, chunks, selected_cases, verify_dataset
from eval.longmemeval_score import score
from governed_memory.answering import generate_answer
from governed_memory.budget import EvidenceBudget, serialize
from governed_memory.embedding import words
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.retrieval import fusion_order

ROOT = Path(__file__).resolve().parents[1]


def source_snapshot():
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "src").rglob("*.rego"))
    files += sorted((ROOT / "eval").glob("*.py"))
    return {
        "code_sha256": hashlib.sha256(
            b"".join(
                p.relative_to(ROOT).as_posix().encode()
                + b"\0"
                + p.read_bytes().replace(b"\r\n", b"\n")
                for p in files
            )
        ).hexdigest(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--", "src", "eval/*.py"], cwd=ROOT, text=True
            ).strip()
        ),
    }


def empty_predictions(case, config, *, error=None, excluded=()):
    return [
        {
            "question_id": case.id,
            "category": case.category,
            "method": method,
            "chunk_ids": [],
            "session_ids": [],
            "evidence_tokens": 1,
            "latency_ms": 0,
            "candidate_scores": [],
            "error": error,
            "index": {
                "chunks": 0,
                "sessions": 0,
                "excluded_future_sessions": list(excluded),
                "lexical_ms": 0,
                "embedding_ms": 0,
            },
        }
        for method in config["methods"]
    ]


async def retrieve_case(case, config, embedder, reranker, budget, generator=None):
    started = perf_counter()
    documents, excluded = chunks(case, embedder.model.tokenizer, config)
    if not documents:
        rows = empty_predictions(case, config, excluded=excluded)
        if generator is not None:
            for row in rows:
                row["response"] = await generate_answer(
                    generator, case.question, [], retain_raw=True
                )
                row["answer_latency_ms"] = 0
        return rows
    corpus = [words(document.text) or [""] for document in documents]
    lexical_index = BM25Okapi(corpus)
    lexical_index_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    vectors = np.array(await embedder.create_batch([document.text for document in documents]))
    embedding_index_ms = (perf_counter() - started) * 1000
    rows = []
    for method in config["methods"]:
        started = perf_counter()
        error, candidate_scores = None, []
        try:
            lexical = lexical_index.get_scores(words(case.question))
            ids = [document.id for document in documents]
            if method == "bm25":
                order = sorted(range(len(documents)), key=lambda i: (-lexical[i], ids[i]))
            else:
                query_vector = np.array(await embedder.create(case.question))
                order = fusion_order(lexical, vectors @ query_vector, ids)
            ranked = [documents[i] for i in order]
            if method == "learned_hybrid_cross_encoder":
                candidates = ranked[: config["rerank_pool"]]
                scores = await reranker.scores(
                    case.question, [document.text for document in candidates]
                )
                candidate_scores = [
                    {"chunk_id": doc.id, "score": value}
                    for doc, value in zip(candidates, scores, strict=True)
                ]
                ranked = [
                    doc
                    for doc, value in sorted(
                        zip(candidates, scores, strict=True),
                        key=lambda pair: (-pair[1], pair[0].id),
                    )
                ]
            evidence, tokens = budget.pack(ranked, config["token_budget"], config["k"])
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            evidence, tokens = [], 1
        # Serialization is included. Public output stores IDs rather than copying conversations.
        serialize(evidence)
        row = {
            "question_id": case.id,
            "category": case.category,
            "method": method,
            "chunk_ids": [item["id"] for item in evidence],
            "session_ids": list(dict.fromkeys(item["session_id"] for item in evidence)),
            "evidence_tokens": tokens,
            "latency_ms": (perf_counter() - started) * 1000,
            "candidate_scores": candidate_scores,
            "error": error,
            "index": {
                "chunks": len(documents),
                "sessions": len(case.sessions) - len(excluded),
                "excluded_future_sessions": excluded,
                "lexical_ms": lexical_index_ms,
                "embedding_ms": embedding_index_ms,
            },
        }
        if generator is not None:
            generation_start = perf_counter()
            row["response"] = await generate_answer(
                generator,
                case.question,
                evidence,
                case.question_date,
                max_new_tokens=config["generation_max_tokens"],
                retain_raw=True,
            )
            serialize(row["response"])
            row["answer_latency_ms"] = (
                row["latency_ms"] + (perf_counter() - generation_start) * 1000
            )
        rows.append(row)
    return rows


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path)
    args = parser.parse_args()
    verify_dataset(args.dataset)
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if config["models"] != MODEL_PROFILES:
        raise ValueError("model profiles differ from the frozen protocol")
    if args.output.exists():
        raise FileExistsError("use a new run directory to preserve prior predictions")
    args.output.mkdir(parents=True)
    initial_source = source_snapshot()
    embedder, reranker = MiniLMEmbedder(args.model_cache), MiniLMReranker(args.model_cache)
    budget = EvidenceBudget()
    # Warm kernels without reading any selected history or scoring labels.
    await embedder.create("A fictional example warms the encoder.")
    await reranker.scores("database", ["The service uses PostgreSQL."])
    predictions = args.output / "predictions.jsonl"
    with predictions.open("w", encoding="utf-8") as output:
        for number, case in enumerate(selected_cases(args.dataset, config), 1):
            started = perf_counter()
            try:
                rows = await retrieve_case(case, config, embedder, reranker, budget)
            except Exception as exc:
                rows = empty_predictions(case, config, error=f"{type(exc).__name__}: {exc}")
                elapsed = (perf_counter() - started) * 1000
                for row in rows:
                    row["latency_ms"] = elapsed
            for row in rows:
                output.write(serialize(row) + "\n")
            output.flush()
            print(
                f"{number}/{len(config['cases'])}: {case.id}, "
                f"{rows[0]['index']['chunks']} chunks, {perf_counter() - started:.1f}s",
                flush=True,
            )
    prediction_hash = hashlib.sha256(predictions.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    # Only the scorer opens answer_session_ids, after prediction bytes have been finalized.
    scored, summary = score(args.dataset, predictions)
    (args.output / "scored.jsonl").write_text(
        "".join(serialize(row) + "\n" for row in scored), encoding="utf-8"
    )
    (args.output / "summary.json").write_text(serialize(summary) + "\n", encoding="utf-8")
    final_source = source_snapshot()
    provenance = {
        "ran_at": datetime.now(UTC).isoformat(),
        "manifest": config,
        "predictions_sha256": prediction_hash,
        **initial_source,
        "source_changed_during_run": initial_source["code_sha256"] != final_source["code_sha256"],
        "embedding": embedder.metadata,
        "reranker": reranker.metadata,
        "os": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "concurrency": 1,
        "timing": "warm models; no query cache; document indexing measured separately",
        "failures": sum(bool(row["error"]) for row in scored),
        "timeouts": 0,
        "timeout_policy": "no inference timeout; sequential CPU inference",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "sentence-transformers", "transformers", "numpy", "rank-bm25")
        },
    }
    (args.output / "provenance.json").write_text(serialize(provenance) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {name: values for name, values in summary.items() if name.endswith("/all")}, indent=2
        )
    )
    if provenance["failures"] or provenance["source_changed_during_run"]:
        raise SystemExit("retrieval failures are retained in the run output")


if __name__ == "__main__":
    asyncio.run(main())
