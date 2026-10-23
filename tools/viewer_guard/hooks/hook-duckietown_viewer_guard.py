"""Cython imports are opaque to PyInstaller's Python bytecode analysis."""

import sys

hiddenimports = [
    "argparse", "base64", "binascii", "datetime", "hashlib", "http.client",
    "json", "math", "os", "pathlib", "re", "secrets", "stat", "sys",
    "tempfile", "time", "urllib.parse", "zipfile", "plistlib", "socket",
    "subprocess", "uuid", "xml.parsers.expat",
    "cryptography.exceptions", "cryptography.hazmat.primitives.asymmetric.ed25519",
    "duckietown_viewer_guard_trust", "duckietown_viewer_guard_device",
]
if sys.platform == "win32":
    hiddenimports.append("winreg")
