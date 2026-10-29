import io
import json
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException

from app.services import skill_package_proxy


def test_dependency_status_uses_tenant_scoped_service_request(monkeypatch):
    monkeypatch.setattr(skill_package_proxy.settings, "backend_base_url", "http://chat-api:8000")
    monkeypatch.setattr(skill_package_proxy.settings, "backend_service_token", "service-token")

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://chat-api:8000/api/organization-skills/skill%2Fone/dependency-status?mainId=tenant-a"
        assert request.get_header("X-movo-service-token") == "service-token"
        assert timeout == 10
        return io.BytesIO(json.dumps({"data": {"status": "ready"}}).encode())

    monkeypatch.setattr(skill_package_proxy.urllib.request, "urlopen", fake_urlopen)
    assert skill_package_proxy.organization_skill_dependency_status(
        main_id="tenant-a", skill_id="skill/one",
    ) == {"status": "ready"}


def test_dependency_status_preserves_backend_denial(monkeypatch):
    def denied(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", {}, io.BytesIO(b""))

    monkeypatch.setattr(skill_package_proxy.urllib.request, "urlopen", denied)
    with pytest.raises(HTTPException) as error:
        skill_package_proxy.organization_skill_dependency_status(main_id="tenant-a", skill_id="missing")
    assert error.value.status_code == 404
