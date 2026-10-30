import io
import hashlib
import zipfile
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from app.execution_isolation.audit_reader import extract_text, open_call_file
from app.execution_isolation import audit_reader


def test_extracts_selected_entry_only() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("audit/call-1/stdout.log", "completed")
    with zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
        assert extract_text(archive, "audit/call-1/stdout.log") == "completed"
        with pytest.raises(HTTPException) as error:
            extract_text(archive, "audit/call-2/stdout.log")
    assert error.value.status_code == 404


@pytest.mark.parametrize("path,digest", [
    ("../secrets.txt", "0" * 64),
    ("/etc/passwd", "0" * 64),
    ("valid.txt", "invalid"),
])
def test_rejects_invalid_audit_file_reference(path: str, digest: str) -> None:
    with pytest.raises(HTTPException) as error:
        with open_call_file("unused", "call", path, digest):
            pass
    assert error.value.status_code == 404


def test_reads_only_indexed_call_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"intermediate output"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("audit/call1/files/work/output.txt", content)
    @contextmanager
    def archive_for_test(_path: str):
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            yield archive
    monkeypatch.setattr(audit_reader, "open_audit_archive", archive_for_test)
    digest = hashlib.sha256(content).hexdigest()
    with open_call_file("task.zip", "call1", "work/output.txt", digest) as (chunks, size):
        assert size == len(content)
        assert b"".join(chunks) == content
