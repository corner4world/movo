import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.dsh_runtime.profile.skills.workflow import compile_workflow_body
from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.enterprise_capabilities.knowledge import document_reader
from app.enterprise_capabilities.knowledge.document_evidence import build_knowledge_document_evidence
from app.enterprise_capabilities.runtime.catalog import InternalCapabilityCatalog
from app.governance.position_policy import EffectiveEmployeePolicy


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, _fields):
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def _matching(self, query):
        return [row for row in self.rows if all(
            any(all(row.get(field) == expected for field, expected in clause.items()) for clause in value)
            if key == "$or" else row.get(key) == value
            for key, value in query.items()
        )]

    async def find_one(self, query):
        return next(iter(self._matching(query)), None)

    async def count_documents(self, query):
        return len(self._matching(query))

    def find(self, query):
        return _Cursor(sorted(self._matching(query), key=lambda row: (row["ordinal"], row["_id"])))


def _database():
    document = {
        "_id": "rule-doc", "main_id": "tenant-a", "scope": "organization",
        "deleted_at": None, "parse_status": "succeeded", "name": "审核规则",
        "checksum": "sha256-example",
    }
    chunks = [
        {
            "_id": "1", "main_id": "tenant-a", "document_id": "rule-doc",
            "chunk_stage": "raw", "ordinal": 0, "chunk_id": "r1", "text": "甲" * 1200,
            "page_no": 1, "title_path": ["付款"],
        },
        {
            "_id": "2", "main_id": "tenant-a", "document_id": "rule-doc",
            "chunk_stage": "raw", "ordinal": 1, "chunk_id": "r2", "text": "乙" * 20,
            "page_no": 2, "title_path": ["交付"],
        },
    ]
    return SimpleNamespace(
        knowledge_documents=_Collection([document]),
        knowledge_document_chunks=_Collection(chunks),
    )


def test_ordered_read_continues_inside_a_chunk(monkeypatch):
    monkeypatch.setattr(document_reader, "get_db", _database)
    monkeypatch.setattr(document_reader, "get_product_extension", lambda: SimpleNamespace(knowledge_access_policy=None))

    async def run():
        first = await document_reader.read_knowledge_document(
            tenant_id="tenant-a", user_id="u1", scope="organization",
            source_id="rule-doc", max_chars=1000,
        )
        second = await document_reader.read_knowledge_document(
            tenant_id="tenant-a", user_id="u1", scope="organization",
            source_id="rule-doc", max_chars=1000, **first["next_cursor"],
        )
        return first, second

    first, second = asyncio.run(run())
    assert first["has_more"] is True
    assert first["next_cursor"] == {"offset": 0, "char_offset": 1000}
    assert second["has_more"] is False
    assert "".join(part["text"] for page in (first, second) for part in page["segments"]) == "甲" * 1200 + "乙" * 20


def test_organization_policy_denial_blocks_read(monkeypatch):
    monkeypatch.setattr(document_reader, "get_db", _database)

    class Deny:
        async def require_view(self, **_kwargs):
            raise PermissionError("knowledge_forbidden")

    monkeypatch.setattr(document_reader, "get_product_extension", lambda: SimpleNamespace(knowledge_access_policy=Deny()))
    with pytest.raises(PermissionError, match="knowledge_forbidden"):
        asyncio.run(document_reader.read_knowledge_document(
            tenant_id="tenant-a", user_id="u1", scope="organization", source_id="rule-doc",
        ))


def test_personal_read_uses_authorized_active_document(monkeypatch):
    database = _database()
    database.knowledge_documents.rows[0].update({"scope": "personal", "resource_id": "personal-resource"})
    monkeypatch.setattr(document_reader, "get_db", lambda: database)

    class Access:
        async def require_view(self, **kwargs):
            assert kwargs["resource_id"] == "personal-resource"
            assert kwargs["user_id"] == "u1"
            return SimpleNamespace(resource={"active_document_id": "rule-doc"})

    monkeypatch.setattr(document_reader, "PersonalKnowledgeAccessService", Access)
    result = asyncio.run(document_reader.read_knowledge_document(
        tenant_id="tenant-a", user_id="u1", scope="personal",
        source_id="personal-resource", max_chars=1000,
    ))
    assert result["document_id"] == "rule-doc"
    assert result["source_id"] == "personal-resource"


def test_personal_read_checks_the_current_user_again_after_access_is_revoked(monkeypatch):
    class Deny:
        async def require_view(self, **kwargs):
            assert kwargs["user_id"] == "recipient"
            raise PermissionError("knowledge_forbidden")

    monkeypatch.setattr(document_reader, "PersonalKnowledgeAccessService", Deny)
    with pytest.raises(PermissionError, match="knowledge_forbidden"):
        asyncio.run(document_reader.read_knowledge_document(
            tenant_id="tenant-a", user_id="recipient", scope="personal",
            source_id="personal-resource",
        ))


def test_deleted_or_cross_tenant_document_cannot_be_read(monkeypatch):
    database = _database()
    monkeypatch.setattr(document_reader, "get_db", lambda: database)
    monkeypatch.setattr(document_reader, "get_product_extension", lambda: SimpleNamespace(knowledge_access_policy=None))
    database.knowledge_documents.rows[0]["deleted_at"] = "deleted"
    with pytest.raises(LookupError, match="knowledge_document_not_found"):
        asyncio.run(document_reader.read_knowledge_document(
            tenant_id="tenant-a", user_id="u1", scope="organization", source_id="rule-doc",
        ))
    database.knowledge_documents.rows[0]["deleted_at"] = None
    with pytest.raises(LookupError, match="knowledge_document_not_found"):
        asyncio.run(document_reader.read_knowledge_document(
            tenant_id="tenant-b", user_id="u1", scope="organization", source_id="rule-doc",
        ))


def test_workflow_compiles_bound_document_tool_and_alias():
    definition = next(item for item in InternalCapabilityCatalog().definitions()
                      if item.capability_ref == "knowledge.read_document@v1")
    tool = ToolProfileDefinition(
        name=definition.tool_name, version=definition.version, source_type="internal",
        capability_ref=definition.capability_ref, external_tool_id=definition.capability_ref,
        description=definition.description, input_schema=definition.input_schema,
        risk_level=definition.risk_level,
    )
    row = {
        "name": "合同预审", "config": {"workflowNodes": [{
            "id": "rules", "type": "read_material", "title": "读取审核规则",
            "description": "按规则逐条审核", "outputAlias": "审核规则",
            "businessConfig": {
                "sourceType": "knowledge_document", "knowledgeScope": "organization",
                "knowledgeSourceId": "rule-doc", "sourceRole": "review_policy",
            },
        }]},
    }
    body, refs = compile_workflow_body(row, tools=(tool,), style_refs={})
    assert refs == ("knowledge.read_document@v1",)
    assert "scope=organization" in body and "source_id=rule-doc" in body
    assert "source_role" not in body and "sourceRole" not in body
    assert "Output of this step: 审核规则" in body


def test_document_evidence_keeps_document_source_and_position():
    bundle = build_knowledge_document_evidence({
        "document_id": "rule-doc", "source_id": "rule-doc", "document_name": "审核规则",
        "checksum": "sha256-example", "segments": [{
            "text": "PAY-001：预付款不得超过30%", "chunk_id": "r1",
            "ordinal": 0, "char_offset": 0, "page_no": 1, "title_path": ["付款"],
        }],
    })
    item = bundle["results"][0]
    assert item["meta"]["document_id"] == "rule-doc"
    assert item["meta"]["provenance"] == "authorized_knowledge_document_read"
    assert item["meta"]["page_no"] == 1


def test_english_document_evidence_uses_english_fallbacks():
    bundle = build_knowledge_document_evidence({
        "segments": [{"text": "Policy text", "chunk_id": "c1"}],
    }, language="en-US")
    assert bundle["language"] == "en-US"
    assert bundle["results"][0]["title"] == "Knowledge document"
    assert bundle["results"][0]["source"] == "Internal knowledge document"


def test_document_read_uses_existing_internal_knowledge_position_permission():
    policy = EffectiveEmployeePolicy(
        tenant_id="tenant-a", user_id="u1", capabilities={"internal_knowledge": False},
    )
    assert policy.allows_internal("knowledge.read_document@v1") is False
