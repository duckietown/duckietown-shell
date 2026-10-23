import importlib.util
import unittest
from unittest.mock import patch

from dt_shell_tests import test_engine as source


AVAILABLE = importlib.util.find_spec("duckietown_engine_guard") is not None
if AVAILABLE:
    import duckietown_engine_guard


@unittest.skipUnless(AVAILABLE, "Install the standalone compiled Engine guard to run these checks.")
class NativeEngineTests(source.EngineTests):
    def setUp(self):
        super().setUp()
        mock = patch.object(source, "runtime", duckietown_engine_guard)
        mock.start()
        self.addCleanup(mock.stop)

    def test_developer_authorization_starts_monitor_before_engine_initialization(self):
        self.skipTest("Pinned native startup/lifetime is exercised with ephemeral compiled trust by tools/engine_guard/test_native.py.")
