"""Build isolated test trust and exercise compiled Engine startup and lifetime enforcement.

The workload is a loopback HTTP fixture, not a simulator or physical robot.
"""

import argparse
from contextlib import ExitStack
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
from dt_shell import engine
from dt_shell_tests.test_engine import EngineFixture
from dt_shell_tests.test_renderer import DEVICE, IDENTITY, ISSUERS, UID, public


def run(command, *, cwd, env):
    result = subprocess.run(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300,
    )
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}):\n{result.stdout[-12000:]}")


def prepare(directory: Path, checkout: Path):
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    authorities = {}
    for name in (
        "DTS_RELEASE_PUBLIC_KEY", "DTS_COMMANDS_PUBLIC_KEY", "DTM_RELEASE_PUBLIC_KEY",
        "DTV_RELEASE_PUBLIC_KEY", "DTM_ENGINE_RELEASE_PUBLIC_KEY",
    ):
        authorities[name] = Ed25519PrivateKey.generate()
        environment[name] = public(authorities[name])
    for name in (
        "DTS_DEVELOPER_PUBLIC_KEYS", "DTM_RENDERER_PUBLIC_KEYS", "DTV_AUTH_PUBLIC_KEYS", "DTM_ENGINE_PUBLIC_KEYS",
    ):
        authorities[name] = {issuer: Ed25519PrivateKey.generate() for issuer in ISSUERS}
        environment[name] = json.dumps({issuer: public(key) for issuer, key in authorities[name].items()})
    build = directory / "guard-source"
    for name in (
        "build_support.py", "lib/dt_shell/engine_runtime.py", "lib/dt_shell/viewer_runtime.py",
        "tools/engine_guard/setup.py", "tools/engine_guard/trust.pyx",
    ):
        destination = build / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    run([
        sys.executable, "tools/engine_guard/setup.py", "bdist_wheel", "--dist-dir", str(directory / "wheels"),
    ], cwd=build, env=environment)
    wheel, = (directory / "wheels").glob("*.whl")
    site = directory / "native-site"
    run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(site), str(wheel)], cwd=build, env=environment)
    run([
        sys.executable, "-m", "unittest", "dt_shell_tests.test_engine_native",
    ], cwd=ROOT, env={**environment, "PYTHONPATH": os.pathsep.join((str(site), str(ROOT / "lib")))})
    payload = directory / "payload"
    shutil.copytree(
        checkout / "packages", payload / "packages",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so", "*.pyd"),
    )
    run([
        sys.executable, str(checkout / "tools/compile_engine.py"), "build_ext", "--inplace",
        "--build-lib", str(directory / "engine-build-lib"), "--build-temp", str(directory / "engine-build-temp"),
    ], cwd=payload, env=environment)
    spec = importlib.util.spec_from_file_location("native_engine_release_tools", ROOT / "tools/engine_release.py")
    tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools)
    fixture = EngineFixture(directory)
    fixture.keys = authorities["DTM_ENGINE_PUBLIC_KEYS"]
    fixture.issuers = {issuer: public(key) for issuer, key in fixture.keys.items()}
    fixture.release_key = authorities["DTM_ENGINE_RELEASE_PUBLIC_KEY"]
    fixture.release_public = public(fixture.release_key)
    family = "linux-arm64" if platform.machine().lower() in ("aarch64", "arm64") else "linux"
    with patch.dict(os.environ, environment):
        release = tools.seal(payload, version="1.0.0", platform=family, key=fixture.release_key)
    return fixture, site, payload, release, checkout / "packages/duckiematrix_engine/engine.py"


WORKLOAD = """
import json, signal, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from duckiematrix_engine import bootstrap
marker, stopped, mode = map(str, sys.argv[1:4])
def work():
    if mode == "stalled":
        Path(marker).write_text("initializing")
        time.sleep(120)
        return
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"authorized")
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    stop = threading.Event()
    def terminate(*args):
        if mode == "systemexit":
            raise SystemExit(0)
        stop.set()
    signal.signal(signal.SIGTERM, terminate)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    Path(marker).write_text(json.dumps({"port": server.server_port}))
    try:
        stop.wait(120)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        Path(stopped).write_text("closed")
bootstrap._run = work
bootstrap.main()
"""

CORE_CONSTRUCTOR = """
import argparse, ast, importlib, sys
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock
for node in ast.parse(Path(sys.argv[1]).read_text()).body:
    if isinstance(node, ast.ImportFrom) and node.module.startswith(("dt_", "packages.")):
        module = ModuleType(node.module)
        for name in node.names:
            value = type("DTProcess", (), {}) if name.name == "DTProcess" else MagicMock(name=name.name)
            setattr(module, name.name, value)
        sys.modules[node.module] = module
sys.modules["netifaces"] = ModuleType("netifaces")
core = importlib.import_module("packages.duckiematrix_engine.engine")
assert core.__file__.endswith(tuple(EXTENSION_SUFFIXES))
from duckietown_engine_guard import EngineAuthorizationError
try:
    core.MatrixEngine(argparse.Namespace())
except EngineAuthorizationError as error:
    assert "authorized DTS bootstrap" in str(error)
else:
    raise AssertionError("The compiled core must not initialize without its authorized bootstrap.")
"""


def exercise(directory: Path, prepared):
    fixture, site, payload, release, core_source = prepared
    environment = {
        **os.environ, "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(site), str(payload / "packages"), str(payload))),
    }
    environment.pop("DT_MATRIX_ENGINE_HANDOFF", None)
    children = []
    logs = []

    def start(name, *, handoff=None, mode="running"):
        marker = directory / f"{name}.ready"
        stopped = directory / f"{name}.stopped"
        log = (directory / f"{name}.log").open("wb")
        logs.append(log)
        child = subprocess.Popen(
            [sys.executable, "-c", WORKLOAD, str(marker), str(stopped), mode], cwd=payload,
            env={**environment, **({"DT_MATRIX_ENGINE_HANDOFF": str(handoff)} if handoff else {})},
            stdout=log, stderr=log,
        )
        children.append(child)
        return child, marker, stopped

    def ready(child, marker):
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline and child.poll() is None:
            time.sleep(0.05)
        if not marker.exists():
            raise AssertionError(f"Authorized workload did not start ({child.poll()}).")

    try:
        run([sys.executable, "-c", CORE_CONSTRUCTOR, str(core_source)], cwd=payload, env=environment)
        denied, marker, _ = start("denied")
        assert denied.wait(timeout=15) != 0 and not marker.exists()
        assert "requires a live authorized DTS session" in (directory / "denied.log").read_text()
        shell = SimpleNamespace(profile=SimpleNamespace(
            distro=SimpleNamespace(name="ente"),
            database=lambda name: SimpleNamespace(yaml=str(directory / "profile" / (name + ".yaml"))),
        ))
        context = {"distribution": "ente", "runtime": release["sha256"], "image": "1" * 64,
                   "device_id": DEVICE, "development": False}
        with ExitStack() as stack:
            for mock in (
                patch("dt_shell.engine._trust", return_value=(fixture.release_public, fixture.issuers)),
                patch("dt_shell.renderer._identity", return_value=(IDENTITY, SimpleNamespace(uid=UID))),
                patch("dt_shell.renderer.DTHUB_URL", ISSUERS[0]),
                patch("dt_shell_device.get_device_parameters", return_value={"device_id": DEVICE, "device_hostname": "test"}),
                patch("dt_shell_device.get_device_id", return_value=DEVICE),
                patch("dt_shell_device.get_renderer_device_id", return_value=DEVICE),
                patch.object(engine.EngineSession, "_request", new=lambda session: fixture.grant(session.launch_key)),
            ):
                stack.enter_context(mock)
            session = engine.EngineSession(shell, context=context)
            stack.callback(session.close)
            handoff = directory / "engine.json"
            session.write_handoff(handoff)
            path = payload / "packages/duckiematrix_engine/main.py"
            original = path.read_bytes()
            path.write_bytes(original + b"\n# altered fixture\n")
            tampered, marker, _ = start("tampered", handoff=handoff)
            assert tampered.wait(timeout=15) != 0 and not marker.exists()
            path.write_bytes(original)
            live, marker, stopped = start("live", handoff=handoff)
            ready(live, marker)
            port = json.loads(marker.read_text())["port"]
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                assert response.status == 200 and response.read() == b"authorized"
            finally:
                connection.close()
            stalled, startup, _ = start("stalled", handoff=handoff, mode="stalled")
            ready(stalled, startup)
            exited, exit_ready, exit_stopped = start("systemexit", handoff=handoff, mode="systemexit")
            ready(exited, exit_ready)
            started = time.monotonic()
            session.close()
            assert live.wait(timeout=40) != 0
            assert stalled.wait(timeout=max(1, 40 - (time.monotonic() - started))) != 0
            assert exited.wait(timeout=max(1, 40 - (time.monotonic() - started))) != 0
            elapsed = time.monotonic() - started
            assert elapsed <= 40, elapsed
            assert stopped.read_text() == "closed"
            assert exit_stopped.read_text() == "closed"
            print(
                "Native Engine guard: compiled core constructor/startup/tamper denial, HTTP workload, "
                f"graceful shutdown and stalled-start cancellation passed in {elapsed:.2f}s."
            )
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True, help="dt-duckiematrix checkout")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="duckiematrix-engine-native-") as temporary:
        directory = Path(temporary)
        prepared = prepare(directory, args.engine.resolve())
        exercise(directory, prepared)
    print("Isolated native guard, compiled Engine payload and temporary test keys were removed.")


if __name__ == "__main__":
    main()
