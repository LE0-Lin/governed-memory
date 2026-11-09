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

    def graph(self):
        if not self.neo4j_uri:
            return None
        from governed_memory.graph_adapter import GraphProjection

        embedder = None
        model = os.environ.get("MEMORY_EMBEDDING_MODEL")
        if model:
            from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

            key = os.environ.get("MEMORY_EMBEDDING_API_KEY")
            if not key:
                raise ValueError(
                    "MEMORY_EMBEDDING_API_KEY required for an external embedding model"
                )
            embedder = OpenAIEmbedder(
                OpenAIEmbedderConfig(
                    embedding_model=model,
                    api_key=key,
                    base_url=os.environ.get("MEMORY_EMBEDDING_BASE_URL"),
                    embedding_dim=1024,
                )
            )
        return GraphProjection(self.neo4j_uri, self.neo4j_user, self.neo4j_password, embedder)
