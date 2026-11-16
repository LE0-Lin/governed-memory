import argparse
import asyncio
import json
import sys
from pathlib import Path

from governed_memory.db import create_db, initialize, require_current_schema
from governed_memory.identity import bootstrap, create_project, issue_credential, revoke_access
from governed_memory.ingest import import_file
from governed_memory.ledger import Ledger
from governed_memory.operators import COMMANDS, add_commands, run_command
from governed_memory.settings import Settings


def output(value):
    print(json.dumps(value, default=str, ensure_ascii=False, indent=2))


def parser():
    root = argparse.ArgumentParser(description="Governed temporal memory operator CLI")
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser(
        "init", help="initialize an empty ledger and issue its admin credential"
    )
    p.add_argument("--project", required=True)
    p.add_argument("--principal", default="operator")
    p = commands.add_parser(
        "upgrade", help="upgrade tables and reconcile revoked support dependencies"
    )
    p.add_argument("--project", required=True)
    p = commands.add_parser("credential")
    p.add_argument("--project", required=True)
    p.add_argument("--principal", required=True)
    p.add_argument("--role", choices=["reader", "agent", "approver", "admin"], required=True)
    p = commands.add_parser("create-project")
    p.add_argument("--from-project", required=True)
    p.add_argument("--project", required=True)
    p = commands.add_parser("revoke-access")
    p.add_argument("--project", required=True)
    p.add_argument("--principal", required=True)
    p = commands.add_parser("ingest")
    p.add_argument("--project", required=True)
    p.add_argument("file")
    for name in ("explain", "preview", "approve", "reject", "revoke"):
        p = commands.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("id")
        if name not in {"explain", "preview"}:
            p.add_argument("--expected-revision", type=int, required=True)
            p.add_argument("--reason", required=True)
        if name == "approve":
            p.add_argument("--protected", action="store_true")
            p.add_argument("--expected-head", type=int, required=True)
    p = commands.add_parser("withdraw-source")
    p.add_argument("--project", required=True)
    p.add_argument("id")
    p = commands.add_parser(
        "approve-support", help="approve a second source for an existing assertion"
    )
    p.add_argument("--project", required=True)
    p.add_argument("id", help="staged evidence candidate ID")
    p.add_argument("--target", required=True)
    p.add_argument("--expected-revision", type=int, required=True)
    p.add_argument("--expected-target-revision", type=int, required=True)
    p.add_argument("--expected-head", type=int, required=True)
    p.add_argument("--reason", required=True)
    for name in ("search", "answer"):
        p = commands.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("query")
        p.add_argument("--valid-at")
        p.add_argument("--known-at")
        p.add_argument("--token-budget", type=int, default=2048)
        p.add_argument("--k", type=int, default=5)
    p = commands.add_parser("project", help="retry the durable projection queue")
    p.add_argument("--project", required=True)
    p.add_argument(
        "--rebuild", action="store_true", help="requeue every stored historical snapshot"
    )
    commands.add_parser("serve", help="run the agent-only stdio MCP tools")
    add_commands(commands)
    return root


async def graph_operation(settings, ledger, args):
    graph = settings.graph()
    try:
        if args.command == "project":
            from sqlalchemy.orm import Session

            with Session(ledger.engine) as session:
                ledger.authenticate(session, settings.token, args.project, ("admin",))
            if graph is None:
                raise ValueError("MEMORY_NEO4J_URI is required for graph projection")
            from governed_memory.graph_adapter import project_pending

            await graph.initialize()
            if args.rebuild:
                ledger.requeue(settings.token, args.project)
            result = await project_pending(ledger, graph, project=args.project)
            output(result)
            return 1 if result["failed"] else 0
        retriever = settings.retriever(ledger, graph)
        operation = retriever.search
        if args.command == "answer":
            from governed_memory.answering import AnswerService

            generator = settings.generator()
            if generator is None:
                raise ValueError("set MEMORY_GENERATION_PROFILE to enable answers")
            operation = AnswerService(
                retriever, generator, answer_format=settings.answer_format
            ).answer
        result = await operation(
            settings.token,
            args.project,
            args.query,
            valid_at=args.valid_at,
            known_at=args.known_at,
            token_budget=args.token_budget,
            k=args.k,
        )
        output(result)
        return 0
    finally:
        if graph:
            await graph.close()


def main():
    # Native Windows pipes may use a legacy code page; command JSON is always UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    settings = Settings.from_env()
    if args.command == "serve":
        from governed_memory.mcp_server import run

        run()
        return
    if settings.database_url == "sqlite:///.local/memory.db":
        Path(".local").mkdir(exist_ok=True)
    engine = create_db(settings.database_url)
    if args.command not in {"init", "upgrade"}:
        require_current_schema(engine)
    ledger = Ledger(
        engine,
        policy=settings.policy(),
        authorizer=None if args.command == "fga-setup" else settings.authorizer(),
    )
    try:
        if args.command in COMMANDS:
            output(run_command(args, settings, ledger))
        elif args.command == "init":
            initialize(engine)
            output(
                {
                    "admin_token": bootstrap(engine, args.principal, args.project),
                    "store_safely": "Keep this credential out of agent configuration and Git.",
                }
            )
        elif args.command == "credential":
            output(
                {
                    "token": issue_credential(
                        engine,
                        settings.token,
                        args.principal,
                        args.project,
                        args.role,
                        authorizer=ledger.authorizer,
                    )
                }
            )
        elif args.command == "upgrade":
            from sqlalchemy.orm import Session

            from governed_memory.identity import authenticate

            with Session(engine) as session:
                authenticate(
                    session, settings.token, args.project, ("admin",), authorizer=ledger.authorizer
                )
            initialize(engine)
            repaired = ledger.reconcile_support_dependencies(settings.token, args.project)
            output({"schema": "current", "project": args.project, "dependency_repairs": repaired})
        elif args.command == "approve-support":
            output(
                ledger.approve_support(
                    settings.token,
                    args.project,
                    args.id,
                    args.target,
                    expected_revision=args.expected_revision,
                    expected_target_revision=args.expected_target_revision,
                    expected_head=args.expected_head,
                    reason=args.reason,
                )
            )
        elif args.command == "create-project":
            create_project(
                engine,
                settings.token,
                args.from_project,
                args.project,
                authorizer=ledger.authorizer,
            )
            output({"created": args.project})
        elif args.command == "revoke-access":
            revoke_access(
                engine, settings.token, args.project, args.principal, authorizer=ledger.authorizer
            )
            output({"revoked": args.principal, "project": args.project})
        elif args.command == "ingest":
            output(import_file(ledger, settings.token, args.project, args.file))
        elif args.command == "explain":
            output(ledger.explain(settings.token, args.project, args.id))
        elif args.command == "preview":
            output(ledger.preview(settings.token, args.project, args.id))
        elif args.command in {"approve", "reject", "revoke"}:
            output(
                ledger.decide(
                    settings.token,
                    args.project,
                    args.id,
                    args.command,
                    args.expected_revision,
                    reason=args.reason,
                    protected=getattr(args, "protected", False),
                    expected_head=getattr(args, "expected_head", None),
                )
            )
        elif args.command == "withdraw-source":
            ledger.withdraw_source(settings.token, args.project, args.id)
            output({"withdrawn": args.id})
        else:
            raise SystemExit(asyncio.run(graph_operation(settings, ledger, args)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
