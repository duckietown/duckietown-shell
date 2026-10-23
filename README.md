[![CircleCI](https://circleci.com/gh/duckietown/duckietown-shell.svg?style=shield)](https://circleci.com/gh/duckietown/duckietown-shell) [![Docker Hub](https://img.shields.io/docker/pulls/duckietown/duckietown-shell.svg)](https://hub.docker.com/r/duckietown/duckietown-shell/)

# Duckietown Shell

*Duckietown Shell* provides a command-line interface for Duckietown. Most functionality runs in Docker containers; DTS provides a concise interface to those operations.

DTS is available on [PyPI](https://pypi.org/project/duckietown-shell/) as signed native wheels and installs command sets through verified updates.

## Supported runtimes

**DTS requires CPython 3.10, 3.11, or 3.12.** Native release wheels support Linux x86-64/ARM64, macOS Intel/Apple Silicon, and Windows x86-64. Official releases have no source-distribution or universal-wheel fallback. Installation examples select Python 3.12 explicitly; that interpreter must already be installed:

```shell
pipx install --python python3.12 duckietown-shell
```

## Plans and access

From **1 February 2027 at 00:00 UTC**, the 'ente' distribution requires the free 'Independent User' plan or an active 'Institutional User' plan. Until that deadline, active accounts without a qualifying plan have temporary access to 'ente', including Duckiematrix, through signed grace permissions. This includes accounts with only the 'Instructor' add-on or expired plans. Authentication, the one-computer limit, transfers, and anti-tamper checks still apply; cached grace permissions cannot outlast the deadline. The supplemental 'Instructor' plan alone is insufficient after the deadline; staff or superusers remain exempt from the plan and one-computer limit.

The same policy applies to 'ente-staging'. The 'daffy' and 'daffy-staging' distributions remain plan-free, and ordinary Hub identity-token generation is not gated on a plan. Core token, profile, and command management commands remain available. See [plan and computer management](#plan-and-computer-management) for status, transfers, and offline access.

Official builds authenticate every external command set. `dts update` downloads verified, signed command snapshots rather than executing a mutable Git checkout. This includes `daffy`. Unsigned third-party command repositories need an approved signed release. Publishing, cache migration, and recovery are covered in [signed command delivery](devel.md#signed-command-delivery).

Duckiematrix is exclusive to 'ente'. Use DTS **6.3.1 or newer** with matching signed commands. The Engine and Renderer require separate signed permissions, including Engine-only and no-renderer launches. Keep each launching DTS command running. Only DTS contacts the Hub; neither component receives your identity token. Valid cached permissions allow offline relaunches until their original expiry, at most 24 hours for normal use or one hour for staff/superuser development, shortened by known identity/plan expiry and the grace deadline where applicable. Ordinary DTS 'ente' authorization must also remain valid. See [Engine authorization](devel.md#duckiematrix-engine-authorization) and [Renderer authorization](devel.md#duckiematrix-renderer-authorization) for source/custom-image development and recovery.

The Duckietown Viewer is also exclusive to Ente. Its desktop and browser apps use a separate signed Viewer
permission with the same plan, grace, computer and bounded-offline rules. Keep
the launching DTS process running. Direct app/container/URL launches are not
authorization exceptions; source work requires its own staff/superuser Viewer
developer permission. Ordinary Daffy workflows remain plan-free.
See [Viewer authorization](devel.md#duckietown-viewer-authorization) for developer
preparation, signed releases, host delegation and coordinated rollout.

## Prerequisites

In addition to a supported CPython interpreter, host development and robot commands use:

1. [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git/)
2. [Git LFS](https://git-lfs.github.com/) (for building and working with the docs only)
3. [Docker](https://docs.docker.com/get-docker/)

### Docker Prerequisites

**Note**: You need to add yourself to the `docker` group:

```shell
sudo adduser `whoami` docker
```

**Important**: after you do that, you must *log out and in* to have the group change take effect.

#### Docker on MacOS

By default, Docker uses the OS X keychain to store credentials, but this is not good.

Edit `~/.docker/config.json` and remove all references to an "osxkeychain".

Then run `docker login` again.

Then you should see an `auth` entry of the type:

```json
{
    "auths": {
        "https://index.docker.io/v1/": {
            "auth": "mXXXXXXXXXXXXXXXXXXXXXXXXXX"
        }
    },
}
```

## Installing the Duckietown Shell

### Installation on Ubuntu

Ubuntu 22.04 and later are the supported Ubuntu releases. A supported CPython interpreter is required independently of the operating-system version.

#### Install using [pipx](https://pipx.pypa.io/stable/installation/)

Install `pipx`:

```shell
sudo apt install -y pipx
pipx ensurepath
```

Install the `duckietown-shell`:

```shell
pipx install --python python3.12 duckietown-shell
```

To upgrade to the latest version of `duckietown-shell`:

```shell
pipx upgrade duckietown-shell
```

#### Install using `pip`

An isolated virtual environment is the alternative to pipx:

```shell
python3.12 -m venv "$HOME/.venvs/duckietown-shell"
. "$HOME/.venvs/duckietown-shell/bin/activate"
python -m pip install --upgrade duckietown-shell
```

The environment must be activated before invoking its `dts` executable.

#### Testing the Installation on Ubuntu

Typing

```shell
which dts
```

resolves to the pipx executable under `$HOME/.local/bin`, or to the executable in the active virtual environment.

For pipx installations, `$HOME/.local/bin` must be on the shell path:

```shell
export PATH="$HOME/.local/bin:$PATH"
```

This setting belongs in `~/.bashrc` for Bash, or the corresponding shell initialization file.

### Older Ubuntu versions

Use a supported CPython interpreter and an OS compatible with the published manylinux wheel. Unsupported Python or platform combinations cannot build an official release from a source archive.

### Duckietown Shell on MacOS X

#### Using `pipx` to install

Install `pipx`:

(see https://pipx.pypa.io/stable/installation/ for more details)

```shell
brew install python@3.12 pipx
pipx ensurepath
sudo pipx ensurepath --global # optional to allow pipx actions in global scope. See "Global installation" section below.
```

Install the `duckietown-shell`:

```shell
pipx install --python python3.12 duckietown-shell
```

To upgrade to the latest version of `duckietown-shell`:

```shell
pipx upgrade duckietown-shell
```

#### Using `pip` to install

An isolated virtual environment is the alternative to pipx:

**Note: Never use `sudo pip install` to install `duckietown-shell`.**

```shell
python3.12 -m venv "$HOME/.venvs/duckietown-shell"
. "$HOME/.venvs/duckietown-shell/bin/activate"
python -m pip install --upgrade duckietown-shell
```

The environment must be activated before invoking its `dts` executable.

#### Testing the Installation

Typing

```shell
which dts
```

should output the path to the `dts` executable. This path can vary based on your Python setup. If it is not found, you may need to add something to your shell path.

### Installation on Windows

Install 64-bit CPython 3.10, 3.11, or 3.12, Git, and Docker Desktop. In PowerShell:

```powershell
py -3.12 -m pip install --user pipx
py -3.12 -m pipx ensurepath
py -3.12 -m pipx install --python (py -3.12 -c "import sys; print(sys.executable)") duckietown-shell
```

Open a new terminal if needed, then run `dts version`. The shell supports Windows startup, computer identification, and profile virtual environments; individual robot/development commands may additionally require Linux-specific tools or WSL. Windows ARM64 and 32-bit Python are not release-wheel targets.

### Legacy Docker installation

The existing Shell Dockerfiles and historical images are not the native release path. The main Dockerfile still uses an Alpine/Python 2-era base, which does not match the supported CPython/glibc wheel targets. DTS normally runs on the host; use the pipx or virtual-environment installation instructions above. Renderer container launching is a separate workflow with host-ID and networking requirements described in [devel.md](devel.md#duckiematrix-renderer-authorization).

## Testing Duckietown shell

Installation and command availability can be checked with:

```shell
dts version
dts help
```

Update installed command sets with:

```shell
dts update
```

First installation and explicit updates require available signed command artifacts. Integrity failures must be handled with the targeted [command-cache recovery procedure](devel.md#signed-command-delivery), not by deleting profiles or bypassing verification. Reinstalling DTS repairs its wheel, not a modified external command cache.

-----------------------

The following sections describe profile setup and common commands.

## Non-interactive setup

The Duckietown Shell can be preconfigured without interactive prompts by setting a few environment variables before the first run:

- `DTSHELL_PROFILE` – name of the profile to use or create.
- `DTSHELL_DISTRO` – distribution to associate with the profile.
- `DTSHELL_TOKEN` or `DUCKIETOWN_TOKEN` – a Duckietown authentication token.

With these variables exported, running `dts` will not ask for input during the initial configuration, which is useful for scripted or containerized setups.

Official compiled releases accept `DTSHELL_LIB`, `DTSHELL_COMMANDS`, and `DTSHELL_PYTHONPATH` only after verifying a separate staff/superuser grant through [authenticated developer mode](devel.md#authenticated-developer-mode). The [source-development workflow](devel.md#source-development) runs the checkout explicitly and is not an attested native release.

## Compile one of the (legacy) "Duckumentation" (books)

To compile one of the books (e.g., docs-duckumentation, but there are many others):

```shell
git clone https://github.com/duckietown/docs-duckumentation.git
cd docs-duckumentation
git submodule init
git submodule update
dts docs build
```

There is an incremental build system. To clean and run from scratch:

```shell
dts docs clean
dts docs build
```

The new [Duckietown documentation infrastructure](https://docs.duckietown.com/ente/devmanual-docs/intro.html) requires only the command

```shell
dts docs build
```

to compile a book locally.

## Authenticate a Duckietown Token

Normal identity tokens are generated through [Duckietown Hub](https://hub.duckietown.com/token) without requiring a plan. 'ente' plan/device permissions and DTS/Renderer/Viewer developer permissions are issued separately; they must not replace the identity token stored by `dts tok set`.

Run the command `dts tok set` to set the Duckietown authentication token:

```shell
dts tok set
```

Instructions will guide you, and you will be prompted for the token.

If you already know the token, then you can use:

```shell
dts tok set dt2-YOUR-TOKEN
```

### Verifying that a token is valid

To verify that a token is valid, you can use:

```shell
dts tok verify dt2-TOKEN-TO-VERIFY
```

This exits with 0 if the token is valid, and writes on standard output the following json:

```shell
{"uid": 3, "expiration": "2018-09-23"}
```

which means that the user is identified as uid 3 until the given expiration date.

## Plan and computer management

The [access policy](#plans-and-access) determines whether an account can use 'ente'. Each account that is neither staff nor a superuser can register one DTS computer. Identity-token or cache copies do not authorize a different computer in the supported client. The fingerprint hashes the Linux machine ID, macOS platform UUID, or Windows MachineGuid; VMs, separate OS installations, and reinstalls may have different identities. No raw machine ID is sent to Hub.

[Duckietown Workspaces](https://github.com/duckietown/workspace#one-computer-for-the-host-and-its-workspaces) inherit the initializing host OS's identity through read-only machine-ID mounts. Host DTS and its local Workspaces therefore share one computer registration, including after container rebuilds; host DTS is not required to initialize the identity. Initialize from the same host OS used by host DTS, not a different VM or WSL installation. Recreate older Workspace containers to apply the mounts. If an account was registered with an older container-specific identity, use `dts plan transfer` once from the updated Workspace or matching host. Profiles, tokens, and permission caches remain separate and must not be copied between computers.

Plan/device authorizations are cached for at most 24 hours, shortened by a recorded qualifying-plan expiration or the grace deadline. Without a valid cached grant, an unavailable Hub blocks 'ente' commands but does not block 'daffy' commands.

These commands use the selected profile's ordinary DT2 identity token and do not require an existing 'ente' authorization:

```shell
dts plan status
dts plan transfer
```

Status distinguishes:

- **Account plans**: all plans listed on the account, including add-ons.
- **Plan granting 'ente' access**: the qualifying 'Independent User' plan or 'Institutional User' plan.
- **Plan requirement for 'ente'**: met, exempt, or temporary grace with the enforcement date. Temporary access is not labeled as meeting the plan requirement.

Status also shows any recorded plan expiration, the registered computer, the latest expiry among its issued authorizations, and any pending transfer. Eligibility is not a promise that the current computer can obtain a grant during a pending transfer. User-facing dates use a readable UTC format, such as `10 October 2026 at 14:38 UTC`, with seconds when relevant; machine-readable API dates remain ISO 8601. DTS warns about the grace deadline when fetching a fresh grace grant, and about a recorded plan expiration within three days when fetching a fresh plan grant.

Run `dts plan transfer` on the replacement computer:

- An initial registration or immediate transfer is reported as registered now; run an 'ente' command to request authorization.
- On the already-registered computer with no pending transfer, the command confirms that no transfer is needed.
- A scheduled transfer shows when authorization can next be requested. Hub pauses new authorizations until every old grant expires, for at most 24 hours, then activates the replacement.

The transfer availability time is not a new grant's expiration. Transfer requests do not issue authorizations or change existing token expiry dates. Switching credentials or profiles does not reset this per-user registration.

-----------------------

## Duckiebot setup

### Command for flashing SD card

This command will install DuckieOS on the SD-card:

```shell
dts init_sd_card
```

-----------------------

### Command for starting ROS GUIs

This command will start the ROS GUI container:

```shell
dts start_gui_tools <DUCKIEBOT_NAME_GOES_HERE>
```

-----------------------

### Command for calibrating the Duckiebot

This command will run the Duckiebot calibration procedure:

```shell
dts calibrate_duckiebot <DUCKIEBOT_NAME_GOES_HERE>
```

## Advanced configuration

By default, Duckietown Shell uses the folder `~/dt-data` for storing log data and other cache data.

Alternatively, use the `--dt-data` argument to choose a different folder:

```shell
dts logs --dt-data ![dir] ![command]
```

The directory can also be specified using the environment variable `DT_DATA`:

```shell
DT_DATA=/tmp/data dts logs summary
```

## Uninstalling or resetting

For a pipx installation, uninstalling the package uses:

```shell
pipx uninstall duckietown-shell
```

For a pip installation, `python -m pip uninstall duckietown-shell` must use the same virtual environment that installed it.

A complete local reset removes profiles, stored tokens, Docker credentials, and cached grants. Back up required credentials first. This does not clear Hub-side computer registration, revoke issued permissions, or replace `dts plan transfer`. Cache integrity recovery normally needs only the affected cache, not a full reset.

On Ubuntu/Mac, for example, this could be done with:

```shell
rm -rf ~/.duckietown/shell
```

-----------------------

## Developing Duckietown Shell

Development and release procedures are maintained in the [developer guide](devel.md):

- [Source setup](devel.md#source-development), [local commands development](devel.md#local-commands-development), and [VS Code debugging](devel.md#debugging-with-visual-studio-code).
- [Development container](devel.md#development-container) configuration and environment handling.
- [Authenticated developer mode](devel.md#authenticated-developer-mode) for staff/superuser source overrides in official installations.
- [Automated releases](devel.md#automated-releases), [native wheel signing](devel.md#signed-native-releases), and [signed command delivery](devel.md#signed-command-delivery).
