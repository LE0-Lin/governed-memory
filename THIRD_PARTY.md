# Third-party components

The governance, ledger, retrieval constraints, CLI/MCP integration and synthetic evaluation are application code in this repository. The graph engine, tokenizer and retrieval libraries are reused dependencies.

| Component | Use | Upstream |
| --- | --- | --- |
| Graphiti 0.31.2 (Apache-2.0) | Direct graph node/edge persistence, full-text/vector search and RRF | [getzep/graphiti](https://github.com/getzep/graphiti/tree/v0.31.2) |
| rank-bm25 0.2.2 (Apache-2.0) | Local BM25 scoring | [dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) |
| tiktoken (MIT) | Evidence token accounting | [openai/tiktoken](https://github.com/openai/tiktoken) |
| Open Policy Agent (Apache-2.0) | Optional policy decisions, using an official separate container | [open-policy-agent/opa](https://github.com/open-policy-agent/opa) |
| Sentence Transformers (Apache-2.0), Transformers (Apache-2.0), PyTorch (BSD-style) | Optional embedding, cross-encoder and answer inference | [Sentence Transformers](https://github.com/huggingface/sentence-transformers), [Transformers](https://github.com/huggingface/transformers), [PyTorch](https://github.com/pytorch/pytorch) |
| LM Format Enforcer (MIT), pinned upstream revision | JSON Schema constraints via the standard Transformers prefix-token callback | [noamgat/lm-format-enforcer](https://github.com/noamgat/lm-format-enforcer/tree/2597936f55da0e3cab8a6047eba91b2ecdfe888a) |
| SQLAlchemy, psycopg, MCP Python SDK and NumPy | Storage, transport and vector arithmetic | Exact versions are in `uv.lock`; distributions retain their own licenses |

`src/governed_memory/data/cl100k_base.tiktoken` and its pattern/special-token metadata are vendored from tiktoken's public `cl100k_base` encoding. Copyright (c) 2022 OpenAI, Shantanu Jain. The full MIT notice is retained in [third_party/tiktoken-LICENSE](third_party/tiktoken-LICENSE). The vocabulary SHA-256 is `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`; the refresh script verifies it before writing. Runtime loading uses this local asset and does not download a tokenizer.

Graphiti source code has not been copied into this package. Its LLM extraction, entity resolution and contradiction handling are deliberately excluded from the trusted projection path. Neo4j and PostgreSQL run as separate upstream container images, whose licensing and distribution notices remain with those images.

The optional weights are downloaded from the upstream model repositories, not
copied into this package. Their model cards identify Apache-2.0 licenses:

- [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41), revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
- [ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/tree/233902d25c440f23af6f7d6e94d2946bac0bee0a), revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`.
- [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775), CPU smoke generator.
- [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/tree/989aa7980e4cf806f80c7fef2b1adb7bc71aa306), full-run generator.
- [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554), separate local answer judge.

The external retrieval experiment uses the MIT-licensed
[LongMemEval cleaned dataset](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/tree/98d7416c24c778c2fee6e6f3006e7a073259d48f)
from [LongMemEval](https://github.com/xiaowu0162/LongMemEval). The complete dataset
and model weights are not redistributed. The full answer-run outputs include
retrieved public-history excerpts and generated answers, alongside IDs, scores,
metrics and provenance. The upstream MIT notice is retained in
[third_party/LongMemEval-LICENSE](third_party/LongMemEval-LICENSE).
The synthetic evaluation corpus and application examples
are fictional; no private user documents, conversations or credentials are used.
