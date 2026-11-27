"""Check conditional-answer coverage, archived contexts and preregistered promotion gates."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "eval/results/longmemeval-full-2026-11-12/v2"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def checksum(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def development_counts(rows):
    fixture = read_json(ROOT / "eval/relevance-dev.json")
    labels = {}
    for group in fixture["groups"]:
        values = {doc["id"]: doc["value"].casefold() for doc in group["documents"]}
        for query in group["queries"]:
            labels[query["id"]] = [values[key] for key in query["gold"]]
    assert {(row["question_id"], row["method"]) for row in rows} == {
        (key, mode) for key in labels for mode in ("json_schema", "conditional")
    }
    assert len(rows) == 160
    result = {}
    for mode in ("json_schema", "conditional"):
        valid_negative, positive_gold = 0, 0
        for row in rows:
            if row["method"] != mode:
                continue
            response, gold = row["response"], labels[row["question_id"]]
            if response["error"]:
                continue
            valid_negative += not gold and response["abstain"]
            positive_gold += (
                bool(gold)
                and not response["abstain"]
                and all(value in response["answer"].casefold() for value in gold)
            )
        result[mode] = dict(
            valid_negative_abstentions=valid_negative, positive_gold_included=positive_gold
        )
    return result


def verify(dev, external, score):
    assert checksum(BASELINE / "predictions.jsonl") == (
        "6f2d609e91d6791b839b49c89e9d530491ec9e2c0918cfec5aa02008b21985f6"
    )
    original = {
        row["question_id"]: row
        for row in read_rows(BASELINE / "predictions.jsonl")
        if row["method"] == "learned_hybrid_cross_encoder"
    }
    predictions = read_rows(external / "predictions.jsonl")
    judgments = read_rows(score / "scored.jsonl")
    assert len(predictions) == len(judgments) == len(original) == 500
    assert {row["question_id"] for row in predictions} == set(original)
    assert {row["question_id"] for row in judgments} == set(original)
    assert all(row["method"] == "conditional" for row in predictions + judgments)
    provenance = read_json(external / "provenance.json")
    assert not provenance["dirty_source"] and not provenance["source_changed_during_run"]
    assert provenance["predictions_sha256"] == checksum(external / "predictions.jsonl")
    scorer = read_json(score / "provenance.json")
    assert scorer["predictions_sha256"] == provenance["predictions_sha256"]
    assert not scorer["source_changed_during_run"]
    scored = {row["question_id"]: row for row in judgments}
    invalid, runtime_errors, valid_negative = 0, 0, 0
    for row in predictions:
        prior = original[row["question_id"]]
        response = row["response"]
        assert row["chunk_ids"] == prior["chunk_ids"]
        assert set(response["evidence_ids"]) <= set(row["chunk_ids"])
        assert not response["abstain"] or not response["evidence_ids"]
        assert scored[row["question_id"]]["answer"] == response["answer"]
        assert scored[row["question_id"]]["abstain"] == response["abstain"]
        assert not row["error"]
        invalid += bool(response["error"])
        runtime_errors += response["reason"] == "generation_error"
        valid_negative += (
            row["question_id"].endswith("_abs") and response["abstain"] and not response["error"]
        )
    baseline_scores = [
        row
        for row in read_rows(BASELINE / "score/scored.jsonl")
        if row["method"] == "learned_hybrid_cross_encoder"
    ]
    old_positive = sum(
        row["judge_label"] is True for row in baseline_scores if row["category"] != "abstention"
    )
    old_total = sum(row["judge_label"] is True for row in baseline_scores)
    assert (old_positive, old_total) == (154, 169)
    positive = sum(
        row["judge_label"] is True for row in judgments if row["category"] != "abstention"
    )
    total = sum(row["judge_label"] is True for row in judgments)
    previous_scores = {row["question_id"]: row for row in baseline_scores}
    paired = {}
    for group in ("positive", "abstention"):
        selected = [
            row for row in judgments if (row["category"] == "abstention") == (group == "abstention")
        ]
        paired[group] = dict(
            newly_correct=sum(
                row["judge_label"] is True
                and previous_scores[row["question_id"]]["judge_label"] is not True
                for row in selected
            ),
            previously_correct_lost=sum(
                row["judge_label"] is not True
                and previous_scores[row["question_id"]]["judge_label"] is True
                for row in selected
            ),
            correct_in_both=sum(
                row["judge_label"] is True
                and previous_scores[row["question_id"]]["judge_label"] is True
                for row in selected
            ),
        )
    dev_counts = development_counts(read_rows(dev / "predictions.jsonl"))
    old_dev, new_dev = dev_counts["json_schema"], dev_counts["conditional"]
    gates = dict(
        original_contexts_preserved=True,
        zero_runtime_errors=runtime_errors == 0,
        fewer_invalid_answers=invalid < 108,
        more_valid_negative_abstentions=valid_negative > 6,
        positive_correctness_preserved=positive >= old_positive,
        overall_correctness_preserved=total >= old_total,
        development_negatives_preserved=new_dev["valid_negative_abstentions"]
        >= old_dev["valid_negative_abstentions"],
        development_positives_preserved=new_dev["positive_gold_included"]
        >= old_dev["positive_gold_included"],
        judge_calibration_passed=scorer["calibration_correct"] == scorer["calibration_total"] == 20,
    )
    return {
        "cases": 500,
        "invalid_answers": invalid,
        "runtime_errors": runtime_errors,
        "valid_negative_abstentions": valid_negative,
        "positive_local_judge_correct": positive,
        "overall_local_judge_correct": total,
        "paired_local_judgments": paired,
        "development": dev_counts,
        "promotion_gates": gates,
        "eligible_for_runtime_promotion": all(gates.values()),
        "new_predictions_sha256": provenance["predictions_sha256"],
        "scored_sha256": checksum(score / "scored.jsonl"),
        "checker_sha256": checksum(Path(__file__)),
        "scoring_is_official_or_human": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.dev, args.external, args.score)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
