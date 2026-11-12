import json

import pytest

from governed_memory.answering import answer_schema, parse_answer


def accepts(parser, text):
    for character in text:
        if character not in parser.get_allowed_characters():
            return False
        parser = parser.add_character(character)
    return parser.can_end()


@pytest.mark.parametrize(
    "reply,expected",
    [
        ({"answer": "数据库 🧪", "evidence_ids": ["E1"], "abstain": False}, True),
        ({"answer": "Unknown", "evidence_ids": [], "abstain": True}, True),
        ({"answer": "SQLite", "evidence_ids": ["E2"], "abstain": False}, False),
        ({"answer": "SQLite", "evidence_ids": ["E1"], "abstain": []}, False),
        ({"answer": "SQLite", "evidence_ids": "E1", "abstain": False}, False),
        ({"answer": "SQLite", "evidence_ids": ["E1"], "abstain": False, "extra": 1}, False),
    ],
)
def test_schema_constrains_types_fields_and_available_citation_aliases(reply, expected):
    library = pytest.importorskip("lmformatenforcer")
    from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig

    config = CharacterLevelParserConfig()
    config.alphabet += "数据库 🧪"
    parser = library.JsonSchemaParser(answer_schema([{"id": "real-source"}]), config)
    assert accepts(parser, json.dumps(reply, ensure_ascii=False)) is expected


def test_schema_does_not_replace_semantic_citation_validation():
    # JSON shape alone cannot establish that an answered question cites a source.
    with pytest.raises(ValueError, match="supporting citations"):
        parse_answer(
            '{"answer":"SQLite","evidence_ids":[],"abstain":false}', [{"id": "real-source"}]
        )
