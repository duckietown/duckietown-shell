"""Offline Engine inventory/catalog signing; private keys never enter an image."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_support import engine_public_keys, engine_release_public_key
from tools.viewer_release import sign


common_spec = importlib.util.spec_from_file_location(
    "duckietown_engine_guard_common", ROOT / "lib/dt_shell/viewer_runtime.py",
)
common = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common)
sys.modules.setdefault(common_spec.name, common)
spec = importlib.util.spec_from_file_location("engine_release_runtime", ROOT / "lib/dt_shell/engine_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def signing_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Engine signing requires an unencrypted Ed25519 PEM.")
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    if public != engine_release_public_key():
        raise ValueError("The Engine signing key does not match compiled public trust.")
    return key


def seal(root: Path, *, version: str, platform: str, key: Ed25519PrivateKey) -> dict:
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None or platform not in ("linux", "linux-arm64"):
        raise ValueError("Invalid Engine release coordinates.")
    claims = {
        "format": 1, "audience": "duckiematrix-engine-release", "kind": "engine",
        "distribution": "ente", "version": version, "platform": platform,
        "entrypoint": "packages/duckiematrix_engine",
        "files": common.inventory(root, manifest=runtime.MANIFEST),
        "trust": {"release": engine_release_public_key(), "issuers": json.loads(engine_public_keys())},
    }
    (root / runtime.MANIFEST).write_bytes(sign(claims, key))
    return runtime.verify_release(
        root, release_key=engine_release_public_key(), issuer_keys=json.loads(engine_public_keys()),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    release = commands.add_parser("seal")
    release.add_argument("root", type=Path)
    release.add_argument("--version", required=True)
    release.add_argument("--platform", required=True)
    release.add_argument("--key", type=Path, required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("images", type=Path)
    catalog.add_argument("--version", required=True)
    catalog.add_argument("--key", type=Path, required=True)
    catalog.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = signing_key(args.key)
    if args.command == "seal":
        result = seal(args.root.resolve(), version=args.version, platform=args.platform, key=key)
    else:
        claims = {
            "format": 1, "audience": "duckiematrix-engine-images", "distribution": "ente",
            "version": args.version, "images": common.decode_json(args.images.read_bytes()),
        }
        raw = sign(claims, key)
        result = runtime.verify_image_catalog(raw, release_key=engine_release_public_key())
        args.output.write_bytes(raw)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, sort_keys=True))


if __name__ == "__main__":
    main()
