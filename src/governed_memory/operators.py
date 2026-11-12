"""Optional ingestion, semantic review and external governance operator commands."""

import asyncio
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.identity import authenticate
from governed_memory.models import Grant

COMMANDS = {
    "ingest-document",
    "review",
    "resolve-entity",
    "derive",
    "lineage",
    "fga-setup",
    "fga-grant",
}


def add_commands(commands):
    for name in sorted(COMMANDS):
        p = commands.add_parser(name)
        p.add_argument("--project", required=True)
        if name == "ingest-document":
            p.add_argument("file")
            p.add_argument("--valid-from", required=True)
            p.add_argument("--valid-until")
            p.add_argument("--locator")
        elif name in {"review", "resolve-entity"}:
            p.add_argument("id")
            if name == "resolve-entity":
                p.add_argument("--target", required=True, help="approved canonical entity snapshot")
                p.add_argument("--expected-revision", type=int, required=True)
                p.add_argument("--reason", required=True)
        elif name == "derive":
            for field in ("subject", "predicate", "value", "valid-from"):
                p.add_argument(f"--{field}", required=True)
            p.add_argument("--valid-until")
            p.add_argument("--parent", action="append", required=True, help="approved snapshot ID")
            p.add_argument("--locator", required=True)
        elif name == "lineage":
            p.add_argument("--limit", type=int, default=100)
        elif name == "fga-grant":
            p.add_argument("--principal", required=True)
            p.add_argument(
                "--role", choices=["reader", "agent", "approver", "admin"], required=True
            )
            p.add_argument("--remove", action="store_true")


def run_command(args, settings, ledger):
    token, project = settings.token, args.project
    if args.command == "derive":
        return ledger.propose(
            token,
            project,
            subject=args.subject,
            predicate=args.predicate,
            value=args.value,
            valid_from=args.valid_from,
            valid_until=args.valid_until,
            locator=args.locator,
            parent_ids=args.parent,
        )
    if args.command == "resolve-entity":
        return ledger.resolve_entity(
            token,
            project,
            args.id,
            args.target,
            expected_revision=args.expected_revision,
            reason=args.reason,
        )
    if args.command in {"ingest-document", "review"}:
        # Check before constructing the model adapters (which may load or download weights).
        roles = (
            ("agent", "approver", "admin")
            if args.command == "ingest-document"
            else ("admin", "approver")
        )
        with Session(ledger.engine) as session:
            ledger.authenticate(session, token, project, roles)
        embedder = settings.embedder()
        from governed_memory.embedding import HashEmbedder

        if isinstance(embedder, HashEmbedder):
            raise ValueError("set MEMORY_LOCAL_EMBEDDING=1 or configure semantic embeddings")
        if args.command == "review":
            from governed_memory.semantic_review import NliDetector, SemanticReview

            return asyncio.run(
                SemanticReview(
                    ledger, embedder, NliDetector(os.environ.get("MEMORY_MODEL_CACHE"))
                ).inspect(token, project, args.id)
            )
        from governed_memory.semantic_ingest import FactExtractor, import_document

        generator = settings.generator()
        if generator is None:
            raise ValueError("set MEMORY_GENERATION_PROFILE to extract document facts")
        path = Path(args.file)
        return asyncio.run(
            import_document(
                ledger,
                token,
                project,
                path.read_text(encoding="utf-8"),
                args.locator or path.name,
                args.valid_from,
                embedder,
                FactExtractor(generator),
                valid_until=args.valid_until,
                backend=os.environ.get("MEMORY_RANKING_BACKEND", "auto"),
            )
        )
    if args.command == "fga-setup":
        from governed_memory.authorization import provision

        if os.environ.get("MEMORY_FGA_STORE_ID") or os.environ.get("MEMORY_FGA_MODEL_ID"):
            raise ValueError("fga-setup is only for a new store; existing stores use fga-grant")
        endpoint = os.environ.get("MEMORY_FGA_URL")
        if not endpoint:
            raise ValueError("MEMORY_FGA_URL is required")
        with Session(ledger.engine) as session:
            authenticate(session, token, project, ("admin",))
            grants = list(
                session.execute(
                    select(Grant.principal_id, Grant.role).where(Grant.project == project)
                )
            )
        authorizer = provision(
            endpoint, project, grants, api_key=os.environ.get("MEMORY_FGA_API_KEY")
        )
        return {
            "MEMORY_FGA_STORE_ID": authorizer.store_id,
            "MEMORY_FGA_MODEL_ID": authorizer.model_id,
        }
    with Session(ledger.engine) as session:
        ledger.authenticate(session, token, project, ("admin",))
    if args.command == "fga-grant":
        if ledger.authorizer is None:
            raise ValueError("configure OpenFGA before editing relationships")
        ledger.authorizer.grant(args.principal, project, args.role, remove=args.remove)
        return {"principal": args.principal, "role": args.role, "removed": args.remove}
    if args.command == "lineage":
        from governed_memory.lineage import drain

        endpoint = os.environ.get("MEMORY_LINEAGE_ENDPOINT")
        if not endpoint:
            raise ValueError("MEMORY_LINEAGE_ENDPOINT must be a complete collector events URL")
        return drain(
            ledger.engine,
            project,
            endpoint,
            api_key=os.environ.get("MEMORY_LINEAGE_API_KEY"),
            limit=args.limit,
        )
    raise ValueError("unknown operator command")
