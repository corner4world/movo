import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from app.services.external_tools import ExternalToolService
from app.services.http_proxy_policy import should_trust_environment_proxy


def test_proxy_policy_keeps_remote_proxy_and_bypasses_loopback():
    assert should_trust_environment_proxy("https://api.example.com/lookup")
    assert not should_trust_environment_proxy("http://localhost:8765/lookup")
    assert not should_trust_environment_proxy("http://127.0.0.1:8765/lookup")
    assert not should_trust_environment_proxy("http://[::1]:8765/lookup")


def test_direct_http_tool_reaches_loopback_despite_system_proxy(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"marker": "MVO-HTTP-1028"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    try:
        result = asyncio.run(ExternalToolService()._test_http_direct({
            "method": "GET", "url": f"http://127.0.0.1:{server.server_port}/lookup",
            "query": {"marker": "MVO-HTTP-1028"},
        }))
        assert result["success"] is True
        assert result["raw"] == {"marker": "MVO-HTTP-1028"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
