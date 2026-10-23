"""Build ephemeral native trust and exercise the real backend/desktop guard locally.

No Hub credentials, production signing keys, Docker daemon or robot are used.
"""

import argparse
import asyncio
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import aiohttp
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
from dt_shell import renderer, viewer
import dt_shell_device
from dt_shell_tests.test_renderer import IDENTITY, ISSUERS, UID, public
from dt_shell_tests.test_viewer import ViewerFixture


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(f"Build failed ({result.returncode}):\n{result.stdout[-10000:]}")


def prepare(directory, backend):
    environment = os.environ.copy()
    authorities = {}
    for name in ("DTS_RELEASE_PUBLIC_KEY", "DTS_COMMANDS_PUBLIC_KEY", "DTM_RELEASE_PUBLIC_KEY", "DTV_RELEASE_PUBLIC_KEY"):
        authorities[name] = Ed25519PrivateKey.generate()
        environment[name] = public(authorities[name])
    for name in ("DTS_DEVELOPER_PUBLIC_KEYS", "DTM_RENDERER_PUBLIC_KEYS", "DTV_AUTH_PUBLIC_KEYS"):
        authorities[name] = {issuer: Ed25519PrivateKey.generate() for issuer in ISSUERS}
        environment[name] = json.dumps({issuer: public(key) for issuer, key in authorities[name].items()})
    run([
        sys.executable, "tools/viewer_guard/setup.py", "build", "--build-base", str(directory / "guard-build"),
        "bdist_wheel", "--bdist-dir", str(directory / "guard-bdist"), "--dist-dir", str(directory / "wheels"),
    ], cwd=ROOT, env=environment)
    wheel, = (directory / "wheels").glob("*.whl")
    site = directory / "native-site"
    run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(site), str(wheel)], cwd=ROOT, env=environment)
    run([
        sys.executable, "-m", "PyInstaller", "--clean", "--onefile", "--name", "viewer-guard",
        "--paths", str(site), "--additional-hooks-dir", str(ROOT / "tools/viewer_guard/hooks"),
        "--distpath", str(directory / "desktop/bin"), "--workpath", str(directory / "freeze-build"),
        "--specpath", str(directory), str(ROOT / "tools/viewer_guard/desktop.py"),
    ], cwd=ROOT, env=environment)
    payload = directory / "backend"
    shutil.copytree(
        backend / "packages", payload / "packages",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so", "*.pyd"),
    )
    run([
        sys.executable, str(backend / "tools/compile_backend.py"),
        "build_ext", "--inplace", "--build-temp", str(directory / "backend-build"),
    ], cwd=payload, env=environment)
    marker = directory / "app-imported"
    app = payload / "packages/dt_app_empty_viewer/app.py"
    app.write_text(app.read_text() + f"\nPath({str(marker)!r}).write_text('authorized app import')\n")
    spec = importlib.util.spec_from_file_location("native_viewer_release_tools", ROOT / "tools/viewer_release.py")
    tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools)
    fixture = ViewerFixture(directory)
    fixture.keys = authorities["DTV_AUTH_PUBLIC_KEYS"]
    fixture.issuers = {issuer: public(key) for issuer, key in fixture.keys.items()}
    fixture.release_key = authorities["DTV_RELEASE_PUBLIC_KEY"]
    fixture.release_public = public(fixture.release_key)
    family = family_name()
    if __import__("platform").machine().lower() in ("arm64", "aarch64"):
        family += "-arm64"
    executable = "viewer-guard.exe" if os.name == "nt" else "viewer-guard"
    with patch.dict(os.environ, environment):
        desktop = tools.seal(
            directory / "desktop", version="1.2.3", platform=family,
            entrypoint="bin/" + executable, kind="desktop", key=fixture.release_key,
        )
        release = tools.seal(
            payload, version="1.2.3", platform=family,
            entrypoint="packages/duckietown_viewer", kind="backend", key=fixture.release_key,
        )
    return fixture, site, payload, marker, desktop, release, executable


async def exercise(directory, args, prepared):
    fixture, site, payload, marker, desktop, release, executable = prepared
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}/app/"
    device = dt_shell_device.get_device_id()
    context, tickets = viewer.new_context(
        app="empty_viewer", endpoint=endpoint, backend=release["sha256"], backend_image="1" * 64,
        desktop=desktop["sha256"], desktop_version="1.2.3", desktop_device=device,
    )
    shell = SimpleNamespace(profile=SimpleNamespace(
        distro=SimpleNamespace(name="ente"),
        database=lambda name: SimpleNamespace(yaml=str(directory / "profile" / (name + ".yaml"))),
    ))
    children = []
    logs = []
    session = None
    mocks = contextlib.ExitStack()
    environment = {
        **os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MODULE": "empty_viewer",
        "DT_VIEWER_BACKEND_PORT": str(port), "VEHICLE_NAME": "viewer-test",
        "PYTHONPATH": os.pathsep.join((str(site), str(payload / "packages"), str(args.common))),
    }
    environment.pop("DT_VIEWER_HANDOFF", None)

    async def backend_process(env):
        log_path = directory / f"backend-{len(children)}.log"
        log = log_path.open("wb")
        logs.append(log)
        process = await asyncio.create_subprocess_exec(
            str(args.backend_python), "-c", "from duckietown_viewer.main import main; main()",
            cwd=payload / "packages/duckietown_viewer", env=env, stdout=log, stderr=log,
        )
        children.append(process)
        return process, log_path

    try:
        denied, denied_log = await backend_process(environment)
        assert await asyncio.wait_for(denied.wait(), 15) != 0
        assert "requires a live authorized DTS session" in denied_log.read_text()
        assert not marker.exists(), "An unauthorized app module was imported."

        def issue(session):
            return fixture.grant(session.launch_key, app=session.app, changes={"device_id": device})

        for mock in (
            patch("dt_shell.viewer._trust", return_value=(fixture.release_public, fixture.issuers)),
            patch("dt_shell.renderer._identity", return_value=(IDENTITY, SimpleNamespace(uid=UID))),
            patch("dt_shell.renderer.DTHUB_URL", ISSUERS[0]),
            patch.object(viewer.ViewerSession, "_request", new=issue),
        ):
            mocks.enter_context(mock)
        session = viewer.ViewerSession(shell, app="empty_viewer", context=context, os_family=family_name())
        handoff = directory / "backend.json"
        desktop_handoff = directory / "desktop.json"
        session.write_handoff(handoff, consumer="backend", ticket=tickets["ready"])
        session.write_handoff(desktop_handoff, consumer="desktop", ticket=tickets["desktop"])
        environment["DT_VIEWER_HANDOFF"] = str(handoff)
        wrong_app, wrong_log = await backend_process({**environment, "MODULE": "keyboard_controller"})
        assert await asyncio.wait_for(wrong_app.wait(), 15) != 0
        assert "does not match" in wrong_log.read_text()
        assert not marker.exists()

        app = payload / "packages/dt_app_empty_viewer/app.py"
        original = app.read_bytes()
        app.write_bytes(original + b"\n# unauthorized modification\n")
        altered, altered_log = await backend_process(environment)
        assert await asyncio.wait_for(altered.wait(), 15) != 0
        assert "signed release inventory" in altered_log.read_text()
        assert not marker.exists()
        app.write_bytes(original)

        backend, backend_log = await backend_process(environment)
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as http:
            origin = endpoint.removesuffix("/app/")
            for _ in range(100):
                if backend.returncode is not None:
                    raise AssertionError("Backend startup failed:\n" + backend_log.read_text()[-10000:])
                try:
                    async with http.get(origin + "/__viewer__/health") as response:
                        if response.status == 200:
                            break
                except aiohttp.ClientConnectorError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("The native-authorized backend did not become responsive.")
            assert marker.exists(), "The authorized app was not imported."
            for path in ("/app/", "/app/__state__/", "/app/__tobackend__/"):
                async with http.get(origin + path) as response:
                    assert response.status == 403, (path, response.status)
            async with http.post(origin + "/__viewer__/session", json={"ticket": tickets["browser"]}) as response:
                assert response.status == 200
            async with http.get(endpoint) as response:
                assert response.status == 200
                assert "text" in await response.text()
            async with http.get(origin + "/app/__state__/") as response:
                assert response.status == 200
                for header in response.headers.getall("Link", []):
                    for target in re.findall(r"<([^>]+)>", header):
                        assert urlsplit(target).netloc in ("", urlsplit(origin).netloc), target
            async with http.ws_connect(origin + "/app/__state__/:events/") as stream:
                assert (await stream.receive(timeout=5)).type == aiohttp.WSMsgType.BINARY
                guard_log = (directory / "desktop.log").open("wb")
                logs.append(guard_log)
                guard = await asyncio.create_subprocess_exec(
                    str(directory / "desktop/bin" / executable),
                    "--handoff", str(desktop_handoff), "--url", endpoint,
                    stdout=asyncio.subprocess.PIPE, stderr=guard_log,
                )
                children.append(guard)
                ready = json.loads(await asyncio.wait_for(guard.stdout.readline(), 15))
                assert ready == {"authorized": True, "ticket": tickets["desktop"]}

                async def consume_until_closed():
                    async for _ in stream:
                        pass

                draining = asyncio.create_task(consume_until_closed())
                started = time.monotonic()
                await asyncio.to_thread(session.close)
                await asyncio.wait_for(asyncio.gather(backend.wait(), guard.wait(), draining), timeout=35)
                assert time.monotonic() - started <= 35
                assert backend.returncode != 0 and guard.returncode != 0
                print("PASS: compiled backend and frozen native guard; HTTP/real DTPS WS; denial-before-import; tamper rejection; DTS-exit shutdown within 35 seconds.")
    finally:
        failed = sys.exc_info()[0] is not None
        if session is not None:
            await asyncio.to_thread(session.close)
        mocks.close()
        for process in children:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        for log in logs:
            log.close()
        if failed:
            for path in directory.glob("*.log"):
                print(f"\n{path.name}:\n{path.read_text(errors='replace')[-10000:]}", file=sys.stderr)


def family_name():
    return {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=ROOT.parent / "dt-duckietown-viewer")
    parser.add_argument("--common", type=Path, default=ROOT.parent / "dt-commons/packages")
    parser.add_argument("--backend-python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    args.backend, args.common, args.backend_python = (
        args.backend.resolve(), args.common.resolve(), args.backend_python.absolute(),
    )
    with tempfile.TemporaryDirectory(prefix="viewer-native-test-") as temporary:
        directory = Path(temporary)
        prepared = prepare(directory, args.backend)
        asyncio.run(exercise(directory, args, prepared))


if __name__ == "__main__":
    main()
