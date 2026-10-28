from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from app.dsh_runtime.errors import DshSessionMissingError, DshTransportError
from app.dsh_runtime.transport import HttpKernelHostTransport


def test_runtime_host_transport_ignores_process_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    class RuntimeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"runtime":null}')

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")

    async def run() -> None:
        transport = HttpKernelHostTransport(f"http://127.0.0.1:{server.server_port}")
        try:
            assert await transport.request("GET", "/v1/runtimes") == {"runtime": None}
        finally:
            await transport.close()

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_only_definitive_resume_miss_is_recoverable() -> None:
    async def run() -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "error": {"code": "kernel_request_failed", "message": 'session "dsh-lost" not found'}
            })

        transport = HttpKernelHostTransport("http://localhost")
        await transport.close()
        transport._client = httpx.AsyncClient(
            base_url="http://localhost", transport=httpx.MockTransport(respond)
        )
        try:
            with pytest.raises(DshSessionMissingError):
                await transport.request("POST", "/v1/runtimes/runtime/sessions/dsh-lost/resume")
            with pytest.raises(DshTransportError) as other:
                await transport.request("POST", "/v1/runtimes/runtime/sessions/dsh-lost/send")
            assert not isinstance(other.value, DshSessionMissingError)
        finally:
            await transport.close()

    asyncio.run(run())
