"""Offline Viewer artifact signing; private keys remain in protected release jobs."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_support import viewer_public_keys, viewer_release_public_key

spec = importlib.util.spec_from_file_location("viewer_release_runtime", ROOT / "lib/dt_shell/viewer_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def sign(claims: dict, key: Ed25519PrivateKey) -> bytes:
    content = runtime.canonical(claims)
    return runtime.canonical({
        "payload": base64.b64encode(content).decode("ascii"),
        "signature": base64.b64encode(key.sign(content)).decode("ascii"),
    })


def signing_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Viewer signing requires an unencrypted Ed25519 PEM.")
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    if public != viewer_release_public_key():
        raise ValueError("The Viewer signing key does not match the compiled public trust.")
    return key


def seal(root: Path, *, version: str, platform: str, entrypoint: str, kind: str, key: Ed25519PrivateKey) -> dict:
    if (
        re.fullmatch(r"\d+\.\d+\.\d+", version) is None
        or platform not in ("linux", "linux-arm64", "macos", "macos-arm64", "windows", "windows-arm64")
        or not runtime.relative_path(entrypoint) or not (root / entrypoint).exists()
        or kind not in ("desktop", "backend")
    ):
        raise ValueError("Invalid Viewer release coordinates or entrypoint.")
    manifest = {
        "format": 1, "audience": "duckietown-viewer-release", "kind": kind,
        "distribution": "ente", "version": version, "platform": platform,
        "entrypoint": entrypoint, "files": runtime.inventory(root, windows=platform.startswith("windows")),
        "trust": {"release": viewer_release_public_key(), "issuers": json.loads(viewer_public_keys())},
    }
    (root / runtime.MANIFEST).write_bytes(sign(manifest, key))
    return runtime.verify_release(
        root, release_key=viewer_release_public_key(), issuer_keys=json.loads(viewer_public_keys()), kind=kind,
    )


def pack(root: Path, output: Path) -> None:
    runtime.verify_release(
        root, release_key=viewer_release_public_key(), issuer_keys=json.loads(viewer_public_keys()),
    )
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in sorted(directories + files):
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    entry = ZipInfo(relative)
                    entry.create_system = 3
                    entry.external_attr = 0o120777 << 16
                    archive.writestr(entry, os.readlink(path))
                elif path.is_file():
                    archive.write(path, relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    release = commands.add_parser("seal")
    release.add_argument("root", type=Path)
    release.add_argument("--version", required=True)
    release.add_argument("--platform", required=True)
    release.add_argument("--entrypoint", required=True)
    release.add_argument("--kind", choices=("desktop", "backend"), required=True)
    release.add_argument("--key", type=Path, required=True)
    release.add_argument("--archive", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("--kind", choices=("desktop", "backend"), default="desktop")
    catalog = commands.add_parser("catalog")
    catalog.add_argument("images", type=Path, help="JSON mapping of Docker architectures to immutable image identities")
    catalog.add_argument("--version", required=True)
    catalog.add_argument("--key", type=Path, required=True)
    catalog.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "seal":
        result = seal(
            args.root.resolve(), version=args.version, platform=args.platform,
            entrypoint=args.entrypoint, kind=args.kind, key=signing_key(args.key),
        )
        if args.archive:
            pack(args.root.resolve(), args.archive)
    elif args.command == "verify":
        result = runtime.verify_release(
            args.root, release_key=viewer_release_public_key(), issuer_keys=json.loads(viewer_public_keys()),
            kind=args.kind,
        )
    else:
        claims = {
            "format": 1, "audience": "duckietown-viewer-backends", "distribution": "ente",
            "version": args.version, "images": runtime.decode_json(args.images.read_bytes()),
        }
        raw = sign(claims, signing_key(args.key))
        result = runtime.verify_backend_catalog(raw, release_key=viewer_release_public_key())
        args.output.write_bytes(raw)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, sort_keys=True))


if __name__ == "__main__":
    main()
