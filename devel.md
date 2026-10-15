# Duckietown Shell development and releases

The [README](README.md) covers installation and [supported runtimes](README.md#supported-runtimes). User-facing [plan requirements](README.md#plans-and-access), [computer registration and transfers](README.md#plan-and-computer-management), and [profile environment variables](README.md#non-interactive-setup) are maintained there rather than repeated in this guide.

## Source development

Official wheels contain compiled launch, dispatch, authorization, device, profile, and environment modules. They require native verification of a signed staff/superuser developer grant before accepting `DTSHELL_LIB`, `DTSHELL_COMMANDS`, or `DTSHELL_PYTHONPATH`. Empty or nonexistent override directories remain invalid. There is no release flag that disables integrity verification.

Run the Python checkout explicitly for development instead of installing it editable or invoking the official wheel's `dts` entry point. On Linux or macOS:

```shell
git clone git@github.com:duckietown/duckietown-shell.git
git clone git@github.com:duckietown/duckietown-shell-commands.git
cd duckietown-shell
python3.12 -m venv .venv
.venv/bin/python -m pip install -r lib/dt_shell/assets/requirements.txt \
    "cryptography>=44,<51" "Cython>=3.0.12,<4" "docker>=6.1.3,<7"
export DTSHELL_VENV_DIR="$PWD/.venv"
PYTHONPATH="$PWD/lib" DTSHELL_COMMANDS="$PWD/../duckietown-shell-commands" \
    .venv/bin/python -m dt_shell_cli.dts version
```

This example uses sibling Shell and commands checkouts. For an existing commands checkout elsewhere, set `DTSHELL_COMMANDS` to its actual directory instead; `/path/to/...` is a placeholder, not a runnable path.

`DTSHELL_VENV_DIR` keeps delegated source commands in the same environment, where the Cython shim is installed. DTS installs command-set dependencies into that environment on first use.

Dependency records live inside the selected environment under `.dts/installed_dependencies.yaml`, not in the profile. Switching or recreating the environment therefore checks its requirements again. Legacy profile records are not reused, so environments upgraded from older DTS releases perform a one-time dependency check. `pip check` validates installed packages; it does not establish that the command-set requirements have been installed.

On Windows, use `.venv\Scripts\python.exe` and set `$env:PYTHONPATH` to the absolute `lib` directory and `$env:DTSHELL_VENV_DIR` to the absolute `.venv` directory in PowerShell. Source code still performs the normal plan checks; it is a development route, not an authenticated official release. `Cython` supplies the source-mode `cython.compiled` marker without compiling the checkout.

Cryptography is installed explicitly rather than depending on an older source checkout's dependency asset to include it. Source packaging is not this workflow: `pip install -e .` invokes the protected build and still needs the configured native trust keys. Directly executed tools import source packages through `PYTHONPATH`; `DTSHELL_LIB` is handled by the DTS CLI, not by arbitrary Python scripts.

Source mode does not provide native release integrity or embedded Duckiematrix Renderer trust. It supports ordinary development and compilation-only Unity trust generation. Renderer launch and publication tests use an installed signed native DTS release; setting `DTSHELL_LIB` does not turn a source checkout into a verified native build.

## Local commands development

The Shell contains core environment-management commands. Duckietown-specific commands come from [Duckietown Shell Commands](https://github.com/duckietown/duckietown-shell-commands).

`DTSHELL_COMMANDS` selects a local checkout in [explicit source mode](#source-development) or [authenticated native developer mode](#authenticated-developer-mode):

```shell
export DTSHELL_COMMANDS=/path/to/my/duckietown-shell-commands
```

In native mode, current staff/superuser developer authorization is verified before any checkout code is imported. Ordinary plan eligibility and repository access are not sufficient.

For VS Code, set `DTSHELL_COMMANDS` in [`.vscode/python.env`](.vscode/python.env). If the commands repository is cloned beside the Shell repository, an optional symlink makes its files available in the same workspace for source breakpoints. From the Shell repository:

```shell
ln -s "$(realpath ../duckietown-shell-commands)" ./duckietown-shell-commands
```

The symlink does not set `DTSHELL_COMMANDS`; configure the variable separately.

## Debugging with Visual Studio Code

After [source setup](#source-development):

1. Select `.venv` as the Python interpreter and open the Run & Debug view.
2. Select the checked-in [`dts` launch configuration](.vscode/launch.json), which runs `dt_shell_cli.dts`.
3. Supply command arguments through the picker, for example `profile list`.
4. Set source breakpoints and start debugging with F5.

The configured [`.vscode/python.env`](.vscode/python.env) supplies `PYTHONPATH=./lib`. Source breakpoints apply to this explicit Python workflow; compiled native core modules are not Python source files.

For this source workflow, enable `DTSHELL_VENV_DIR=.venv/` in that file so delegated commands also use the source environment.

The default debugger reads that file, not `.env.local`. A private `.env.local` file is ignored by Git but must be loaded explicitly; it is not loaded just because it exists. Private token files require restrictive permissions. Identity-token setup and profile variables are documented under [non-interactive setup](README.md#non-interactive-setup) and [token authentication](README.md#authenticate-a-duckietown-token).

For manual debugging with verbose output:

```shell
PYTHONPATH="$PWD/lib" .venv/bin/python -m dt_shell_cli.dts --debug -vv version
```

## Development container

The checked-in [Dev Container configuration](.devcontainer/devcontainer.json) uses the Ubuntu Noble base, Docker-in-Docker with its own daemon, and an unpinned Python feature. Its current `postCreateCommand` runs `pip install -e . --break-system-packages`, which invokes the native build rather than the explicit source-development workflow. The [host source workflow](#source-development) does not depend on that setup. The [legacy Shell Dockerfiles/images](README.md#legacy-docker-installation) are not an alternative native release path.

Container development requires [VS Code](https://code.visualstudio.com/), the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers), and [Docker](https://www.docker.com/get-started):

1. Before reopening in the container, pin its Python feature to a supported version such as 3.12 and remove the editable-install `postCreateCommand`.
2. Export an ordinary identity token in the host environment before starting VS Code:

   ```shell
   export DTSHELL_TOKEN="dt2-YOUR-IDENTITY-TOKEN"
   code .
   ```

3. Use **Dev Containers: Reopen in Container**.
4. Follow [source setup](#source-development) inside the existing checkout, starting with virtual-environment creation rather than cloning again.

The container sets `DTSHELL_PROFILE=ente` and `DTSHELL_DISTRO=ente` and forwards the exported host token. It does not automatically load `.env.local`. The ordinary 'ente' plan/device checks still apply. See [non-interactive setup](README.md#non-interactive-setup) for the shared profile variables.

After source setup, a normal invocation creates a missing profile:

```shell
PYTHONPATH="$PWD/lib" .venv/bin/python -m dt_shell_cli.dts version
ls -la ~/.duckietown/shell/profiles/ente/
```

`--help` exits during argument parsing and does not create a profile.

Open webpages in the host's default browser from the container with:

```shell
"$BROWSER" https://www.duckietown.org
```

## Authenticated developer mode

Repository read access and ordinary plan eligibility do not grant permission to replace code in an official DTS installation. The native bootstrap requires a dedicated `develop:dts` capability from an active Hub staff **or** superuser account, including superusers whose separate staff flag is false. The capability is independent of the plans granting access to 'ente'; normal 'daffy' use remains plan-free.

First, with source overrides unset, select a profile and store its normal DT2 identity token with `dts tok set`. For 'daffy' development the preferred token slot must also contain a DT2 identity token, even though ordinary 'daffy' use supports legacy tokens. Only the active preferred token is used; a plan-scoped token or a developer grant cannot replace an identity token.

Then set the development variables normally:

```shell
export DTSHELL_LIB=/path/to/duckietown-shell/lib
export DTSHELL_COMMANDS=/path/to/duckietown-shell-commands
export DTSHELL_PYTHONPATH=/path/to/developer/helpers
dts version
```

Each variable is optional. `DTSHELL_PYTHONPATH` uses `:` between directories on Linux/macOS and `;` on Windows. In PowerShell, use `$env:DTSHELL_LIB`, `$env:DTSHELL_COMMANDS`, and `$env:DTSHELL_PYTHONPATH`. Keep the source checkout compatible with the installed native release.

Before importing overridden code, the verified native bootstrap:

- Reads the selected profile and validates its DT2 `auth` identity without importing the overridden shell or commands.
- Uses the wheel-owned native computer-identity component. The existing Linux/macOS/Windows fingerprint is unchanged.
- Verifies a separately signed, non-renewable developer grant against compiled issuer/public-key pins. Unsigned privilege flags, local mode flags, plan eligibility, and arbitrary `DTHUB_HOST`/`DTHUB_URL` servers are not trusted.
- Binds the grant to the account, exact active identity token, approved issuer, and this computer, without registering or limiting staff/superuser computers.
- Allows only the requested source paths and prints the account, issuer, and readable UTC expiry in an authenticated developer-mode notice.

Grants last **at most one hour**, capped by identity-token expiry. If a cached grant is missing or expired, startup automatically requests a new one from the approved Hub before loading source code. A valid cache works offline without a request. An invalid/tampered cache fails explicitly and is never an unsigned fallback; use `dts developer clear` or `dts developer renew` to repair it.

New grants always recheck current database privileges. Removing staff/superuser access blocks the next issuance; an already issued offline grant may remain valid until expiry, for at most one hour. A running session checks expiry at guarded source imports, dispatch, and delegation, with a monotonic deadline. It does not silently renew mid-command: restart DTS to reauthorize. Switching identities or override paths also requires restarting.

The native launcher handles these commands before loading external or overridden code, even when override variables are invalid:

```shell
dts developer status       # Inspect the local signed grant; no network renewal
dts developer renew        # Request a new grant after a current Hub privilege check
dts developer clear        # Remove this profile/issuer/identity/computer's cached grant
dts --profile daffy developer status
dts developer              # List the available subcommands
dts developer --help
dts developer status --help
```

These are also exposed through the embedded command/help surface. Use a fresh `dts` process for recovery after an active session expires. `clear` removes the cache, not account privileges or grants already held by other running processes. Unset source overrides to stop automatic authorization and return to normal DTS. Cache files contain the signed grant, not the raw identity token, and are scoped by profile, issuer, identity fingerprint, and computer.

`status`, `renew`, and `clear` are separate DTS subcommands, with their own help and tab completion. Running `dts developer` lists them rather than enabling developer mode. In the explicit Python source workflow, group and subcommand help are available, but grant management requires the official native DTS installation. Running the checkout does not authenticate a developer grant.

The official wheel's signature and inventory remain required in developer mode. With the compiled command loader, only the explicitly approved `DTSHELL_COMMANDS` checkout can bypass command-set signing; a cached developer grant by itself does not disable normal command verification. Source overrides intentionally allow developers to execute and alter code, so modified source is **not an attested official runtime**. They are not a promise against in-memory monkeypatching or determined local attacks. The explicit Python source workflow remains available separately and is not silently labelled as authenticated official development.

### Developer trust deployment

Production and staging use **different Ed25519 developer-signing keys**, distinct from release, command, Renderer artifact/permission, and DT2 token keys. Generate each pair outside all repositories with `tools/release.py keygen`. Mount only the appropriate private PEM into each Hub as `/run/secrets/dts_developer.key`; never give developer private keys to wheel builders, signing/test jobs, source checkouts, or release artifacts.

Configure the shell repository variable `DTS_DEVELOPER_PUBLIC_KEYS` with exactly these issuer/public-key entries (replace both placeholders with 64 lowercase hexadecimal characters):

```json
{
  "https://hub.duckietown.com": "<production-developer-public-key>",
  "https://staging-hub.duckietown.com": "<staging-developer-public-key>"
}
```

The matching map is required during wheel compilation, sealing, and verification. `BASE_URL` on each Hub must match its HTTPS issuer. Runtime public-key overrides are not supported; rotating a developer key requires coordinated Hub deployment and rebuilt official wheels. Keep the Hub endpoint and wheel public-key pins compatible when deploying updates.

The native CI matrix runs `python tools/developer_test.py wheelhouse`. It first verifies the production wheel, then compiles a temporary bootstrap with ephemeral release/developer keys, re-signs a private test copy, and exercises real native grant checks and source overrides. Production wheels are never altered and production developer private keys are not required. Temporary test keys and artifacts are deleted, not published.

The Hub developer and Renderer grant signers retain Python 3.8-compatible annotations. The native DTS client's CPython 3.10–3.12 requirement does not require a Hub container Python upgrade.

## Duckiematrix Renderer authorization

Duckiematrix follows the ['ente' access policy](README.md#plans-and-access). Use an official native DTS 6.3.0-or-newer installation and an 'ente' profile. Grace access does not grant developer privileges. The Renderer no longer accepts a long-lived identity token through `--token` or a browser URL.

`dts matrix run` automatically obtains a separate signed `use:duckiematrix-renderer` permission. **Only DTS contacts the Hub.** The Renderer verifies pinned Hub signatures locally, then challenges a loopback DTS session using a fresh random nonce every ten seconds. DTS signs account, identity fingerprint, computer, session, nonce, and verified artifact bindings with the launch key authorized by Hub. Proofs last at most thirty seconds and never exceed the underlying permission's expiry. DTS must stay running; a direct launch without the live session is denied. There is no second login in the Renderer.

Normal Renderer permissions last at most **24 hours**. Renderer developer permissions last at most **one hour**. Known identity/qualifying-plan expiration shortens them; privileged accounts are still bound to a computer and expiration. Plan-free grace permissions carry a signed `plan_grace_until` and expire no later than the [plan enforcement deadline](README.md#plans-and-access). DTS and the Renderer validate that exact cutoff; neither cached permissions nor thirty-second proofs extend it. A valid cached permission supports offline relaunches, with a new live session each time; the ordinary DTS 'ente' authorization must also remain valid. Renderer permission does not authorize unrelated 'ente' commands. DTS attempts renewal near expiry. A network outage does not extend a permission; an explicit Hub denial is not an offline fallback. Before the cutoff, loss of a qualifying plan permits normal grace access, not developer access. From the cutoff, loss of eligibility blocks new issuance, but an already issued qualifying-plan permission can remain valid until its original expiry. Ordinary Renderer expirations also contribute to the shared 'ente' computer-transfer deadline.

Unsigned custom binaries and Unity Editor require the separate `develop:duckiematrix-renderer` permission from a current staff **or** superuser account. Repository access and ordinary plan eligibility are not developer authorization:

```shell
dts matrix run --renderer-binary /path/to/custom/duckiematrix.x86_64
dts matrix run --renderer-editor
dts matrix run --renew-authorization
```

For Editor Play mode, generate the approved public trust source before opening Unity, start the editor session command, and copy its local endpoint into AppLauncher's `editorOnlyDtsSessionEndpoint`. Start with the `init` scene. Alternatively set `DTM_DTS_SESSION_URL` in Unity's environment. Keep DTS running. An official signed custom release uses normal permission; an unsigned custom build uses developer permission. Authenticated DTS source overrides still require their separate `develop:dts` grant; an expired native developer context cannot continue issuing Renderer proofs.

The selected profile's `databases/renderer-sessions` directory contains a private Ed25519 launch key and separate normal/developer grant files, scoped by issuer, identity fingerprint, and computer. The key persists to support offline relaunches; simultaneous launches serialize key initialization so they share the same key. **Do not share it or the cache**. POSIX files are private (`0600`); on Windows keep the profile/cache under the user's private directory and restrict its ACL. Runtime caches never contain the raw identity token. Invalid, oversized, or symlinked cache files fail explicitly. `--renew-authorization` replaces the grant when the key is valid. To recover an invalid key, stop DTS/Renderer sessions and remove only the matching `.pem`, `-use.json`, and `-develop.json` files, then authorize online again. Removing a key alone leaves incompatible cached grants. Removing caches does not revoke already issued Hub permissions.

Official Renderer installations verify the artifact signature, complete file inventory, IL2CPP backend, version/platform/entrypoint, and the exact compiled public-key map. Downloads are staged, safely extracted, verified, and selected atomically; a bad update preserves the previous installation. Optional remote checksums are hints, never signing authority. Offline update checks may use only a verified installed release.

Native players also verify their own inventory and OS fingerprint. WSL-to-Windows launches keep the registered WSL fingerprint and separately attest the native Windows MachineGuid. Linux containers mount the host machine ID read-only and use host networking. FEX must expose the host machine ID and loopback to the emulated Renderer. WebGL verifies the signed inventory and DTS-attested bundle, but cannot independently identify the computer or attest executing browser bytes. Remote browsing does not gain access to another computer's loopback DTS session. These are practical tamper-resistance measures, not process/hardware attestation; real WSL/FEX/container/browser/OS tests remain release gates.

Both DTS and Unity builds must pin **the same** `DTM_RELEASE_PUBLIC_KEY` and exact `DTM_RENDERER_PUBLIC_KEYS` production/staging map. These three keys must be distinct from all DTS wheel/command/developer keys. Each Hub mounts only its own Renderer private key as `/run/secrets/duckiematrix_renderer.key`; Renderer builders and DTS builders receive public keys only. Rotation requires coordinated Hub, DTS, and Renderer releases. See the [Renderer build and deployment guide](https://github.com/duckietown/duckiematrix#protected-release-builds) for protected disposable Unity runners, preparation, signing, and verified publication. The guide separates compilation-only source testing from native runtime testing and preserves the manual Unity `Release` build followed by `dts matrix devel release`. The publisher signs a temporary ship-ready copy with a publisher-only artifact key; it does not modify the original Unity build or give private keys to Unity.

## Automated releases

The [Automated Release workflow](.github/workflows/release.yml) bumps semantic versions and dispatches [Upload Python Package](.github/workflows/python-publish.yml) for the resulting release tag.

In **Actions**, select **Automated Release**, then **Run workflow**, and choose:

- `patch` for bug fixes, for example 6.3.0 to 6.3.1.
- `minor` for new features, for example 6.3.0 to 6.4.0.
- `major` for breaking changes, for example 6.3.0 to 7.0.0.

The workflow updates version numbers, creates Git tags, generates a changelog and GitHub release, then dispatches native wheel build, repair, signing, testing, and verified PyPI publication.

Each DTS release uses matching Hub endpoints and signing keys, [signed artifacts for all four command channels](#signed-command-delivery), the [complete native wheel matrix](#signed-native-releases), and [signed Renderer artifacts](#duckiematrix-renderer-authorization). Keep these components compatible when publishing updates. The GitHub release workflow publishes DTS wheels; Hub deployment and Renderer publication are managed separately.

## Signed native releases

Release wheels must cover each [supported CPython minor](README.md#supported-runtimes) on:

| System | Architectures |
| --- | --- |
| Linux (manylinux/glibc) | x86-64, ARM64 |
| macOS | Intel, Apple Silicon |
| Windows | x86-64 |

All 15 combinations must be present before publication. Alpine/musl, Windows ARM64/32-bit, alternative Python implementations, and other Python minors are not official-wheel targets.

The protected modules have no `.py`, `.pyc`, `.pyx`, or generated C fallback in the wheel. The native bootstrap embeds the release, command, approved developer, Renderer artifact, and Renderer permission verification public keys, verifies the signed manifest before loading DTS, and checks again at delegation and command dispatch. The manifest covers the final native binaries, remaining package sources, embedded commands, assets, and immutable wheel metadata. Normal installer metadata and generated bytecode caches are not signed.

Use a **dedicated Ed25519 release-signing key**, not Hub token keys. Once, outside the repository, generate the key pair using Python 3.12 in an isolated build environment:

```shell
python3.12 -m venv /path/to/release-venv
make release-deps PYTHON=/path/to/release-venv/bin/python
/path/to/release-venv/bin/python tools/release.py keygen \
    --private-key /secure/location/dts-release-private.pem \
    --public-key /secure/location/dts-release-public.hex
```

The destination directories must already exist. The key generator rejects existing files and paths inside Git repositories; on POSIX it creates the private file with mode `0600`. On Windows, restrict its ACL to the signing operator. Store the private PEM in a secret manager and never commit it, add it to build artifacts, or pass it to CircleCI's environment-dumping jobs.

Configure GitHub Actions:

| Setting | Kind | Value |
| --- | --- | --- |
| `DTS_RELEASE_PUBLIC_KEY` | Repository variable | 64 lowercase hexadecimal characters from the public-key file |
| `DTS_COMMANDS_PUBLIC_KEY` | Repository variable | Separate command-signing public key, also 64 lowercase hexadecimal characters |
| `DTS_DEVELOPER_PUBLIC_KEYS` | Repository variable | Exact production/staging issuer map with separate developer public keys, as described above |
| `DTM_RELEASE_PUBLIC_KEY` | Repository variable | Separate Renderer artifact public key, matching Unity releases |
| `DTM_RENDERER_PUBLIC_KEYS` | Repository variable | Exact production/staging issuer map with separate Renderer permission public keys |
| `DTS_RELEASE_SIGNING_KEY` | Repository secret | Complete unencrypted Ed25519 private PEM, preserving newlines |
| `PYPI_USERNAME` | Existing repository secret | PyPI token username, normally `__token__` |
| `PYPI_TOKEN` | Existing repository secret | PyPI upload token |

The public key is required at **build time**; no runtime signing secret or public-key override is supported. A missing/invalid key or compiler is a build error, not a reason to produce a pure-Python wheel. Key rotation requires rebuilding the wheels with the new embedded public key and signing them with the matching private key.

The **Upload Python Package** workflow builds and repairs platform wheels with cibuildwheel, then signs their final bytes in a separate job. Only that job receives the release private key. It installs and tests each signed wheel on its matching OS/architecture/Python before allowing publication. The **Automated Release** workflow explicitly dispatches it after creating the GitHub release: releases made with `GITHUB_TOKEN` do not otherwise trigger a second workflow. You can also publish a GitHub release manually or dispatch **Upload Python Package** with an existing tag.

The Makefile no longer publishes source distributions:

```shell
export DTS_RELEASE_PUBLIC_KEY="$(cat /secure/location/dts-release-public.hex)"
export DTS_COMMANDS_PUBLIC_KEY="$(cat /secure/location/dts-commands-public.hex)"
export DTS_DEVELOPER_PUBLIC_KEYS='{"https://hub.duckietown.com":"<production-developer-public-key>","https://staging-hub.duckietown.com":"<staging-developer-public-key>"}'
export DTM_RELEASE_PUBLIC_KEY="$(cat /secure/location/renderer-release-public.hex)"
export DTM_RENDERER_PUBLIC_KEYS='{"https://hub.duckietown.com":"<production-renderer-public-key>","https://staging-hub.duckietown.com":"<staging-renderer-public-key>"}'
make release-wheels PYTHON=/path/to/release-venv/bin/python WHEELHOUSE=wheelhouse
export DTS_RELEASE_SIGNING_KEY_FILE=/secure/location/dts-release-private.pem
make release-seal PYTHON=/path/to/release-venv/bin/python WHEELHOUSE=wheelhouse
```

Local cibuildwheel builds only platforms supported by the build host; use the CI matrix to produce the complete cross-platform release. Sign **after** auditwheel/delocate repair; modifying a sealed wheel invalidates its signature. Linux cibuildwheel builds require Docker or Podman, macOS requires Xcode tools, and Windows requires MSVC. Run cibuildwheel itself with Python 3.11 or 3.12, even when building Python 3.10 wheels.

Download the complete `signed-wheels` CI artifact into a new `dist` directory when using manual upload. Then:

```shell
make release-verify PYTHON=/path/to/release-venv/bin/python DIST=dist
make upload PYTHON=/path/to/release-venv/bin/python DIST=dist
```

`make upload` verifies signatures, native entry points, Python metadata, wheel RECORDs, the release version, and all 15 targets before invoking Twine. It rejects unsigned/universal wheels, source archives, duplicate targets, and stale files. Keep `TWINE_USERNAME`/`TWINE_PASSWORD` in the usual secure publishing environment. `make bump-upload` deliberately stops with migration guidance: one workstation cannot build and publish all supported operating systems. `make bump` still bumps and pushes as before; it does not create a GitHub release or publish wheels.

Native profile environments must match the installed DTS interpreter's Python minor version, OS, and architecture. An incompatible existing or custom `DTSHELL_VENV_DIR` produces an actionable error instead of attempting to load a different ABI. Reset/recreate an old profile environment with the installed interpreter after changing Python versions.

This is tamper resistance for ordinary installations, not independent local attestation. The wheel manifest does not authenticate older clients, third-party dependencies, installer-generated bytecode, entry-point scripts, or in-memory Python monkeypatching. External command snapshots use their own signatures, inventory checks, and source loader, as described below. Protected-server/private-registry checks are still needed against determined users. `daffy` remains plan-free in an intact official installation.

## Signed command delivery

All normal external command sets in official builds, including `daffy` and custom sets, must be signed by the approved **separate Ed25519 command-signing key**. Ordinary plan eligibility, staff/superuser status, a repository URL, and `DTHUB_HOST` cannot select a verification key or permit unsigned command code. The wheel-owned embedded set is protected by the wheel signature instead. The only supported unsigned exception in the compiled command loader is an explicit `DTSHELL_COMMANDS` checkout approved by [authenticated developer mode](#authenticated-developer-mode). Cached developer authorization without requested overrides does not exempt normal command sets. The explicit Python source-development workflow above is unchanged.

Generate the command key outside every checkout:

```shell
/path/to/release-venv/bin/python tools/commands_release.py keygen \
    --private-key /secure/location/dts-commands-private.pem \
    --public-key /secure/location/dts-commands-public.hex
```

Keep the command private key out of the DTS wheel-building and wheel-signing jobs. Configure the matching public key in both repositories; it is compiled into the native bootstrap and cannot be overridden at runtime. Changing it requires rebuilding the DTS wheels.

The commands repository's **Publish signed DTS commands** workflow requires:

| Setting | Location | Purpose |
| --- | --- | --- |
| `DTS_COMMANDS_PUBLIC_KEY` | Commands repository variable | Matches the key embedded in DTS |
| `DTS_COMMAND_SIGNING_TOOLS_REF` | Commands repository variable | Approved, full 40-character commit SHA in this shell repository |
| `DTS_COMMANDS_SIGNING_KEY` | Protected `command-signing` environment secret | Complete command private PEM, preserving newlines |
| `DTS_SIGNING_TOOLS_READ_TOKEN` | Optional commands repository secret | Read-only access to the signing-tools repository if it becomes private |

Protect the signing environment with required reviewers and permitted release branches. Restrict workflow edits and release publishing to approved maintainers; developers who can read repositories should not automatically receive signing secrets. Do not expose the command key to pull-request jobs, source hooks, or CircleCI jobs that print their environment.

When publishing command-channel updates:

1. Commit the shell signing tools and set their approved SHA in the commands repository. Configure the separate command key and protected environment.
2. Make the publishing workflow available on the default branch and all four automatic-update branches: `ente`, `ente-staging`, `daffy`, and `daffy-staging`. Manual dispatch can publish any of those branch checkouts without changing branches on developers' machines.
3. Publish signed artifacts for **all four channels**, especially `daffy`, before publishing a DTS version that requires them. Each channel also publishes a safe signed fixture used by native DTS CI tests, without exposing the private key to those test jobs.
4. Keep `DTS_COMMANDS_PUBLIC_KEY` in the shell repository consistent with the command signer, and publish compatible native DTS wheels when the key or client compatibility changes. Retain public artifact delivery for ordinary `daffy` users if authoring repositories later become private.

The native-wheel workflow refuses to proceed until it has verified signed metadata and archives for all four channels against the proposed DTS version. The read-only preflight can also be run locally:

```shell
/path/to/release-venv/bin/python tools/commands_release.py ready --version 6.3.0
```

For local artifact production, from a clean committed commands checkout:

```shell
export DTS_COMMANDS_PUBLIC_KEY="$(cat /secure/location/dts-commands-public.hex)"
export DTS_COMMANDS_SIGNING_KEY_FILE=/secure/location/dts-commands-private.pem
/path/to/release-venv/bin/python tools/commands_release.py build \
    /path/to/duckietown-shell-commands /new/empty/artifact-directory \
    --repository github.com/duckietown/duckietown-shell-commands \
    --branch ente --distribution ente --revision 42
/path/to/release-venv/bin/python tools/commands_release.py verify /new/empty/artifact-directory
```

The signer reads tracked regular files, including executable file modes, without importing configuration or initialization code. Configuration must declare one literal `VERSION` string and literal minimum/maximum shell-version tuples. Dependencies normally come from `__command_set__/requirements.txt`; all included dependency/constraint files and assets are covered by the complete inventory. Links, submodules, bytecode, duplicate/case-colliding paths, and unsafe paths are rejected. The signed manifest also binds repository, channel, allowed distribution(s), command version, shell compatibility, commit, publication time, monotonically increasing revision, archive length, and archive checksum.

`publish` uses GitHub CLI with authorized release-writing credentials. It uploads the content-addressed archive before replacing the single signed channel envelope. The deterministic channel tag is printed/calculated by `release_tag()` in [artifacts.py](lib/dt_shell/commands/artifacts.py). Do not reset the workflow run-number sequence or reuse a revision for different content. To intentionally restore old source, publish it as a new higher revision rather than serving a lower revision.

Official clients never clone or execute legacy cached checkouts. They verify metadata and every file, stage extraction, and atomically select a separate generation under the command set's `.dts-signed` cache. Old generations are retained so running processes are not switched underneath their imports. An unsigned legacy checkout is left untouched, outside the import path, while the first signed snapshot is downloaded. Command metadata is checked before any configuration hook runs, and dependency installation and execution recheck integrity. Python modules compile directly from verified bytes; unsigned `.pyc` files are neither trusted nor generated in signed snapshots.

Known lower revisions and reused revisions with different content are rejected. This is local rollback resistance, not a trusted hardware counter: a user who controls the whole cache and profile state can erase the recorded history. Signed command snapshots do not have an age-based expiration, so `daffy` can continue offline using an intact verified cache. A network failure during an automatic metadata check emits a warning before using that cache. First installation and explicit `dts update` fail explicitly when delivery is unavailable; signature, inventory, compatibility, or rollback failures never fall back to unsigned code. The separate `ente` plan grant retains its normal expiry and offline rules.

For cache integrity errors, stop DTS and quarantine only the affected command set's `.dts-signed` directory, preserving the rest of the profile and its credentials. The next normal launch downloads a fresh verified snapshot. Do not delete the entire shell/profile directory or disable verification. Ordinary PyPI reinstalling repairs the wheel, not a modified external command cache.

Command delivery uses public GitHub release assets. Command-set signing is separate from the Renderer authorization described above; neither adds private-repository download credentials or Docker image download restrictions.

## Use local challenge server

Use the env variable `DTSERVER` to work on a local server:

```shell
export DTSERVER=http://localhost:6544/
```

## Plan authorization for `ente`

The [README defines eligibility and the grace deadline](README.md#plans-and-access) and documents [status, computer registration, transfers, and offline access](README.md#plan-and-computer-management). This section describes the authorization protocol and local Hub development.

DTS obtains a signed, non-renewable authorization for `ente` from `/api/v1/auth/token/ente/` and caches it per profile, identity token, and Hub. The grant is bound to the user, Hub, and registered computer. Its signed expiration is the earlier of 24 hours and any recorded expiration of the plan granting access. A plan-free grace grant instead has `base_plan: null`, a signed `plan_grace_until`, and expiration bounded by the enforcement deadline; the Hub uses its own UTC clock and stops new grace issuance at that exact instant. No scheduler or environment-variable bypass is involved. Cached grace is rejected at the cutoff even while offline. Redeemed seats for the 'Institutional User' plan use their parent plan's expiration; the 'Instructor' plan does not extend it. Qualifying plan flags without a recorded validity period, including enrollment in the free 'Independent User' plan, retain daily authorization with no recorded plan expiration and are not capped at the grace deadline. The cached grant is checked locally and refreshed on demand after at most 24 hours, or earlier if its signed expiration is reached.

To use local code with a development HTTPS Hub:

```shell
DTSHELL_LIB=/path/to/duckietown-shell/lib \
DTSHELL_COMMANDS=/path/to/duckietown-shell-commands \
DTHUB_HOST=localhost:8443 \
PYTHONPATH=/path/to/duckietown-shell/lib \
/path/to/source-venv/bin/python -m dt_shell_cli.dts devel info
```

`DTHUB_HOST` is a hostname with an optional port; `DTHUB_URL` overrides the full URL used by the shell. A development Hub using different signing keys requires an isolated client configured to trust its development public keys. Self-signed HTTPS certificates must also be trusted; do not disable certificate verification.

This is an official-client policy, not tamper-proof anti-sharing. Machine IDs can be spoofed or cloned, and public clients can be modified to bypass local checks. It also does not stop already-running/downloaded robot images. Enforcing access against hostile clients requires a protected server or image registry.
