"""
Tests for platform-specific compatibility in dt_shell.

This module tests that platform-specific functions work correctly
across different operating systems (Linux, macOS, Windows).
"""
import sys
import unittest
from unittest.mock import patch


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection functions."""

    def test_on_linux_detection(self):
        """Test that on_linux() correctly detects Linux platforms."""
        from dt_shell.checks.environment import on_linux

        # Mock different platforms
        with patch.object(sys, 'platform', 'linux'):
            self.assertTrue(on_linux())

        with patch.object(sys, 'platform', 'linux2'):
            self.assertTrue(on_linux())

        with patch.object(sys, 'platform', 'darwin'):
            self.assertFalse(on_linux())

        with patch.object(sys, 'platform', 'win32'):
            self.assertFalse(on_linux())

    def test_on_macos_detection(self):
        """Test that on_macos() correctly detects macOS platforms."""
        from dt_shell.checks.environment import on_macos

        # Mock different platforms
        with patch.object(sys, 'platform', 'darwin'):
            self.assertTrue(on_macos())

        with patch.object(sys, 'platform', 'linux'):
            self.assertFalse(on_macos())

        with patch.object(sys, 'platform', 'win32'):
            self.assertFalse(on_macos())

    def test_platform_detection_mutually_exclusive(self):
        """Test that on_linux() and on_macos() are mutually exclusive."""
        from dt_shell.checks.environment import on_linux, on_macos

        # On any platform, at most one should be true
        self.assertFalse(on_linux() and on_macos())


class TestDockerEnvironmentChecks(unittest.TestCase):
    """Test docker environment checks are platform-specific."""

    def test_docker_group_check_only_on_linux(self):
        """Test that docker group check only runs on Linux, not macOS."""
        # This is more of a documentation test - the actual behavior
        # is that check_user_in_docker_group() should only be called
        # on Linux systems in check_docker_environment()

        # On macOS, Docker Desktop manages permissions differently
        # and doesn't use Unix groups the same way Linux does
        pass


if __name__ == '__main__':
    unittest.main()
