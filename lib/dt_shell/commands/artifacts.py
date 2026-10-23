"""Signed external command snapshots; no command code is executed by this module."""

import base64
import binascii
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import requests
from filelock import FileLock


MANIFEST_NAME = "duckietown_commands.json"
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_FILES = 20000
STORE_NAME = ".dts-signed"
INDEX_NAME = "current.json"


class CommandArtifactError(RuntimeError):
    pass


class CommandArtifactUnavailable(CommandArtifactError):
    pass


def failure(detail: str) -> CommandArtifactError:
    return CommandArtifactError(
        f"Command-set integrity check failed: {detail} "
        "No unsigned code will be loaded. Restore a verified snapshot or contact Duckietown support."
    )


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise failure("duplicate metadata fields.")
        result[key] = value
    return result


def _json(content: bytes):
    try:
        return json.loads(content, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as error:
        raise failure("invalid JSON metadata.") from error


def safe_relative(value: str) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\\" not in value
        and not any(character in value for character in ':<>"|?*')
        and not PurePosixPath(value).is_absolute()
        and all(part not in ("", ".", "..") for part in value.split("/"))
        and all(not part.endswith((".", " ")) for part in value.split("/"))
        and all(
            part.split(".")[0].upper()
            not in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{n}" for n in range(1, 10)),
                *(f"LPT{n}" for n in range(1, 10)),
            }
            for part in value.split("/")
        )
        and not any(ord(character) < 32 for character in value)
    )


def version_tuple(value: str) -> tuple[int, int, int]:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None
    ):
        raise failure("invalid command-set or shell version.")
    major, minor, patch = map(int, value.split("."))
    return major, minor, patch


def repository_identity(provider: str, username: str, project: str) -> str:
    if (
        provider != "github.com"
        or re.fullmatch(r"[A-Za-z0-9_-]+", username) is None
        or re.fullmatch(r"[A-Za-z0-9_.-]+", project) is None
        or project in (".", "..")
    ):
        raise failure("signed command delivery currently requires a GitHub repository.")
    return f"github.com/{username.lower()}/{project.lower()}"


def release_tag(branch: str) -> str:
    if (
        not isinstance(branch, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,127}", branch) is None
        or any(part in ("", ".", "..") for part in branch.split("/"))
    ):
        raise failure("invalid command release channel.")
    return (
        "dts-commands-"
        + branch.replace("/", "-")
        + "-"
        + hashlib.sha256(branch.encode()).hexdigest()[:12]
    )


def unpack_envelope(envelope: bytes) -> tuple[bytes, bytes]:
    if len(envelope) > MAX_METADATA_BYTES:
        raise failure("command metadata is too large.")
    data = _json(envelope)
    if not isinstance(data, dict) or set(data) != {"manifest", "signature"}:
        raise failure("unsupported signed envelope.")
    try:
        content = base64.b64decode(data["manifest"], validate=True)
        signature = base64.b64decode(data["signature"], validate=True)
    except (TypeError, ValueError, binascii.Error) as error:
        raise failure("invalid signature encoding.") from error
    if len(signature) != 64:
        raise failure("invalid signature length.")
    return content, signature


@dataclass(frozen=True)
class SignedManifest:
    repository: str
    branch: str
    distributions: tuple[str, ...]
    version: str
    minimum_shell_version: str
    maximum_shell_version: str
    revision: int
    commit: str
    created_at: int
    requirements: Optional[str]
    archive_name: str
    archive_sha256: str
    archive_size: int
    files: Mapping[str, Mapping[str, object]]
    identifier: str
    envelope: bytes

    def matches(
        self, repository: str, branch: str, distribution: str, shell_version: str
    ):
        if self.repository != repository or self.branch != branch:
            raise failure(
                "the artifact belongs to a different repository or release channel."
            )
        if distribution not in self.distributions:
            raise failure(
                f"the artifact is not approved for the '{distribution}' distribution."
            )
        if not (
            version_tuple(self.minimum_shell_version)
            <= version_tuple(shell_version)
            <= version_tuple(self.maximum_shell_version)
        ):
            raise failure(
                f"this artifact requires DTS {self.minimum_shell_version} through "
                f"{self.maximum_shell_version}; installed DTS is {shell_version}."
            )
        if self.created_at > time.time() + 300:
            raise failure(
                "the artifact has a future publication date; check this computer's clock."
            )


def parse_manifest(content: bytes, envelope: bytes) -> SignedManifest:
    data = _json(content)
    fields = {
        "format",
        "repository",
        "branch",
        "distributions",
        "version",
        "minimum_shell_version",
        "maximum_shell_version",
        "revision",
        "commit",
        "created_at",
        "requirements",
        "archive",
        "files",
    }
    if (
        not isinstance(data, dict)
        or set(data) != fields
        or type(data["format"]) is not int
        or data["format"] != 1
        or canonical_json(data) != content
    ):
        raise failure("unsupported or noncanonical signed manifest.")
    repository = data["repository"]
    if not isinstance(repository, str) or len(repository.split("/")) != 3:
        raise failure("invalid repository identity.")
    if repository_identity(*repository.split("/")) != repository:
        raise failure("noncanonical repository identity.")
    release_tag(data["branch"])
    distributions = data["distributions"]
    if (
        not isinstance(distributions, list)
        or not distributions
        or any(value not in ("ente", "daffy") for value in distributions)
        or distributions != sorted(set(distributions))
    ):
        raise failure("invalid distribution metadata.")
    version_tuple(data["version"])
    minimum = version_tuple(data["minimum_shell_version"])
    maximum = version_tuple(data["maximum_shell_version"])
    if minimum > maximum:
        raise failure("invalid shell compatibility range.")
    if (
        type(data["revision"]) is not int
        or data["revision"] < 1
        or type(data["created_at"]) is not int
        or data["created_at"] < 1
        or not isinstance(data["commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", data["commit"]) is None
    ):
        raise failure("invalid release revision, commit, or publication date.")
    archive = data["archive"]
    if (
        not isinstance(archive, dict)
        or set(archive) != {"name", "sha256", "size"}
        or not safe_relative(archive["name"])
        or "/" in archive["name"]
        or not archive["name"].endswith(".zip")
        or not isinstance(archive["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", archive["sha256"]) is None
        or type(archive["size"]) is not int
        or not 0 < archive["size"] <= MAX_ARCHIVE_BYTES
    ):
        raise failure("invalid archive metadata.")
    files = data["files"]
    if not isinstance(files, dict) or not 0 < len(files) <= MAX_FILES:
        raise failure("invalid file inventory.")
    folded = set()
    prefixes = {}
    total = 0
    for name, entry in files.items():
        if (
            not safe_relative(name)
            or MANIFEST_NAME in name.split("/")
            or any(
                part in (".git", "__pycache__", STORE_NAME) for part in name.split("/")
            )
            or name.endswith((".pyc", ".pyo"))
            or name.casefold() in folded
            or not isinstance(entry, dict)
            or set(entry) != {"sha256", "size", "executable"}
            or not isinstance(entry["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
            or type(entry["size"]) is not int
            or entry["size"] < 0
            or type(entry["executable"]) is not bool
        ):
            raise failure("unsafe or invalid inventory entry.")
        folded.add(name.casefold())
        parts = name.split("/")
        for count in range(1, len(parts) + 1):
            prefix = "/".join(parts[:count])
            previous = prefixes.setdefault(prefix.casefold(), prefix)
            if previous != prefix or (count < len(parts) and prefix in files):
                raise failure(
                    "case-colliding paths or file/directory conflicts in the inventory."
                )
        total += entry["size"]
    if total > MAX_ARCHIVE_BYTES:
        raise failure("the expanded command snapshot is too large.")
    requirements = data["requirements"]
    if requirements is not None and (
        not isinstance(requirements, str) or requirements not in files
    ):
        raise failure("the dependency list is outside the signed inventory.")
    return SignedManifest(
        repository,
        data["branch"],
        tuple(distributions),
        data["version"],
        data["minimum_shell_version"],
        data["maximum_shell_version"],
        data["revision"],
        data["commit"],
        data["created_at"],
        requirements,
        archive["name"],
        archive["sha256"],
        archive["size"],
        MappingProxyType(
            {name: MappingProxyType(entry) for name, entry in files.items()}
        ),
        hashlib.sha256(content).hexdigest(),
        envelope,
    )


def verify_manifest(envelope: bytes) -> SignedManifest:
    # Only the native bootstrap supplies the command trust key; URLs and environment variables cannot.
    import dt_shell_release

    content, signature = unpack_envelope(envelope)
    try:
        dt_shell_release.verify_command_signature(signature, content)
    except ValueError as error:
        raise failure("the command manifest signature is invalid.") from error
    return parse_manifest(content, envelope)


def verified_file(root: Path, relative: str, manifest: SignedManifest) -> bytes:
    if relative not in manifest.files:
        raise failure(f"unexpected file '{relative}'.")
    path = root.joinpath(*relative.split("/"))
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise failure(
            f"'{relative}' is a symbolic link or outside the command snapshot."
        )
    try:
        content = path.read_bytes()
    except OSError as error:
        raise failure(f"'{relative}' cannot be read: {error}.") from error
    entry = manifest.files[relative]
    if (
        len(content) != entry["size"]
        or hashlib.sha256(content).hexdigest() != entry["sha256"]
    ):
        raise failure(f"'{relative}' is missing or has been modified.")
    if os.name != "nt" and bool(path.stat().st_mode & 0o111) != entry["executable"]:
        raise failure(f"the executable permissions of '{relative}' have been modified.")
    return content


def verify_snapshot(root: Path, manifest: SignedManifest):
    if root.is_symlink() or not root.is_dir():
        raise failure("the command snapshot is missing or is a symbolic link.")
    try:
        if (root / MANIFEST_NAME).read_bytes() != manifest.envelope:
            raise failure("cached command metadata has been modified.")
        actual = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise failure("symbolic links are not allowed in command snapshots.")
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
            elif not path.is_dir():
                raise failure("special files are not allowed in command snapshots.")
        expected = set(manifest.files) | {MANIFEST_NAME}
        if actual != expected:
            raise failure("missing or unexpected files in the command snapshot.")
        for name in manifest.files:
            verified_file(root, name, manifest)
    except OSError as error:
        raise failure(f"the command inventory cannot be read: {error}.") from error


def verify_requirements(root: Path, manifest: SignedManifest):
    pending = [manifest.requirements] if manifest.requirements is not None else []
    visited = set()
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        try:
            content = verified_file(root, relative, manifest).decode("utf-8")
            lines = content.replace("\\\r\n", "").replace("\\\n", "").splitlines()
            for line in lines:
                tokens = shlex.split(line, comments=True)
                for index, token in enumerate(tokens):
                    included = None
                    if token in ("-r", "-c", "--requirement", "--constraint"):
                        if index + 1 >= len(tokens):
                            raise failure("a requirements include has no filename.")
                        included = tokens[index + 1]
                    elif token.startswith(("--requirement=", "--constraint=")):
                        included = token.split("=", 1)[1]
                    elif token.startswith(("-r", "-c")) and len(token) > 2:
                        included = token[2:]
                    if included is not None:
                        candidate = (root / relative).parent / included
                        if not candidate.resolve().is_relative_to(root.resolve()):
                            raise failure(
                                "a dependency include is outside the signed snapshot."
                            )
                        pending.append(
                            candidate.resolve().relative_to(root.resolve()).as_posix()
                        )
        except (ValueError, UnicodeError) as error:
            raise failure(
                "a dependency list has invalid syntax or encoding."
            ) from error


def extract_archive(content: bytes, destination: Path, manifest: SignedManifest):
    if (
        len(content) != manifest.archive_size
        or hashlib.sha256(content).hexdigest() != manifest.archive_sha256
    ):
        raise failure("the downloaded archive has been modified.")
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or set(names) != set(manifest.files):
                raise failure("the archive does not match the signed file inventory.")
            for entry in entries:
                mode = entry.external_attr >> 16
                expected = manifest.files[entry.filename]
                if (
                    not safe_relative(entry.filename)
                    or entry.is_dir()
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or entry.flag_bits & 1
                    or entry.file_size != expected["size"]
                ):
                    raise failure("unsafe archive entry.")
                value = archive.read(entry)
                if hashlib.sha256(value).hexdigest() != expected["sha256"]:
                    raise failure(
                        f"'{entry.filename}' does not match its signed checksum."
                    )
                path = destination.joinpath(*entry.filename.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
                path.chmod(0o755 if expected["executable"] else 0o644)
    except (BadZipFile, OSError, RuntimeError) as error:
        if isinstance(error, CommandArtifactError):
            raise
        raise failure(f"the command archive cannot be extracted: {error}.") from error
    (destination / MANIFEST_NAME).write_bytes(manifest.envelope)
    verify_snapshot(destination, manifest)
    verify_requirements(destination, manifest)


def _download(url: str, limit: int) -> bytes:
    try:
        with requests.get(url, timeout=(5, 30), stream=True) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > limit:
                    raise failure("the download exceeds its allowed size.")
            return bytes(content)
    except requests.RequestException as error:
        raise CommandArtifactUnavailable(
            f"Could not download signed commands from '{url}': {error}"
        ) from error


def artifact_url(repository: str, branch: str, name: str) -> str:
    if not safe_relative(name) or "/" in name:
        raise failure("invalid release asset name.")
    return f"https://{repository}/releases/download/{quote(release_tag(branch), safe='')}/{quote(name, safe='')}"


class CommandArtifactStore:
    def __init__(
        self,
        cache: Path,
        repository: str,
        branch: str,
        distribution: str,
        shell_version: str,
    ):
        self.cache = cache
        self.store = cache / STORE_NAME
        self.repository = repository
        self.branch = branch
        self.distribution = distribution
        self.shell_version = shell_version

    def _match(self, manifest: SignedManifest):
        manifest.matches(
            self.repository, self.branch, self.distribution, self.shell_version
        )

    def cached(self) -> Optional[tuple[Path, SignedManifest]]:
        index = self.store / INDEX_NAME
        if not index.exists():
            if self.store.exists():
                raise failure("the signed cache index is missing.")
            return None
        if index.is_symlink() or self.store.is_symlink() or self.cache.is_symlink():
            raise failure("the command cache contains a symbolic link.")
        try:
            envelope = index.read_bytes()
        except OSError as error:
            raise failure(f"cached metadata cannot be read: {error}.") from error
        manifest = verify_manifest(envelope)
        self._match(manifest)
        root = self.store / manifest.identifier
        verify_snapshot(root, manifest)
        return root, manifest

    def ensure(
        self, check_updates: bool, readonly: bool = False, warn=None
    ) -> tuple[Path, SignedManifest]:
        if readonly:
            cached = self.cached()
            if cached is None:
                raise failure(
                    "there is no verified cache; run DTS normally to download signed commands."
                )
            return cached
        if self.cache.is_symlink() or self.store.is_symlink():
            raise failure("the command cache contains a symbolic link.")
        self.cache.mkdir(parents=True, exist_ok=True)
        # The lock spans verification, staging and pointer replacement, not command execution.
        with FileLock(str(self.cache / ".dts-signed.lock"), timeout=60):
            cached = self.cached()
            if cached is not None and not check_updates:
                return cached
            try:
                envelope = _download(
                    artifact_url(self.repository, self.branch, MANIFEST_NAME),
                    MAX_METADATA_BYTES,
                )
            except CommandArtifactUnavailable as error:
                if cached is None or warn is None:
                    raise
                warn(f"{error}. Continuing with the verified cached command snapshot.")
                return cached
            latest = verify_manifest(envelope)
            self._match(latest)
            if cached is not None:
                previous = cached[1]
                if latest.revision < previous.revision:
                    raise failure(
                        "a stale release would roll back the installed command revision."
                    )
                if latest.revision == previous.revision:
                    if latest.identifier != previous.identifier:
                        raise failure(
                            "a release revision was reused for different command content."
                        )
                    return cached
            archive = _download(
                artifact_url(self.repository, self.branch, latest.archive_name),
                latest.archive_size,
            )
            destination = self.store / latest.identifier
            if destination.exists():
                verify_snapshot(destination, latest)
            else:
                with tempfile.TemporaryDirectory(
                    prefix=".staging-", dir=self.cache
                ) as temporary:
                    staged = Path(temporary) / "snapshot"
                    staged.mkdir()
                    extract_archive(archive, staged, latest)
                    self.store.mkdir(exist_ok=True)
                    staged.rename(destination)
            descriptor, temporary = tempfile.mkstemp(prefix=".index-", dir=self.store)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(envelope)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.store / INDEX_NAME)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return destination, latest


_roots: dict[Path, SignedManifest] = {}


class VerifiedSourceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name: str, path: str, root: Path, manifest: SignedManifest):
        super().__init__(name, path)
        self.root = root
        self.manifest = manifest

    def get_code(self, fullname):
        relative = Path(self.path).relative_to(self.root).as_posix()
        # Compile the verified bytes, never an unsigned timestamp/hash-based .pyc cache.
        return compile(
            verified_file(self.root, relative, self.manifest),
            self.path,
            "exec",
            dont_inherit=True,
        )

    def get_source(self, fullname):
        relative = Path(self.path).relative_to(self.root).as_posix()
        return importlib.util.decode_source(
            verified_file(self.root, relative, self.manifest)
        )


class VerifiedCommandFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            return None
        origin = Path(spec.origin).absolute()
        for root, manifest in _roots.items():
            if not origin.is_relative_to(root):
                continue
            relative = origin.relative_to(root).as_posix()
            verified_file(root, relative, manifest)
            if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
                spec.loader = VerifiedSourceLoader(
                    fullname, str(origin), root, manifest
                )
            elif isinstance(spec.loader, importlib.machinery.SourcelessFileLoader):
                raise failure(
                    "unsigned bytecode cannot be imported from a command snapshot."
                )
            return spec
        return None


_finder = VerifiedCommandFinder()


def register_snapshot(root: Path, manifest: SignedManifest):
    root = root.absolute()
    _roots[root] = manifest
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)


def source_spec(name: str, path: str, submodule_search_locations=None):
    origin = Path(path).absolute()
    loader = None
    for root, manifest in _roots.items():
        if origin.is_relative_to(root):
            loader = VerifiedSourceLoader(name, str(origin), root, manifest)
            break
    return importlib.util.spec_from_file_location(
        name, path, loader=loader, submodule_search_locations=submodule_search_locations
    )
