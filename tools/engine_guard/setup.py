"""Build the Engine verifier without Python source fallbacks."""

import json
from pathlib import Path
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_support import engine_public_keys, engine_release_public_key


include = ROOT / "build" / "engine-guard-include"
include.mkdir(parents=True, exist_ok=True)
header = include / "engine_trust.h"
header.write_text(
    f'static const char DTM_ENGINE_RELEASE_PUBLIC_KEY[] = "{engine_release_public_key()}";\n'
    f"static const char DTM_ENGINE_PUBLIC_KEYS[] = {json.dumps(engine_public_keys())};\n",
    encoding="ascii",
)
setup(
    name="duckiematrix-engine-guard",
    version="1.0.0",
    description="Native, scoped Duckiematrix Engine session verifier",
    python_requires=">=3.10,<3.13",
    install_requires=["cryptography>=42,<51"],
    packages=[],
    py_modules=[],
    ext_modules=cythonize(
        [
            Extension("duckietown_engine_guard", ["lib/dt_shell/engine_runtime.py"]),
            Extension("duckietown_engine_guard_common", ["lib/dt_shell/viewer_runtime.py"]),
            Extension(
                "duckietown_engine_guard_trust", ["tools/engine_guard/trust.pyx"],
                include_dirs=[str(include)], depends=[str(header)],
            ),
        ],
        build_dir="build/engine-guard-cython",
        compiler_directives={"language_level": "3", "binding": True, "annotation_typing": False},
    ),
)
