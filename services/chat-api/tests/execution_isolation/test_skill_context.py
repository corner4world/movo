from types import SimpleNamespace

import pytest

from app.execution_isolation.skill_context import invoked_skill_source_id


def test_runtime_skill_name_maps_only_to_published_source_id():
    profile = SimpleNamespace(skills=(SimpleNamespace(name="ppt-master", source_id="skill-1"),))
    assert invoked_skill_source_id(profile, "ppt-master") == "skill-1"
    with pytest.raises(ValueError, match="absent from the authorized"):
        invoked_skill_source_id(profile, "other-skill")
