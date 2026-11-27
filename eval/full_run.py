"""All 500 pinned cleaned-S histories, retrieval and generation, with resumable case files."""

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

from eval.longmemeval_data import (
    DATASET,
    FILENAME,
    MODEL_PROFILES,
    REVISION,
    SHA256,
    category,
    records,
    selected_cases,
    verify_dataset,
)
from eval.longmemeval_run import empty_predictions, retrieve_case, source_snapshot
from eval.longmemeval_score import score
from governed_memory.answering import generate_answer
from governed_memory.budget import EvidenceBudget, serialize
from governed_memory.generation import GENERATION_PROFILES, TransformersGenerator
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker

MANIFEST = Path(__file__).with_name("full_manifest.json")
STRUCTURED_MANIFEST = Path(__file__).with_name("full_structured_manifest.json")


def versions():
    return {
        name: importlib.metadata.version(name)
        for name in (
            "governed-memory",
            "torch",
            "transformers",
            "sentence-transformers",
            "numpy",
            "rank-bm25",
            "accelerate",
            "lm-format-enforcer",
        )
    }


def hardware(device):
    if device == "cpu":
        return {"device": device, "processor": platform.processor()}
    import torch

    try:
        driver = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        driver = None
    return {
        "device": device,
        "gpu": torch.cuda.get_device_name(0),
        "cuda": torch.version.cuda,
        "capability": list(torch.cuda.get_device_capability(0)),
        "driver": driver,
    }


def freeze(path, destination=STRUCTURED_MANIFEST):
    if destination.exists():
        raise FileExistsError("the full protocol is already frozen")
    verify_dataset(path)
    cases = [{"id": row["question_id"], "category": category(row)} for row in records(path)]
    if len(cases) != 500 or len({row["id"] for row in cases}) != 500:
        raise ValueError("expected all 500 unique cleaned-S questions")
    generation, judge = GENERATION_PROFILES["standard"], GENERATION_PROFILES["judge"]
    config = {
        "protocol": "full-cleaned-s-v2-structured",
        "answer_format": "json_schema",
        "format_enforcer_revision": "2597936f55da0e3cab8a6047eba91b2ecdfe888a",
        "dataset": DATASET,
        "revision": REVISION,
        "file": FILENAME,
        "sha256": SHA256,
        "selection": "all 500 questions; no answer-based filtering",
        "selection_fields": ["question_id", "question_type"],
        "cases": sorted(cases, key=lambda row: row["id"]),
        "retrieval_models": MODEL_PROFILES,
        "generation": {
            "profile": "standard",
            "model": generation.model,
            "revision": generation.revision,
        },
        "judge": {"profile": "judge", "model": judge.model, "revision": judge.revision},
        "generation_max_tokens": 384,
        "judge_max_tokens": 12,
        "max_input_tokens": 4096,
        "methods": ["bm25", "learned_hybrid", "learned_hybrid_cross_encoder"],
        "k": 8,
        "token_budget": 2048,
        "rerank_pool": 50,
        "chunk_wordpieces": 200,
        "chunk_overlap": 40,
        "decoding": "greedy",
        "scope": "retrieval and cited generation, without organization governance labels",
    }
    destination.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialize(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


async def run(args):
    verify_dataset(args.dataset)
    config = read_json(args.manifest)
    if config.get("answer_format") != "json_schema":
        raise ValueError("use commit 54b2593 to reproduce the unconstrained v1 protocol")
    manifest_hash = hashlib.sha256(args.manifest.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    initial = source_snapshot()
    if initial["dirty_source"]:
        raise ValueError("commit inference sources before starting or resuming the frozen run")
    if args.output.exists():
        if not args.resume:
            raise FileExistsError("use --resume with unchanged code, or a new output directory")
        original = read_json(args.output / "start.json")
        if any(
            original[key] != value
            for key, value in {
                "manifest_sha256": manifest_hash,
                "code_sha256": initial["code_sha256"],
                "device": args.device,
                "versions": versions(),
                "hardware": hardware(args.device),
            }.items()
        ):
            raise ValueError("resume requires the identical frozen protocol, source and device")
    else:
        args.output.mkdir(parents=True)
        original = {
            **initial,
            "manifest_sha256": manifest_hash,
            "device": args.device,
            "started_at": datetime.now(UTC).isoformat(),
            "manifest": config,
            "versions": versions(),
            "hardware": hardware(args.device),
        }
        write_json(args.output / "start.json", original)
    cases_folder = args.output / "cases"
    cases_folder.mkdir(exist_ok=True)
    embedder = MiniLMEmbedder(args.model_cache, device=args.device)
    reranker = MiniLMReranker(args.model_cache, device=args.device)
    generator = TransformersGenerator(
        "standard", args.generation_cache, args.device, config["max_input_tokens"]
    )
    budget = EvidenceBudget()
    # Synthetic warmup only; no selected question, history or score label is inspected.
    await embedder.create("A fictional example warms the encoder.")
    await reranker.scores("database", ["The fictional service uses SQLite."])
    await generate_answer(
        generator,
        "Which database?",
        [{"id": "warmup", "text": "The fictional service uses SQLite."}],
    )
    for number, case in enumerate(selected_cases(args.dataset, config), 1):
        path = cases_folder / (case.id + ".json")
        if path.exists():
            saved = read_json(path)
            if {row["method"] for row in saved} != set(config["methods"]) or any(
                row["question_id"] != case.id for row in saved
            ):
                raise ValueError("invalid saved case")
            continue
        started = perf_counter()
        try:
            rows = await retrieve_case(case, config, embedder, reranker, budget, generator)
        except Exception as exc:
            rows = empty_predictions(case, config, error=f"{type(exc).__name__}: {exc}")
        write_json(path, rows)
        errors = sum(bool(row.get("error") or row.get("response", {}).get("error")) for row in rows)
        print(
            f"{number}/500: {case.id}, {perf_counter() - started:.1f}s, response errors={errors}",
            flush=True,
        )
    rows = []
    for case in config["cases"]:
        rows.extend(read_json(cases_folder / (case["id"] + ".json")))
    predictions = args.output / "predictions.jsonl"
    predictions.write_text("".join(serialize(row) + "\n" for row in rows), encoding="utf-8")
    # Retrieval labels are opened only after every answer has been finalized.
    scored, summary = score(args.dataset, predictions)
    write_json(args.output / "retrieval-summary.json", summary)
    (args.output / "retrieval-scored.jsonl").write_text(
        "".join(serialize(row) + "\n" for row in scored), encoding="utf-8"
    )
    final = source_snapshot()
    provenance = {
        **original,
        "finished_at": datetime.now(UTC).isoformat(),
        "generator": generator.metadata,
        "embedding": embedder.metadata,
        "reranker": reranker.metadata,
        "source_changed_during_run": final["code_sha256"] != initial["code_sha256"],
        "predictions_sha256": hashlib.sha256(
            predictions.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "rows": len(rows),
        "retrieval_errors": sum(bool(row.get("error")) for row in rows),
        "invalid_answers": sum(
            row.get("response", {}).get("error") == "InvalidAnswer" for row in rows
        ),
        "generation_errors": sum(
            row.get("response", {}).get("reason") == "generation_error" for row in rows
        ),
        "os": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "timing": "warm kernels; per-history indexing separate; no query/answer cache",
        "versions": versions(),
    }
    if args.device == "cuda":
        import torch

        provenance["gpu"] = torch.cuda.get_device_name(0)
        provenance["cuda_runtime"] = torch.version.cuda
    write_json(args.output / "provenance.json", provenance)
    print(
        serialize(
            {
                key: provenance[key]
                for key in ("rows", "retrieval_errors", "invalid_answers", "generation_errors")
            }
        )
    )
    if (
        provenance["source_changed_during_run"]
        or provenance["retrieval_errors"]
        or provenance["generation_errors"]
    ):
        raise SystemExit("execution failures were retained; inspect the run before making claims")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=STRUCTURED_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-cache", type=Path)
    parser.add_argument("--generation-cache", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--freeze-manifest", action="store_true")
    args = parser.parse_args()
    if args.freeze_manifest:
        print(f"Frozen {len(freeze(args.dataset, args.manifest)['cases'])} cases")
    elif args.output is None:
        parser.error("--output is required for inference")
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
