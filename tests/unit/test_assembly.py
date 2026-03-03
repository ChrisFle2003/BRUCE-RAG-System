import unittest

from common.assembly import assemble
try:
    from embedding.service import DeterministicEmbedder
except ModuleNotFoundError:  # numpy may not be installed before `make setup`
    DeterministicEmbedder = None


class AssemblyRulesTest(unittest.TestCase):
    def test_low_confidence_filtered_from_main_text(self):
        rows = [
            {
                "route_id": 3,
                "route_name": "BRUCE",
                "source_seite_ids": [11],
                "bausteine": [
                    {"type": "fact", "content": "High fact", "confidence": 0.9},
                    {"type": "fact", "content": "Low fact", "confidence": 0.2},
                ],
            }
        ]

        result = assemble(rows)
        self.assertIn("High fact", result["answer_text"])
        self.assertNotIn("Low fact", result["answer_text"])
        self.assertEqual(len(result["low_confidence_sections"]), 1)

    def test_code_is_never_filtered(self):
        rows = [
            {
                "route_id": 3,
                "route_name": "BRUCE",
                "source_seite_ids": [12],
                "bausteine": [
                    {
                        "type": "code",
                        "content": "def x(): return 1",
                        "confidence": 0.1,
                    }
                ],
            }
        ]

        result = assemble(rows)
        self.assertIn("def x(): return 1", result["answer_text"])


class MappingTest(unittest.TestCase):
    def test_dim_to_zone_boundaries(self):
        if DeterministicEmbedder is None:
            self.skipTest("embedding dependencies not installed")
        self.assertEqual(DeterministicEmbedder.dim_to_zone(-32768, 27), 0)
        self.assertEqual(DeterministicEmbedder.dim_to_zone(32767, 27), 26)


if __name__ == "__main__":
    unittest.main()
