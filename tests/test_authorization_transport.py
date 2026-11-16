import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from sqlalchemy import event

from governed_memory import authorization, mcp_server
from governed_memory.authorization import OpenFgaAuthorizer
from governed_memory.db import create_db, initialize
from governed_memory.errors import Denied
from governed_memory.identity import Identity, bootstrap
from governed_memory.ledger import Ledger
from governed_memory.settings import Settings


def test_keepalive_reuses_transport_but_never_a_decision(monkeypatch):
    state = {"allowed": True, "status": 200}
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.client_address, payload))
            body = json.dumps({"allowed": state["allowed"]}).encode()
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connections, responses = [], []
    original = authorization.connection

    def connection(*args, **kwargs):
        client = original(*args, **kwargs)
        connections.append(client)
        client.event_hooks["response"].append(
            lambda response: responses.append(response.headers.get("connection", "").lower())
        )
        return client

    monkeypatch.setattr(authorization, "connection", connection)
    authorizer = OpenFgaAuthorizer(f"http://127.0.0.1:{server.server_port}", "0" * 26, "1" * 26)
    actor = Identity("agent", "demo", "agent")
    try:
        authorizer.check(actor, "writer")
        state["allowed"] = False
        with pytest.raises(Denied, match="permission denied"):
            authorizer.check(actor, "writer")
        state.update(allowed=True, status=503)
        with pytest.raises(Denied, match="unavailable"):
            authorizer.check(actor, "writer")
        state["status"] = 200
        authorizer.check(actor, "writer")
        assert len(requests) == 4
        assert len(connections) == 1
        # A local network intermediary may explicitly close every response.
        # Respect that header; otherwise HTTP/1.1 must reuse the TCP connection.
        if "close" not in responses:
            assert len({address for address, _ in requests}) == 1
        assert all(payload["consistency"] == "HIGHER_CONSISTENCY" for _, payload in requests)
    finally:
        authorizer.close()
        authorizer.close()
        assert authorizer.client.is_closed
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("external", [False, True], ids=["owned", "external"])
async def test_mcp_shutdown_closes_only_its_owned_resources(tmp_path, monkeypatch, external):
    url = "sqlite:///" + (tmp_path / "memory.db").as_posix()
    engine = create_db(url)
    initialize(engine)
    token = bootstrap(engine, "operator", "demo")
    authorizer = OpenFgaAuthorizer("http://localhost:8080", "0" * 26, "1" * 26)
    disposed = []
    event.listen(engine, "engine_disposed", lambda _: disposed.append(True))
    monkeypatch.setattr(mcp_server, "create_db", lambda _: engine)
    monkeypatch.setattr(Settings, "authorizer", lambda _: authorizer)
    ledger = Ledger(engine, authorizer=authorizer) if external else None
    try:
        server = mcp_server.build_server(Settings(url, token, None, "", ""), ledger=ledger)
        async with server.settings.lifespan(server):
            assert not authorizer.client.is_closed and not disposed
        assert authorizer.client.is_closed is not external
        assert bool(disposed) is not external
    finally:
        authorizer.close()
        engine.dispose()


def test_mcp_failed_configuration_releases_its_client_and_engine(tmp_path, monkeypatch):
    engine = create_db("sqlite:///" + (tmp_path / "memory.db").as_posix())
    initialize(engine)
    token = bootstrap(engine, "operator", "demo")
    authorizer = OpenFgaAuthorizer("http://localhost:8080", "0" * 26, "1" * 26)
    disposed = []
    event.listen(engine, "engine_disposed", lambda _: disposed.append(True))
    monkeypatch.setattr(mcp_server, "create_db", lambda _: engine)
    monkeypatch.setattr(Settings, "authorizer", lambda _: authorizer)
    monkeypatch.setenv("MEMORY_DOCUMENT_CACHE_SIZE", "invalid")
    with pytest.raises(ValueError, match="MEMORY_DOCUMENT_CACHE_SIZE"):
        mcp_server.build_server(Settings("unused", token, None, "", ""))
    assert authorizer.client.is_closed and disposed
