"""Build and publish signed, source-only command artifacts without importing command code."""

import argparse
import ast
import base64
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release import commands_public_key, keygen, signing_key

SPEC = importlib.util.spec_from_file_location(
    "dts_command_artifacts", ROOT / "lib/dt_shell/commands/artifacts.py"
)
assert SPEC is not None and SPEC.loader is not None
artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = artifacts
SPEC.loader.exec_module(artifacts)


def configuration_metadata(source: Path) -> tuple[str, str, str]:
    configuration = source / "__command_set__" / "configuration.py"
    if not configuration.exists():
        return "0.0.0", "0.0.0", "99.99.99"
    tree = ast.parse(configuration.read_bytes(), filename=str(configuration))
    versions = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(n, ast.Name) and n.id == "VERSION" for n in node.targets
        ):
            versions.append(ast.literal_eval(node.value))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "VERSION"
        ):
            versions.append(ast.literal_eval(node.value))
    if len(versions) != 1:
        raise ValueError(
            "Command configuration must declare one literal VERSION string."
        )
    configuration_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DTCommandSetConfiguration"
    ]
    if len(configuration_classes) != 1:
        raise ValueError("Expected one DTCommandSetConfiguration class.")
    bounds = []
    for name in ("minimum_shell_version", "maximum_shell_version"):
        functions = [
            node
            for node in configuration_classes[0].body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        if len(functions) != 1:
            raise ValueError(f"Command configuration must declare {name}().")
        body = [
            node
            for node in functions[0].body
            if not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            raise ValueError(
                f"{name}() must return a literal version tuple for signed publication."
            )
        value = ast.literal_eval(body[0].value)
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or any(type(n) is not int or n < 0 for n in value)
        ):
            raise ValueError(f"{name}() must return three nonnegative integers.")
        bounds.append(".".join(map(str, value)))
    artifacts.version_tuple(versions[0])
    return versions[0], bounds[0], bounds[1]


def tracked_payload(source: Path) -> tuple[dict[str, tuple[bytes, bool]], str]:
    source = source.resolve()
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    if dirty.strip():
        raise ValueError("Publish only a clean, committed command checkout.")
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    entries = subprocess.check_output(
        ["git", "-C", str(source), "ls-files", "--stage", "-z"]
    ).split(b"\0")
    payload = {}
    for entry in entries:
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, _, stage = metadata.decode("ascii").split()
        name = path.decode("utf-8")
        if (
            mode not in ("100644", "100755")
            or stage != "0"
            or not artifacts.safe_relative(name)
        ):
            raise ValueError(
                f"Unsupported link, submodule, or path in command payload: {name}."
            )
        full = source / name
        if full.is_symlink() or not full.resolve().is_relative_to(source):
            raise ValueError(f"Unsafe command payload path: {name}.")
        content = full.read_bytes()
        if (
            b"-----BEGIN PRIVATE KEY-----" in content
            or b"-----BEGIN ED25519 PRIVATE KEY-----" in content
        ):
            raise ValueError(f"Private-key material cannot be published: {name}.")
        payload[name] = content, mode == "100755"
    return payload, commit


def build_payload(
    payload: dict[str, tuple[bytes, bool]],
    commit: str,
    repository: str,
    branch: str,
    distributions: list[str],
    revision: int,
    metadata: tuple[str, str, str],
    directory: Path,
    key,
    manifest_name: str = artifacts.MANIFEST_NAME,
):
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Use an empty artifact output directory.")
    directory.mkdir(parents=True, exist_ok=True)
    version, minimum, maximum = metadata
    files = {
        name: {
            "sha256": hashlib.sha256(value).hexdigest(),
            "size": len(value),
            "executable": executable,
        }
        for name, (value, executable) in payload.items()
    }
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, (value, executable) in sorted(payload.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = (
                stat.S_IFREG | (0o755 if executable else 0o644)
            ) << 16
            archive.writestr(entry, value)
    content = stream.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    archive_name = f"commands-{revision}-{digest}.zip"
    requirements = "__command_set__/requirements.txt"
    manifest = artifacts.canonical_json(
        {
            "format": 1,
            "repository": repository,
            "branch": branch,
            "distributions": sorted(set(distributions)),
            "version": version,
            "minimum_shell_version": minimum,
            "maximum_shell_version": maximum,
            "revision": revision,
            "commit": commit,
            "created_at": int(time.time()),
            "requirements": requirements if requirements in payload else None,
            "archive": {"name": archive_name, "sha256": digest, "size": len(content)},
            "files": files,
        }
    )
    envelope = artifacts.canonical_json(
        {
            "manifest": base64.b64encode(manifest).decode("ascii"),
            "signature": base64.b64encode(key.sign(manifest)).decode("ascii"),
        }
    )
    parsed = artifacts.parse_manifest(manifest, envelope)
    with tempfile.TemporaryDirectory(prefix="dts-command-validation-") as temporary:
        artifacts.extract_archive(content, Path(temporary), parsed)
    (directory / archive_name).write_bytes(content)
    (directory / manifest_name).write_bytes(envelope)
    return parsed


def build(
    source: Path,
    directory: Path,
    repository: str,
    branch: str,
    distributions: list[str],
    revision: int,
    key,
):
    payload, commit = tracked_payload(source)
    return build_payload(
        payload,
        commit,
        repository,
        branch,
        distributions,
        revision,
        configuration_metadata(source),
        directory,
        key,
    )


def verify_envelope(envelope: bytes):
    content, signature = artifacts.unpack_envelope(envelope)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(commands_public_key())).verify(
            signature, content
        )
    except InvalidSignature as error:
        raise ValueError("The command artifact signature is invalid.") from error
    return artifacts.parse_manifest(content, envelope)


def verify(directory: Path, manifest_name: str = artifacts.MANIFEST_NAME):
    manifest = verify_envelope((directory / manifest_name).read_bytes())
    if {path.name for path in directory.iterdir()} != {
        manifest.archive_name,
        manifest_name,
    }:
        raise ValueError(
            "Unexpected or missing files in the command release directory."
        )
    with tempfile.TemporaryDirectory(prefix="dts-command-validation-") as temporary:
        artifacts.extract_archive(
            (directory / manifest.archive_name).read_bytes(), Path(temporary), manifest
        )
    return manifest


def publish(directory: Path, manifest_name: str = artifacts.MANIFEST_NAME):
    manifest = verify(directory, manifest_name)
    repo = manifest.repository.removeprefix("github.com/")
    tag = artifacts.release_tag(manifest.branch)
    view = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo], capture_output=True, text=True
    )
    if view.returncode:
        if "release not found" not in view.stderr.lower() and "404" not in view.stderr:
            raise RuntimeError(
                f"Cannot inspect the command release: {view.stderr.strip()}"
            )
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                repo,
                "--target",
                manifest.commit,
                "--title",
                f"Signed DTS commands: {manifest.branch}",
                "--notes",
                "Verified command artifacts for official DTS installations. This channel is updated by trusted CI.",
            ],
            check=True,
        )
    # Content-addressed archives are immutable. Replace the single signed envelope last.
    subprocess.run(
        [
            "gh",
            "release",
            "upload",
            tag,
            str(directory / manifest.archive_name),
            "--repo",
            repo,
            "--clobber",
        ],
        check=True,
    )
    subprocess.run(
        [
            "gh",
            "release",
            "upload",
            tag,
            str(directory / manifest_name),
            "--repo",
            repo,
            "--clobber",
        ],
        check=True,
    )


def fixture_payload() -> dict[str, tuple[bytes, bool]]:
    return {
        "utils/__init__.py": (b"FIXTURE_GENERATION = 1\n", False),
        "utils/table_utils.py": (
            b"def format_matrix(*args, **kwargs):\n"
            b"    raise RuntimeError('Table formatting is outside the version fixture')\n",
            False,
        ),
        "__command_set__/configuration.py": (
            b"from dt_shell.commands import DTCommandSetConfigurationAbs\n"
            b"from dt_shell.environments import VirtualPython3Environment\n"
            b"VERSION = '0.0.0'\n"
            b"class DTCommandSetConfiguration(DTCommandSetConfigurationAbs):\n"
            b"    @classmethod\n    def default_environment(cls): return VirtualPython3Environment()\n"
            b"    @classmethod\n    def version(cls): return 0, 0, 0\n"
            b"    @classmethod\n    def minimum_shell_version(cls): return 0, 0, 0\n"
            b"    @classmethod\n    def maximum_shell_version(cls): return 999, 999, 999\n",
            False,
        ),
        "__command_set__/init.py": (b"", False),
        "probe/__init__.py": (b"", False),
        "probe/command.py": (
            b"from dt_shell import DTCommandAbs\n"
            b"class DTCommand(DTCommandAbs):\n"
            b"    @staticmethod\n    def command(shell, args): print('SIGNED_COMMAND_EXECUTED')\n",
            False,
        ),
    }


def build_fixture(
    source: Path,
    directory: Path,
    repository: str,
    branch: str,
    distributions: list[str],
    revision: int,
    key,
    manifest_name: str = "duckietown_commands.fixture.json",
):
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    payload = fixture_payload()
    updated = dict(payload)
    updated["utils/__init__.py"] = (b"FIXTURE_GENERATION = 2\n", False)
    updated["probe/command.py"] = (
        updated["probe/command.py"][0].replace(
            b"SIGNED_COMMAND_EXECUTED", b"UPDATED_SIGNED_COMMAND_EXECUTED"
        ),
        False,
    )
    with tempfile.TemporaryDirectory(prefix="dts-command-next-fixture-") as temporary:
        next_directory = Path(temporary) / "release"
        next_manifest = build_payload(
            updated,
            commit,
            repository,
            branch,
            distributions,
            revision + 1,
            ("0.0.0", "0.0.0", "999.999.999"),
            next_directory,
            key,
        )
        payload["__fixture_update__/next-envelope.json"] = (
            next_manifest.envelope,
            False,
        )
        payload["__fixture_update__/" + next_manifest.archive_name] = (
            (next_directory / next_manifest.archive_name).read_bytes(),
            False,
        )
    return build_payload(
        payload,
        commit,
        repository,
        branch,
        distributions,
        revision,
        ("0.0.0", "0.0.0", "999.999.999"),
        directory,
        key,
        manifest_name,
    )


def download_fixture(directory: Path, repository: str, branch: str):
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Use an empty fixture output directory.")
    directory.mkdir(parents=True, exist_ok=True)
    envelope = artifacts._download(
        artifacts.artifact_url(repository, branch, "duckietown_commands.fixture.json"),
        artifacts.MAX_METADATA_BYTES,
    )
    manifest = verify_envelope(envelope)
    manifest.matches(repository, branch, "daffy", "6.3.0")
    archive = artifacts._download(
        artifacts.artifact_url(repository, branch, manifest.archive_name),
        manifest.archive_size,
    )
    (directory / artifacts.MANIFEST_NAME).write_bytes(envelope)
    (directory / manifest.archive_name).write_bytes(archive)
    verify(directory)


def ready(repository: str, shell_version: str):
    for branch in ("ente", "ente-staging", "daffy", "daffy-staging"):
        envelope = artifacts._download(
            artifacts.artifact_url(repository, branch, artifacts.MANIFEST_NAME),
            artifacts.MAX_METADATA_BYTES,
        )
        manifest = verify_envelope(envelope)
        manifest.matches(repository, branch, branch.split("-")[0], shell_version)
        archive = artifacts._download(
            artifacts.artifact_url(repository, branch, manifest.archive_name),
            manifest.archive_size,
        )
        with tempfile.TemporaryDirectory(prefix="dts-command-readiness-") as temporary:
            artifacts.extract_archive(archive, Path(temporary), manifest)
    print(
        f"Verified signed artifacts for all four command channels with DTS {shell_version}."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("keygen")
    generate.add_argument("--private-key", type=Path, required=True)
    generate.add_argument("--public-key", type=Path, required=True)
    for name in ("build", "fixture"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        command.add_argument("directory", type=Path)
        command.add_argument(
            "--repository", required=True, help="github.com/owner/project"
        )
        command.add_argument("--branch", required=True)
        command.add_argument(
            "--distribution", action="append", choices=["daffy", "ente"], required=True
        )
        command.add_argument("--revision", type=int, required=True)
    for name in ("verify", "publish"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        command.add_argument("--fixture", action="store_true")
    download = commands.add_parser("download-fixture")
    download.add_argument("directory", type=Path)
    download.add_argument(
        "--repository", default="github.com/duckietown/duckietown-shell-commands"
    )
    download.add_argument("--branch", default="daffy")
    readiness = commands.add_parser("ready")
    readiness.add_argument(
        "--repository", default="github.com/duckietown/duckietown-shell-commands"
    )
    readiness.add_argument("--version", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "keygen":
            keygen(arguments.private_key, arguments.public_key)
        elif arguments.command == "build":
            build(
                arguments.source,
                arguments.directory,
                arguments.repository,
                arguments.branch,
                arguments.distribution,
                arguments.revision,
                signing_key("DTS_COMMANDS"),
            )
        elif arguments.command == "fixture":
            build_fixture(
                arguments.source,
                arguments.directory,
                arguments.repository,
                arguments.branch,
                arguments.distribution,
                arguments.revision,
                signing_key("DTS_COMMANDS"),
            )
        elif arguments.command == "download-fixture":
            download_fixture(
                arguments.directory, arguments.repository, arguments.branch
            )
        elif arguments.command == "ready":
            ready(arguments.repository, arguments.version)
        else:
            name = (
                "duckietown_commands.fixture.json"
                if arguments.fixture
                else artifacts.MANIFEST_NAME
            )
            if arguments.command == "publish":
                publish(arguments.directory, name)
            else:
                verify(arguments.directory, name)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Command release failed: {error}\n")


if __name__ == "__main__":
    main()
