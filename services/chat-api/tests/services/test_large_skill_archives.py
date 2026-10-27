from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import zipfile

import pytest

from app.services.skill_packages import validate_skill_zip
from app.services.skill_packages import archive_store
from app.api.endpoints import dsh_skill_bundles
from starlette.requests import Request


class GridFile:
    def __init__(self, content: bytes, metadata: dict):
        self.content = io.BytesIO(content)
        self.metadata = metadata

    async def read(self, size: int) -> bytes:
        return self.content.read(size)


class GridBucket:
    files: dict[str, GridFile] = {}

    def __init__(self, db, *, bucket_name: str):
        assert bucket_name == archive_store.BUCKET_NAME

    async def upload_from_stream_with_id(self, file_id, filename, source, *, metadata):
        assert filename.endswith('.zip')
        self.files[file_id] = GridFile(source.read(), metadata)

    async def open_download_stream(self, file_id):
        stored = self.files[file_id]
        return GridFile(stored.content.getvalue(), stored.metadata)

    async def delete(self, file_id):
        self.files.pop(file_id)


def _zip_with_large_resource() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('SKILL.md', '---\nname: large-skill\ndescription: Large Skill\n---\nRead references/info.txt.\n')
        archive.writestr('references/info.txt', 'resource available')
        archive.writestr('assets/payload.bin', os.urandom(21 * 1024 * 1024))
    return output.getvalue()


def test_large_skill_uses_gridfs_and_old_inline_archive_is_unchanged(monkeypatch):
    monkeypatch.setattr(archive_store, 'AsyncIOMotorGridFSBucket', GridBucket)
    GridBucket.files = {}
    content = _zip_with_large_resource()
    package = validate_skill_zip(content)
    assert len(content) > 20 * 1024 * 1024
    assert package.name == 'large-skill'
    assert any(item['path'] == 'references/info.txt' for item in package.files)
    fields = asyncio.run(archive_store.archive_fields(object(), content, main_id='tenant-a', digest=package.archive_digest))
    assert 'archive_base64' not in fields
    assert asyncio.run(archive_store.read_archive(object(), {**fields, 'main_id': 'tenant-a', 'digest': package.archive_digest})) == content
    with pytest.raises(ValueError, match='tenant mismatch'):
        asyncio.run(archive_store.read_archive(object(), {**fields, 'main_id': 'tenant-b', 'digest': package.archive_digest}))
    legacy = b'legacy archive'
    assert asyncio.run(archive_store.read_archive(object(), {
        'archive_base64': base64.b64encode(legacy).decode(),
        'digest': hashlib.sha256(legacy).hexdigest(),
    })) == legacy


def test_oversize_archive_is_rejected_before_storage():
    with pytest.raises(Exception) as raised:
        validate_skill_zip(b'x' * (100 * 1024 * 1024 + 1))
    assert raised.value.code == 'archive_too_large'


def test_archive_near_100_mib_limit_is_accepted():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('SKILL.md', '---\nname: near-limit\ndescription: Near limit\n---\nRead the resource.\n')
        archive.writestr('assets/data.bin', b'x' * (99 * 1024 * 1024))
    content = output.getvalue()
    assert 99 * 1024 * 1024 < len(content) <= archive_store.MAX_ARCHIVE_BYTES
    assert validate_skill_zip(content).name == 'near-limit'


def test_internal_bundle_delivery_checks_host_token_and_digest(monkeypatch):
    from fastapi import HTTPException

    content = b'archived skill resource'
    digest = hashlib.sha256(content).hexdigest()
    file_id = 'a' * 32

    class Files:
        async def find_one(self, query):
            assert query == {'_id': file_id}
            return {'length': len(content), 'metadata': {'digest': digest, 'main_id': 'tenant-a'}}

    class Database:
        def __getitem__(self, collection):
            assert collection == 'skill_archives.files'
            return Files()

    class Bucket(GridBucket):
        files = {file_id: GridFile(content, {'digest': digest, 'main_id': 'tenant-a'})}

    monkeypatch.setattr(dsh_skill_bundles, 'get_db', Database)
    monkeypatch.setattr(dsh_skill_bundles, 'AsyncIOMotorGridFSBucket', Bucket)
    monkeypatch.setattr(dsh_skill_bundles, 'get_settings', lambda: type('Settings', (), {
        'DSH_RUNTIME_HOST_TOKEN': 'test-secret',
        'DSH_MODEL_GATEWAY_SIGNING_SECRET': '',
        'ASKAI_ADMIN_JWT_SECRET': '',
    })())
    request = Request({'type': 'http', 'client': ('127.0.0.1', 5000), 'method': 'GET', 'path': '/'})
    with pytest.raises(HTTPException) as denied:
        asyncio.run(dsh_skill_bundles.download(file_id, request, digest, 'Bearer wrong'))
    assert denied.value.status_code == 401
    with pytest.raises(HTTPException) as wrong_digest:
        asyncio.run(dsh_skill_bundles.download(file_id, request, '0' * 64, 'Bearer test-secret'))
    assert wrong_digest.value.status_code == 404

    async def read_body():
        response = await dsh_skill_bundles.download(file_id, request, digest, 'Bearer test-secret')
        return b''.join([part async for part in response.body_iterator])

    assert asyncio.run(read_body()) == content
