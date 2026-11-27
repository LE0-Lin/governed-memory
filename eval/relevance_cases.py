"""Deterministic synthetic relevance fixtures; labels describe explicit available facts."""

import json
from pathlib import Path

# Each specification has four available attributes, two missing-attribute questions,
# and one unrelated question. The primary attribute also gets a paraphrase and keyword query.
SPECS = [
    (
        "dev",
        "Polaris service",
        [
            ("database", "PostgreSQL", "Which database does Polaris service use?"),
            ("deployment region", "Frankfurt", "Where is Polaris service deployed?"),
            ("log retention", "fourteen days", "How long does Polaris service retain logs?"),
            ("backup schedule", "nightly", "How often does Polaris service run backups?"),
        ],
        "What stores persistent records for Polaris service?",
        [
            "What is the monthly budget for Polaris service?",
            "What license covers Polaris service?",
            "What is the longest river in Brazil?",
        ],
    ),
    (
        "dev",
        "Mira onboarding",
        [
            ("mentor", "Leah", "Who mentors Mira during onboarding?"),
            ("office", "Bristol", "Which office hosts Mira onboarding?"),
            ("training duration", "two weeks", "How long does Mira onboarding training last?"),
            ("laptop", "ThinkPad", "What laptop is provided for Mira onboarding?"),
        ],
        "Who guides the new starter in Mira onboarding?",
        [
            "What university did Mira attend?",
            "What salary is offered in Mira onboarding?",
            "How many moons does Neptune have?",
        ],
    ),
    (
        "dev",
        "Solstice workshop",
        [
            ("venue", "Harbor Hall", "Where is Solstice workshop held?"),
            ("city", "Oslo", "Which city hosts Solstice workshop?"),
            ("duration", "three hours", "How long does Solstice workshop last?"),
            (
                "capacity",
                "forty participants",
                "How many participants can attend Solstice workshop?",
            ),
        ],
        "What building will host Solstice workshop?",
        [
            "What does admission to Solstice workshop cost?",
            "Who sponsors Solstice workshop?",
            "What temperature does copper melt at?",
        ],
    ),
    (
        "dev",
        "Nimbus documentation",
        [
            ("format", "Markdown", "What format does Nimbus documentation use?"),
            ("language", "English", "What language is Nimbus documentation written in?"),
            ("owner", "developer experience team", "Who owns Nimbus documentation?"),
            ("review cadence", "every month", "How often is Nimbus documentation reviewed?"),
        ],
        "How are the Nimbus documentation files formatted?",
        [
            "What is the license for Nimbus documentation?",
            "How many pages are in Nimbus documentation?",
            "Who discovered penicillin?",
        ],
    ),
    (
        "dev",
        "Saffron analytics",
        [
            ("warehouse", "BigQuery", "Which warehouse does Saffron analytics use?"),
            ("refresh interval", "six hours", "How often is Saffron analytics refreshed?"),
            ("timezone", "UTC", "Which timezone does Saffron analytics use?"),
            ("owner", "business intelligence team", "Who maintains Saffron analytics?"),
        ],
        "Where does Saffron analytics keep its analytical tables?",
        [
            "What is the annual cost of Saffron analytics?",
            "How many customers use Saffron analytics?",
            "How far is Venus from the Sun?",
        ],
    ),
    (
        "dev",
        "Maple expense policy",
        [
            ("currency", "EUR", "Which currency does Maple expense policy use?"),
            (
                "meal allowance",
                "thirty euros",
                "What meal allowance does Maple expense policy permit?",
            ),
            (
                "submission deadline",
                "ten days",
                "What is the submission deadline in Maple expense policy?",
            ),
            ("approver", "finance manager", "Who approves claims under Maple expense policy?"),
        ],
        "In what money unit are Maple expense policy amounts stated?",
        [
            "What is the mileage rate under Maple expense policy?",
            "What hotel limit does Maple expense policy set?",
            "What causes a lunar eclipse?",
        ],
    ),
    (
        "dev",
        "Coral access policy",
        [
            (
                "authentication",
                "hardware security keys",
                "How do users authenticate under Coral access policy?",
            ),
            (
                "review interval",
                "ninety days",
                "How often is access reviewed under Coral access policy?",
            ),
            ("owner", "security operations team", "Who owns Coral access policy?"),
            (
                "session duration",
                "eight hours",
                "How long can a session last under Coral access policy?",
            ),
        ],
        "What login credential does Coral access policy require?",
        [
            "What password length does Coral access policy require?",
            "What encryption algorithm does Coral access policy specify?",
            "When was the first steam locomotive built?",
        ],
    ),
    (
        "dev",
        "Willow release",
        [
            ("version", "3.4.1", "What version is Willow release?"),
            ("channel", "stable", "Which channel carries Willow release?"),
            ("supported platform", "Linux", "What platform supports Willow release?"),
            ("maintainer", "runtime team", "Who maintains Willow release?"),
        ],
        "What version number identifies Willow release?",
        [
            "When did Willow release ship?",
            "How large is the download for Willow release?",
            "How many bones are in an adult human hand?",
        ],
    ),
    (
        "heldout",
        "Orchid library",
        [
            ("license", "Apache 2.0", "What license covers Orchid library?"),
            ("implementation language", "Rust", "What language implements Orchid library?"),
            (
                "minimum compiler",
                "1.83",
                "What is the minimum compiler version for Orchid library?",
            ),
            ("maintainer", "systems team", "Who maintains Orchid library?"),
        ],
        "Under which terms can Orchid library be redistributed?",
        [
            "How many downloads does Orchid library have?",
            "What price is charged for Orchid library?",
            "What makes the ocean appear blue?",
        ],
    ),
    (
        "heldout",
        "Cobalt parcel",
        [
            ("carrier", "DHL", "Which carrier transports Cobalt parcel?"),
            ("destination", "Lisbon", "Where is Cobalt parcel going?"),
            ("weight", "two kilograms", "How much does Cobalt parcel weigh?"),
            ("service", "express", "What shipping service does Cobalt parcel use?"),
        ],
        "Which delivery company handles Cobalt parcel?",
        [
            "When will Cobalt parcel arrive?",
            "What is the tracking number for Cobalt parcel?",
            "What is the boiling point of ethanol?",
        ],
    ),
    (
        "heldout",
        "Dahlia lab",
        [
            ("room", "B204", "Which room houses Dahlia lab?"),
            ("opening hours", "nine to five", "When is Dahlia lab open?"),
            ("supervisor", "Nora", "Who supervises Dahlia lab?"),
            ("equipment", "optical microscopes", "What equipment is available in Dahlia lab?"),
        ],
        "What room number should visitors use for Dahlia lab?",
        [
            "What is the budget for Dahlia lab?",
            "How many students work in Dahlia lab?",
            "How long is the Nile?",
        ],
    ),
    (
        "heldout",
        "Finch subscription",
        [
            ("billing period", "quarterly", "How often is Finch subscription billed?"),
            ("price", "ninety pounds", "What is the price of Finch subscription?"),
            (
                "included storage",
                "one terabyte",
                "How much storage does Finch subscription include?",
            ),
            (
                "cancellation notice",
                "seven days",
                "What notice is required to cancel Finch subscription?",
            ),
        ],
        "What interval separates Finch subscription invoices?",
        [
            "What payment card funds Finch subscription?",
            "When did Finch subscription begin?",
            "Why do leaves change color in autumn?",
        ],
    ),
    (
        "heldout",
        "Helix recipe",
        [
            ("main ingredient", "chickpeas", "What is the main ingredient in Helix recipe?"),
            ("cooking time", "twenty minutes", "How long does Helix recipe take to cook?"),
            ("servings", "four", "How many servings does Helix recipe make?"),
            ("oven temperature", "180 Celsius", "What oven temperature does Helix recipe require?"),
        ],
        "What food forms the base of Helix recipe?",
        [
            "How many calories are in Helix recipe?",
            "What allergens are listed for Helix recipe?",
            "What planet has the shortest day?",
        ],
    ),
    (
        "heldout",
        "Piper course",
        [
            ("instructor", "Elena", "Who teaches Piper course?"),
            ("duration", "six weeks", "How long does Piper course run?"),
            ("assessment", "a final project", "How is Piper course assessed?"),
            ("delivery mode", "online", "How is Piper course delivered?"),
        ],
        "Who is the teacher responsible for Piper course?",
        [
            "How much tuition does Piper course charge?",
            "What grade is required to pass Piper course?",
            "When was Saturn discovered?",
        ],
    ),
    (
        "heldout",
        "Topaz garden",
        [
            ("watering interval", "every three days", "How often is Topaz garden watered?"),
            ("primary crop", "tomatoes", "What is the primary crop in Topaz garden?"),
            ("soil type", "loam", "What soil type is used in Topaz garden?"),
            ("caretaker", "Owen", "Who looks after Topaz garden?"),
        ],
        "What is the irrigation schedule for Topaz garden?",
        [
            "What is the area of Topaz garden?",
            "How much did Topaz garden cost?",
            "Why do magnets attract iron?",
        ],
    ),
    (
        "heldout",
        "Vesta recording",
        [
            ("file format", "FLAC", "What file format is Vesta recording stored in?"),
            ("sample rate", "48 kilohertz", "What sample rate does Vesta recording use?"),
            ("duration", "twelve minutes", "How long is Vesta recording?"),
            ("producer", "audio team", "Who produced Vesta recording?"),
        ],
        "What encoding container is used for Vesta recording?",
        [
            "Who performed on Vesta recording?",
            "When was Vesta recording released?",
            "What is the tallest mountain in Argentina?",
        ],
    ),
]


MISSING_ENTITIES = [
    "Rigel service",
    "Mina onboarding",
    "Arbor workshop",
    "Fable documentation",
    "Citrine analytics",
    "Pine expense policy",
    "Indigo access policy",
    "Aspen release",
    "Ochre library",
    "Silver parcel",
    "Lotus lab",
    "Wren subscription",
    "Hearth recipe",
    "Robin course",
    "Garnet garden",
    "Nova recording",
]


def build(split):
    groups = []
    for number, (group_split, subject, facts, paraphrase, negatives) in enumerate(SPECS):
        if group_split != split:
            continue
        group_id = f"{split}-{number:02}"
        documents = [
            dict(id=f"{group_id}-d{i}", subject=subject, predicate=predicate, value=value)
            for i, (predicate, value, _) in enumerate(facts)
        ]
        positive = [
            (question, [documents[i]["id"]], "direct") for i, (_, _, question) in enumerate(facts)
        ]
        positive.extend(
            [
                (paraphrase, [documents[0]["id"]], "paraphrase"),
                (f"{subject} {facts[0][0]}", [documents[0]["id"]], "keyword"),
            ]
        )
        missing = [
            (question, [], "missing_attribute" if i < 2 else "unrelated")
            for i, question in enumerate(negatives)
        ]
        missing.append(
            (f"What is the {facts[0][0]} for {MISSING_ENTITIES[number]}?", [], "unknown_entity")
        )
        queries = [
            dict(id=f"{group_id}-q{i}", query=query, gold=gold, kind=kind)
            for i, (query, gold, kind) in enumerate(positive + missing)
        ]
        groups.append(dict(id=group_id, documents=documents, queries=queries))
    return dict(version="relevance-contract-v1", split=split, groups=groups)


if __name__ == "__main__":
    for split in ("dev", "heldout"):
        path = Path(__file__).with_name(f"relevance-{split}.json")
        if path.exists():
            raise SystemExit("frozen relevance fixtures already exist")
        path.write_text(json.dumps(build(split), indent=2) + "\n", encoding="utf-8", newline="\n")
