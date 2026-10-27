from __future__ import annotations

import unittest
from dataclasses import dataclass, replace

from app.api.setup_status_messages import localize_setup_services


@dataclass
class ServiceStatus:
    label: str
    message: str
    ok: bool

    def model_copy(self):
        return replace(self)


class SetupStatusMessagesTests(unittest.TestCase):
    def test_english_status_does_not_mutate_probe(self) -> None:
        original = [ServiceStatus("持久化存储", "已就绪", True)]
        english = localize_setup_services(original, "en-US")
        self.assertEqual((english[0].label, english[0].message), ("Persistent Storage", "Ready"))
        self.assertEqual((original[0].label, original[0].message), ("持久化存储", "已就绪"))
        self.assertIs(localize_setup_services(original, "zh-CN"), original)


if __name__ == "__main__":
    unittest.main()
