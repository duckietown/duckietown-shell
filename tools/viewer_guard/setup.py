"""Build the standalone native guard from the same verifier that DTS uses.

Run from the shell repository root, using the release build environment.
"""

import json
from pathlib import Path
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_support import viewer_public_keys, viewer_release_public_key


include = ROOT / "build" / "viewer-guard-include"
include.mkdir(parents=True, exist_ok=True)
(include / "viewer_trust.h").write_text(
    f'static const char DTV_RELEASE_PUBLIC_KEY[] = "{viewer_release_public_key()}";\n'
    f"static const char DTV_AUTH_PUBLIC_KEYS[] = {json.dumps(viewer_public_keys())};\n",
    encoding="ascii",
)


class NoPythonFallback(build_py):
    def find_package_modules(self, package, package_dir):
        return []


setup(
    name="duckietown-viewer-guard",
    version="1.0.0",
    description="Native, scoped Duckietown Viewer session verifier",
    python_requires=">=3.10,<3.13",
    install_requires=["cryptography>=42,<51"],
    packages=[],
    py_modules=[],
    cmdclass={"build_py": NoPythonFallback},
    entry_points={"console_scripts": ["duckietown-viewer-guard=duckietown_viewer_guard:main"]},
    ext_modules=cythonize(
        [
            Extension("duckietown_viewer_guard", ["lib/dt_shell/viewer_runtime.py"]),
            Extension("duckietown_viewer_guard_device", ["lib/dt_shell_device.py"]),
            Extension(
                "duckietown_viewer_guard_trust", ["tools/viewer_guard/trust.pyx"],
                include_dirs=[str(include)],
            ),
        ],
        build_dir="build/viewer-guard-cython",
        compiler_directives={"language_level": "3", "binding": True, "annotation_typing": False},
    ),
)
