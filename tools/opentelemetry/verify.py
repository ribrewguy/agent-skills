#!/usr/bin/env python3
"""Drive a collector container and a fixture app, then check what arrived.

    python3 tools/opentelemetry/verify.py --fixture spring-kotlin|nuxt --outputs <dir>
        [--module mvc|webflux] [--no-collector] [--start-cmd "<command>"]

Prints PASS <check> / FAIL <check> lines and exits non-zero on any FAIL.
Needs Docker for the collector (not for --no-collector).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import check, parse  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
COLLECTOR_CONFIG = REPO / "plugins/opentelemetry/skills/opentelemetry/assets/collector-test.yaml"
COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib"
IGNORE = shutil.ignore_patterns("node_modules", ".nuxt", ".output", "target", ".git", ".data")

results: list[tuple[str, bool, str]] = []


def record(check_id: str, ok: bool, detail: str = "") -> None:
    results.append((check_id, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {check_id}" + (f": {detail}" if detail else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_get(url: str, timeout: float = 30.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_for(url: str, proc: subprocess.Popen, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            if http_get(url, 2) == 200:
                return True
        except OSError:
            pass
        time.sleep(1)
    return False


def start_collector(out_dir: Path) -> tuple[str, int]:
    out_dir.chmod(0o777)
    sink = out_dir / "telemetry.jsonl"
    sink.touch()
    sink.chmod(0o666)
    name = f"otel-verify-{os.getpid()}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::4318",
         "-v", f"{COLLECTOR_CONFIG}:/etc/otelcol-contrib/config.yaml:ro",
         "-v", f"{out_dir}:/out", COLLECTOR_IMAGE],
        check=True, capture_output=True, text=True,
    )
    port = None
    for _ in range(30):
        p = subprocess.run(["docker", "port", name, "4318"], capture_output=True, text=True)
        m = re.search(r":(\d+)\s*$", p.stdout.strip().splitlines()[0]) if p.stdout.strip() else None
        if m:
            port = int(m.group(1))
            break
        time.sleep(1)
    if port is None:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        raise RuntimeError("collector did not publish port 4318")
    for _ in range(60):
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        if "Everything is ready" in logs.stdout + logs.stderr:
            return name, port
        time.sleep(1)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    raise RuntimeError("collector did not report ready")


def prepare(args, work: Path) -> Path:
    src = Path(args.outputs).resolve()
    dst = work / "app"
    shutil.copytree(src, dst, ignore=IGNORE)
    if args.fixture == "nuxt":
        cmd = ["npm", "ci"] if (dst / "package-lock.json").exists() else ["npm", "install"]
        subprocess.run(cmd + ["--no-audit", "--no-fund"], cwd=dst, check=True, capture_output=True)
    return dst


def own_tests(args, app: Path) -> None:
    cmd = ["./mvnw", "-q", "verify", "-pl", args.module] if args.fixture == "spring-kotlin" else ["npm", "test"]
    p = subprocess.run(cmd, cwd=app, capture_output=True, text=True)
    record("own-tests", p.returncode == 0, "" if p.returncode == 0 else (p.stdout + p.stderr)[-600:].replace("\n", " | "))


def start_command(args, app: Path) -> list[str] | str:
    if args.start_cmd:
        return args.start_cmd
    if args.fixture == "spring-kotlin":
        return ["./mvnw", "-q", "spring-boot:run", "-pl", args.module]
    subprocess.run(["npm", "run", "build"], cwd=app, check=True, capture_output=True)
    cmd = ["node"]
    if (app / "instrumentation.mjs").exists():
        cmd += ["--import", "./instrumentation.mjs"]
    return cmd + [".output/server/index.mjs"]


def run_app(args, app: Path, env: dict, log_path: Path) -> tuple[subprocess.Popen, int]:
    port = free_port()
    full_env = {**os.environ, **env, "PORT": str(port), "NITRO_PORT": str(port), "NITRO_HOST": "127.0.0.1"}
    cmd = start_command(args, app)
    log = open(log_path, "w")
    proc = subprocess.Popen(cmd, cwd=app, env=full_env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True, shell=isinstance(cmd, str))
    return proc, port


def stop_app(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    time.sleep(5)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, choices=["spring-kotlin", "nuxt"])
    ap.add_argument("--outputs", required=True)
    ap.add_argument("--module", choices=["mvc", "webflux"], default="mvc")
    ap.add_argument("--no-collector", action="store_true")
    ap.add_argument("--start-cmd", help="override how the app is started (run from the app root)")
    args = ap.parse_args()

    service = f"fixture-{args.fixture}"
    base_env = {
        "OTEL_SERVICE_NAME": service,
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_RESOURCE_ATTRIBUTES": "service.version=0.0.1,deployment.environment.name=test",
    }
    work = Path(tempfile.mkdtemp(prefix="otel-verify-"))
    collector = None
    try:
        app = prepare(args, work)
        log_path = work / "app.log"

        if args.no_collector:
            proc, port = run_app(args, app, {**base_env, "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:9"}, log_path)
            try:
                up = wait_for(f"http://127.0.0.1:{port}/health", proc, 180)
                status = None
                if up:
                    t0 = time.time()
                    try:
                        status = http_get(f"http://127.0.0.1:{port}/orders/42", 30)
                    except OSError:
                        status = None
                    elapsed = time.time() - t0
                time.sleep(3)
            finally:
                stop_app(proc)
            text = log_path.read_text(errors="replace")
            warns = [l for l in text.splitlines()
                     if re.search(r"(?i)\bwarn", l) and re.search(r"(?i)export|otlp", l)]
            ok = up and status == 200 and len(warns) == 1
            record("no-collector-resilience", ok,
                   f"started={up} orders/42={status} export WARN lines={len(warns)}")
        else:
            out_dir = work / "out"
            out_dir.mkdir()
            collector, cport = start_collector(out_dir)
            own_tests(args, app)
            env = {**base_env, "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://localhost:{cport}"}
            proc, port = run_app(args, app, env, log_path)
            try:
                if not wait_for(f"http://127.0.0.1:{port}/health", proc, 180):
                    record("app-start", False, "app did not serve /health: " + log_path.read_text(errors="replace")[-400:].replace("\n", " | "))
                else:
                    for path in ("/orders/42", "/orders/404", "/orders/boom"):
                        http_get(f"http://127.0.0.1:{port}{path}", 30)
                    time.sleep(2)
            finally:
                stop_app(proc)
            time.sleep(3)
            subprocess.run(["docker", "stop", collector], capture_output=True)
            collector = None
            for cid, ok, detail in check(parse(out_dir / "telemetry.jsonl"), service):
                record(cid, ok, detail)
    finally:
        if collector:
            subprocess.run(["docker", "rm", "-f", collector], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
