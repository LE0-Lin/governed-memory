# Third-party components

The governance, ledger, retrieval constraints, CLI/MCP integration and synthetic evaluation are application code in this repository. The graph engine, tokenizer and retrieval libraries are reused dependencies.

| Component | Use | Upstream |
| --- | --- | --- |
| Graphiti 0.31.2 (Apache-2.0) | Direct graph node/edge persistence, full-text/vector search and RRF | [getzep/graphiti](https://github.com/getzep/graphiti/tree/v0.31.2) |
| rank-bm25 0.2.2 (Apache-2.0) | Local BM25 scoring | [dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) |
| tiktoken (MIT) | Evidence token accounting | [openai/tiktoken](https://github.com/openai/tiktoken) |
| SQLAlchemy, psycopg, MCP Python SDK and NumPy | Storage, transport and vector arithmetic | Exact versions are in `uv.lock`; distributions retain their own licenses |

`src/governed_memory/data/cl100k_base.tiktoken` and its pattern/special-token metadata are vendored from tiktoken's public `cl100k_base` encoding. Copyright (c) 2022 OpenAI, Shantanu Jain. The full MIT notice is retained in [third_party/tiktoken-LICENSE](third_party/tiktoken-LICENSE). The vocabulary SHA-256 is `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`; the refresh script verifies it before writing. Runtime loading uses this local asset and does not download a tokenizer.

Graphiti source code has not been copied into this package. Its LLM extraction, entity resolution and contradiction handling are deliberately excluded from the trusted projection path. Neo4j and PostgreSQL run as separate upstream container images, whose licensing and distribution notices remain with those images.

All example conversations and evaluation records are synthetic. They contain no private user documents, conversations or credentials.
