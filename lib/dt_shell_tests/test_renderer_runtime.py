from importlib.machinery import EXTENSION_SUFFIXES
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from dt_shell import renderer


@unittest.skipUnless(
    renderer.__file__.endswith(tuple(EXTENSION_SUFFIXES)),
    "Requires the installed signed native renderer component",
)
class NativeRendererTrustTests(unittest.TestCase):
    def test_renderer_is_in_the_signed_mandatory_native_inventory(self):
        root = Path(renderer.__file__).resolve().parents[1]
        manifest = json.loads((root / "duckietown_shell.integrity.json").read_text())
        self.assertEqual(
            Path(renderer.__file__).relative_to(root).as_posix(),
            manifest["native_modules"]["dt_shell.renderer"],
        )
        self.assertIn("dt_shell_device", manifest["native_modules"])
        self.assertFalse((root / "dt_shell/renderer.py").exists())

    def test_runtime_environment_cannot_replace_renderer_trust(self):
        expected = renderer._trust()
        with patch.dict(
            os.environ,
            {
                "DTM_RELEASE_PUBLIC_KEY": "0" * 64,
                "DTM_RENDERER_PUBLIC_KEYS": '{"https://attacker.example":"'
                + "0" * 64
                + '"}',
            },
        ):
            self.assertEqual(expected, renderer._trust())
        self.assertEqual(64, len(expected[0]))
        self.assertEqual(
            {"https://hub.duckietown.com", "https://staging-hub.duckietown.com"},
            set(expected[1]),
        )
        self.assertEqual(3, len({expected[0], *expected[1].values()}))

    def test_changing_a_returned_public_map_does_not_change_native_pins(self):
        expected = renderer._trust()
        key, issuers = renderer._trust()
        issuers["https://hub.duckietown.com"] = "0" * 64
        self.assertEqual(expected, renderer._trust())


if __name__ == "__main__":
    unittest.main()
