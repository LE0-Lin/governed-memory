import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    token: str
    neo4j_uri: str | None
    neo4j_user: str
    neo4j_password: str

    @classmethod
    def from_env(cls):
        return cls(
            os.environ.get("MEMORY_DATABASE_URL", "sqlite:///.local/memory.db"),
            os.environ.get("MEMORY_TOKEN", ""),
            os.environ.get("MEMORY_NEO4J_URI"),
            os.environ.get("MEMORY_NEO4J_USER", "neo4j"),
            os.environ.get("MEMORY_NEO4J_PASSWORD", ""),
        )

    def embedder(self):
        model = os.environ.get("MEMORY_EMBEDDING_MODEL")
        if os.environ.get("MEMORY_LOCAL_EMBEDDING") == "1":
            if model:
                raise ValueError("select either local or external embeddings")
            from governed_memory.local_models import MiniLMEmbedder

            return MiniLMEmbedder(os.environ.get("MEMORY_MODEL_CACHE"))
        if model:
            from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

            key = os.environ.get("MEMORY_EMBEDDING_API_KEY")
            if not key:
                raise ValueError(
                    "MEMORY_EMBEDDING_API_KEY required for an external embedding model"
                )
            return OpenAIEmbedder(
                OpenAIEmbedderConfig(
                    embedding_model=model,
                    api_key=key,
                    base_url=os.environ.get("MEMORY_EMBEDDING_BASE_URL"),
                    embedding_dim=1024,
                )
            )
        from governed_memory.embedding import HashEmbedder

        return HashEmbedder()

    def graph(self):
        if not self.neo4j_uri:
            return None
        from governed_memory.graph_adapter import GraphProjection

        embedder = self.embedder()
        return GraphProjection(self.neo4j_uri, self.neo4j_user, self.neo4j_password, embedder)

    def retriever(self, ledger, graph=None):
        from governed_memory.retrieval import Retriever

        relevance = os.environ.get("MEMORY_RELEVANCE_FILTER", "1")
        if relevance not in {"0", "1"}:
            raise ValueError("MEMORY_RELEVANCE_FILTER must be 0 or 1")
        try:
            capacity = int(os.environ.get("MEMORY_DOCUMENT_CACHE_SIZE", "2048"))
        except ValueError:
            raise ValueError("MEMORY_DOCUMENT_CACHE_SIZE must be 0..10000") from None
        if not 0 <= capacity <= 10000:
            raise ValueError("MEMORY_DOCUMENT_CACHE_SIZE must be 0..10000")
        reranker = None
        if os.environ.get("MEMORY_LOCAL_RERANKER") == "1":
            from governed_memory.local_models import MiniLMReranker

            reranker = MiniLMReranker(os.environ.get("MEMORY_MODEL_CACHE"))
        embedder = graph.embedder if graph else self.embedder()
        cutoff = None
        if reranker and relevance == "1":
            from governed_memory.relevance import calibrated_cutoff

            cutoff = calibrated_cutoff(reranker)
        cache = None
        from governed_memory.embedding import HashEmbedder

        if capacity and not isinstance(embedder, HashEmbedder):
            from governed_memory.embedding_cache import DocumentEmbeddingCache

            cache = DocumentEmbeddingCache(capacity)
        return Retriever(
            ledger,
            graph,
            embedder=embedder,
            reranker=reranker,
            ranking_backend=os.environ.get("MEMORY_RANKING_BACKEND", "auto"),
            min_relevance_score=cutoff,
            document_cache=cache,
        )

    def policy(self):
        from governed_memory.policy import BuiltinPolicy, OpaPolicy

        url = os.environ.get("MEMORY_OPA_URL")
        return OpaPolicy(url) if url else BuiltinPolicy()

    def authorizer(self):
        names = ("MEMORY_FGA_URL", "MEMORY_FGA_STORE_ID", "MEMORY_FGA_MODEL_ID")
        values = [os.environ.get(name) for name in names]
        key = os.environ.get("MEMORY_FGA_API_KEY")
        if not any(values) and not key:
            return None
        if not all(values):
            raise ValueError("OpenFGA requires URL, store ID and pinned model ID together")
        from governed_memory.authorization import OpenFgaAuthorizer

        return OpenFgaAuthorizer(*values, api_key=key)

    def generator(self):
        profile = os.environ.get("MEMORY_GENERATION_PROFILE")
        if not profile:
            return None
        from governed_memory.generation import TransformersGenerator

        return TransformersGenerator(
            profile,
            os.environ.get("MEMORY_GENERATION_CACHE"),
            os.environ.get("MEMORY_GENERATION_DEVICE", "cpu"),
        )
