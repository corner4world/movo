"""Narrow control-plane API for per-job containers."""

from __future__ import annotations

import hmac
import os
import threading
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .docker_engine import DockerEngine
from .jobs import ScriptJobs
from .plugin_runtimes import PluginRuntimes


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_jobs: ScriptJobs | None = None
_plugins: PluginRuntimes | None = None
_jobs_lock = threading.Lock()


def jobs() -> ScriptJobs:
    global _jobs
    with _jobs_lock:
        if _jobs is None:
            _jobs = ScriptJobs(DockerEngine())
    return _jobs


def plugins() -> PluginRuntimes:
    global _plugins
    with _jobs_lock:
        if _plugins is None:
            _plugins = PluginRuntimes(DockerEngine())
    return _plugins


class ExecuteScriptRequest(BaseModel):
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class CreatePluginRuntimeRequest(BaseModel):
    isolation_key: str = Field(min_length=1, max_length=512)


class UpdateSettingsRequest(BaseModel):
    max_pending: int = Field(ge=0, le=100)


def _authorize(authorization: str | None) -> None:
    token = os.environ["MOVO_SANDBOX_MANAGER_TOKEN"]
    supplied = (authorization or "").removeprefix("Bearer ")
    if not token or not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        DockerEngine().request("GET", "/_ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Docker Engine unavailable") from exc
    return {"ok": True, **jobs().status(), **plugins().status()}


@app.post("/v1/script-jobs")
def run_script(payload: ExecuteScriptRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return jobs().execute(payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.put("/v1/settings")
def update_settings(payload: UpdateSettingsRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return jobs().set_max_pending(payload.max_pending)


@app.post("/v1/plugin-runtimes")
def create_plugin_runtime(payload: CreatePluginRuntimeRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return plugins().create(payload.isolation_key)


@app.delete("/v1/plugin-runtimes/{lease_id}")
def dispose_plugin_runtime(lease_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    plugins().dispose(lease_id)
    return {"disposed": True}
