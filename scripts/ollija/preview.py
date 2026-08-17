from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .config import ProjectConfig
from .database import (
    DatabaseFingerprint,
    DatabaseSafetyPolicy,
    guard_refresh_target,
)


class PreviewError(ValueError):
    """The local preview cannot be started safely."""


_REMOVED_PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "DEEPSEEK_API_KEY",
    "TWITTERAPI_IO_API_KEY",
    "X_MONITOR_HEADLINE_API_KEY",
)


@dataclass(frozen=True, slots=True)
class PreviewPlan:
    host: str
    port: int
    local_url: str
    private_url: str
    database_url: str
    environment: Mapping[str, str]
    removed_environment_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreviewRuntime:
    pid: int
    database: str
    local_url: str
    private_url: str
    started_at: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "pid": self.pid,
            "database": self.database,
            "local_url": self.local_url,
            "private_url": self.private_url,
            "started_at": self.started_at,
        }


def _database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise PreviewError("preview_database_not_postgres")
    name = parsed.path.lstrip("/")
    if not name:
        raise PreviewError("preview_database_name_missing")
    return name


def build_preview_plan(
    config: ProjectConfig,
    *,
    database_url: str,
    database: DatabaseFingerprint,
    policy: DatabaseSafetyPolicy,
    port_available: Callable[[str, int], bool],
    tailscale_dns_name: str,
) -> PreviewPlan:
    url_database = _database_name(database_url)
    guard_refresh_target(database, policy, allowed_statuses={"active"})
    if database.environment != "local":
        raise PreviewError("preview_database_not_local")
    if url_database != database.database:
        raise PreviewError("preview_database_identity_mismatch")

    local = config.environments.get("local")
    if not isinstance(local, Mapping):
        raise PreviewError("preview_config_invalid")
    host = local.get("preview_host")
    port = local.get("preview_port")
    hostname = local.get("tailscale_hostname")
    if not isinstance(host, str) or not isinstance(port, int):
        raise PreviewError("preview_config_invalid")
    if not port_available(host, port):
        raise PreviewError("preview_port_occupied")

    dns_name = tailscale_dns_name.rstrip(".").lower()
    if (
        not isinstance(hostname, str)
        or not dns_name.endswith(".ts.net")
        or dns_name.split(".", 1)[0] != hostname.lower()
    ):
        raise PreviewError("preview_tailnet_identity_invalid")

    private_url = f"https://{dns_name}"
    environment = {
        "DATABASE_URL": database_url,
        "DEBUG": "True",
        "ALLOWED_HOSTS": f"{host},{dns_name}",
        "CSRF_TRUSTED_ORIGINS": private_url,
        "OLLIJA_STAGING_MODE": "True",
        "XMONITOR_DRY_RUN": "True",
        "X_MONITOR_HEADLINE_SERVING_ENABLED": "False",
        "X_MONITOR_HEADLINE_ENQUEUE_ENABLED": "False",
        "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED": "False",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
    }
    return PreviewPlan(
        host=host,
        port=port,
        local_url=f"http://{host}:{port}",
        private_url=private_url,
        database_url=database_url,
        environment=environment,
        removed_environment_keys=_REMOVED_PROVIDER_KEYS,
    )


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def tailscale_dns_name() -> str:
    completed = subprocess.run(
        ["tailscale", "status", "--json"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise PreviewError("preview_tailnet_unreachable")
    try:
        body = json.loads(completed.stdout)
        name = body["Self"]["DNSName"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PreviewError("preview_tailnet_identity_invalid") from exc
    if not isinstance(name, str):
        raise PreviewError("preview_tailnet_identity_invalid")
    return name


def _runtime_path(config: ProjectConfig) -> Path:
    return config.state_root / "runtime" / "preview.json"


def _write_runtime(path: Path, runtime: PreviewRuntime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".preview.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(runtime.to_dict(), handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _load_runtime(path: Path) -> PreviewRuntime | None:
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        return PreviewRuntime(
            pid=int(body["pid"]),
            database=str(body["database"]),
            local_url=str(body["local_url"]),
            private_url=str(body["private_url"]),
            started_at=str(body["started_at"]),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PreviewError("preview_runtime_invalid") from exc


def _process_command(pid: int) -> str | None:
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _serve_status() -> object:
    completed = subprocess.run(
        ["tailscale", "serve", "status", "--json"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise PreviewError("preview_tailnet_serve_unreachable")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PreviewError("preview_tailnet_serve_invalid") from exc


def _wait_until_ready(url: str, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise PreviewError("preview_process_exited")
        try:
            with urllib.request.urlopen(f"{url}/accounts/login/", timeout=2) as response:
                if response.status < 500:
                    time.sleep(0.1)
                    if process.poll() is not None:
                        raise PreviewError("preview_process_exited")
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    raise PreviewError("preview_start_timeout")


def start_preview(config: ProjectConfig, plan: PreviewPlan) -> PreviewRuntime:
    runtime_path = _runtime_path(config)
    existing = _load_runtime(runtime_path)
    if existing and _process_command(existing.pid):
        raise PreviewError("preview_already_running")
    if existing:
        runtime_path.unlink(missing_ok=True)
    if _serve_status() not in ({}, None):
        raise PreviewError("preview_tailnet_serve_in_use")

    environment = dict(os.environ)
    for key in plan.removed_environment_keys:
        environment.pop(key, None)
    environment.update(plan.environment)
    environment["GOOGLE_CLIENT_ID"] = os.environ.get(
        "OLLIJA_STAGING_GOOGLE_CLIENT_ID", ""
    )
    environment["GOOGLE_CLIENT_SECRET"] = os.environ.get(
        "OLLIJA_STAGING_GOOGLE_CLIENT_SECRET", ""
    )

    logs = config.state_root / "logs"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    logs.chmod(0o700)
    log_path = logs / "preview.log"
    log_handle = log_path.open("ab")
    os.chmod(log_path, 0o600)
    process = subprocess.Popen(
        [
            str(config.canonical_virtualenv / "bin" / "python"),
            str(config.root / "manage.py"),
            "runserver",
            "--noreload",
            f"{plan.host}:{plan.port}",
        ],
        cwd=config.root,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    serve_started = False
    try:
        _wait_until_ready(plan.local_url, process)
        try:
            served = subprocess.run(
                ["tailscale", "serve", "--bg", "--yes", str(plan.port)],
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PreviewError("preview_tailnet_serve_timeout") from exc
        if served.returncode != 0:
            raise PreviewError("preview_tailnet_serve_failed")
        serve_started = True
        runtime = PreviewRuntime(
            pid=process.pid,
            database=urlparse(plan.database_url).path.lstrip("/"),
            local_url=plan.local_url,
            private_url=plan.private_url,
            started_at=datetime.now(UTC).isoformat(),
        )
        _write_runtime(runtime_path, runtime)
        return runtime
    except BaseException:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        if serve_started:
            subprocess.run(
                ["tailscale", "serve", "reset"],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
        raise


def _contains_port(value: object, port: int) -> bool:
    if isinstance(value, str):
        return f":{port}" in value or value == str(port)
    if isinstance(value, Mapping):
        return any(_contains_port(item, port) for item in value.values())
    if isinstance(value, list):
        return any(_contains_port(item, port) for item in value)
    return False


def stop_preview(config: ProjectConfig) -> PreviewRuntime:
    runtime_path = _runtime_path(config)
    runtime = _load_runtime(runtime_path)
    if runtime is None:
        raise PreviewError("preview_not_running")
    command = _process_command(runtime.pid)
    if command is not None:
        if str(config.root / "manage.py") not in command and not (
            "manage.py runserver" in command and str(config.root) in command
        ):
            raise PreviewError("preview_process_identity_mismatch")
        os.kill(runtime.pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while _process_command(runtime.pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _process_command(runtime.pid):
            raise PreviewError("preview_process_stop_timeout")

    serve = _serve_status()
    if serve not in ({}, None):
        if not _contains_port(serve, urlparse(runtime.local_url).port or 0):
            raise PreviewError("preview_tailnet_serve_identity_mismatch")
        completed = subprocess.run(
            ["tailscale", "serve", "reset"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise PreviewError("preview_tailnet_reset_failed")
    runtime_path.unlink(missing_ok=True)
    return runtime
