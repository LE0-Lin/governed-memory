"""Scale the frozen CV timelines without learning labels from ledger output."""

import copy
import re

from eval.retrieval_evidence import load_cases


def scaled_timelines(cohorts):
    if isinstance(cohorts, bool) or cohorts not in (1, 4, 16):
        raise ValueError("timeline cohorts must be 1, 4 or 16")
    base = load_cases("legacy_cv")
    if cohorts == 1:
        return base
    names = sorted({fact["alias"].partition(".")[0] for fact in base["facts"]})
    pattern = re.compile(r"\b(" + "|".join(re.escape(name) for name in names) + r")\b")

    def alias(cohort, original):
        return f"cohort-{cohort + 1:02}/{original}"

    def wording(cohort, original):
        return pattern.sub(lambda match: f"Workspace {cohort + 1:02} {match.group()}", original)

    facts = []
    for cohort in range(cohorts):
        for original in base["facts"]:
            fact = copy.deepcopy(original)
            fact["alias"] = alias(cohort, fact["alias"])
            fact["subject"] = wording(cohort, fact["subject"])
            if fact.get("parent"):
                fact["parent"] = alias(cohort, fact["parent"])
            facts.append(fact)
    queries = []
    for index, original in enumerate(base["queries"]):
        cohort = index % cohorts
        query = copy.deepcopy(original)
        query.update(
            id=alias(cohort, query["id"]),
            query=wording(cohort, query["query"]),
            gold=[alias(cohort, identifier) for identifier in query["gold"]],
            eligible=[
                alias(group, identifier)
                for group in range(cohorts)
                for identifier in query["eligible"]
            ],
        )
        queries.append(query)
    return {**base, "version": f"cv-scaled-{cohorts}", "facts": facts, "queries": queries}
