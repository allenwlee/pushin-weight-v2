# {{AGENT_ATTRIBUTION}}
"""Local Flask dashboard: 9-model grid + per-model drill-down (Unit 7+8)."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .account_graph import build_force_directed
from .config import Config
from .store import Store

log = logging.getLogger(__name__)


# Display name map for the 9 v1 models. PR-reviewable; tweak per brand team
# feedback without touching the rest of the code.
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "minimax": "MiniMax AI",
    "qwen": "Qwen",
    "deepseek": "DeepSeek",
    "glm": "Zhipu GLM",
    "xiaomi_mimo": "Xiaomi MiMo",
    "moonshot_kimi": "Moonshot Kimi",
    "inclusionai": "InclusionAI",
}

# Accent color per model — drives the card border-left + sparkline stroke.
MODEL_ACCENT_COLORS: dict[str, str] = {
    "minimax": "#3b82f6",
    "qwen": "#f97316",
    "deepseek": "#10b981",
    "glm": "#a855f7",
    "xiaomi_mimo": "#eab308",
    "moonshot_kimi": "#ec4899",
    "inclusionai": "#06b6d4",
    
    
}


# --- Sparkline ------------------------------------------------------------


# --- Card data assembly ---------------------------------------------------


def _load_latest_run(runs_dir: Path) -> dict[str, Any] | None:
    if not runs_dir.exists():
        return None
    latest = runs_dir / "LATEST.json"
    target = latest.resolve() if latest.is_symlink() else None
    if target and target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _parse_post_timestamp(created):
    """Parse a tweet created_at into an aware UTC datetime, or None.

    Accepts ISO 8601 ("Z" or "+HH:MM") and Twitter legacy
    ("Mon Jun 08 22:40:07 +0000 2026").
    """
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


# Canonical query_id -> expected_signal mapping. Single source of truth
# shared by the totals branch and the per-day branch in serialize_grid_card.
_QID_TO_SIGNAL: dict[str, str] = {
    "Q1": "release",
    "Q2": "community_question",
    "Q3": "criticism",
    "Q4": "commenter_capture",
    "Q5": "other",
    "Q6": "praise",
}


def _qid_to_signal(qid: str) -> str | None:
    """Map a source_query_id to its expected_signal name, or None for unknown."""
    return _QID_TO_SIGNAL.get(qid)


def serialize_grid_card(
    model_id: str,
    posts: list[dict[str, Any]],
    *,
    window_days: int = 14,
    latest_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the per-model grid card payload."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    in_window: list[dict[str, Any]] = []
    for p in posts:
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        if dt >= cutoff:
            in_window.append(p)

    # Per-day per-signal counts. day_signal_counts[iso_date][signal] = int.
    # A single pass populates both the totals (sig_counts) and the per-day
    # grid that powers the stacked area chart.
    sig_counts: Counter[str] = Counter()
    day_signal_counts: dict[str, Counter[str]] = {}
    for p in in_window:
        sqid = p.get("source_query_id") or ""
        signal = _qid_to_signal(sqid)
        if signal is None:
            continue
        sig_counts[signal] += 1
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        day_signal_counts.setdefault(dt.date().isoformat(), Counter())[signal] += 1

    # Materialize the per-day grid into the response shape Chart.js wants:
    # `days` is a list of ISO date strings (oldest -> newest), and each series
    # is a list[int] aligned to `days` with the count for that signal on that
    # day (0 if no posts). Six series, ordered to match the bar segments.
    chart_series_keys: tuple[str, ...] = (
        "release", "community_question", "criticism",
        "commenter_capture", "other", "praise",
    )
    chart_days: list[str] = []
    chart_series: dict[str, list[int]] = {k: [] for k in chart_series_keys}
    for i in range(window_days - 1, -1, -1):
        d = (now.date() - timedelta(days=i)).isoformat()
        chart_days.append(d)
        day_counter = day_signal_counts.get(d, Counter())
        for sig in chart_series_keys:
            chart_series[sig].append(day_counter.get(sig, 0))

    # Top 3 by like_count (ties broken by recency) — exposes DB column
    # `favorite_count` under the user-facing name `like_count`.
    sorted_posts = sorted(
        in_window,
        key=lambda p: (
            -(p.get("favorite_count") or 0),
            p.get("created_at") or "",
        ),
    )
    top3: list[dict[str, Any]] = []
    for p in sorted_posts[:3]:
        text = (p.get("text") or "").strip()
        if len(text) > 200:
            text = text[:197] + "..."
        headline = (p.get("headline") or "").strip() or None
        # Headline preference: if the post has a fetched headline,
        # render the headline instead of the bare URL. The original
        # text is still passed to the template as a fallback.
        display_text = headline if headline else text
        top3.append(
            {
                "tweet_id": p.get("tweet_id") or p.get("id"),
                "text": text,
                "headline": headline,
                "headline_source": p.get("headline_source"),
                "display_text": display_text,
                "like_count": p.get("favorite_count") or 0,
                "author_handle": p.get("author_handle"),
                "url": _tweet_url(p.get("author_handle"), p.get("tweet_id") or p.get("id")),
            }
        )

    # Degraded sentinels
    sentinels: list[str] = []
    if latest_run:
        degraded = latest_run.get("degraded") or {}
        if degraded.get("cookies"):
            sentinels.append("cookies")
        # Per-model: query_rot
        for q in latest_run.get("queries") or []:
            if q.get("model_id") == model_id and q.get("status") == "error":
                sentinels.append(f"q_error:{q.get('query_id')}")
        # Per-model: skipped_budget entries
        for entry in degraded.get("skipped_budget") or []:
            if isinstance(entry, str) and entry.startswith(f"{model_id}/"):
                sentinels.append("budget")

    return {
        "model_id": model_id,
        "display_name": MODEL_DISPLAY_NAMES.get(model_id, model_id),
        "accent_color": MODEL_ACCENT_COLORS.get(model_id, "#9ca3af"),
        "chart": {"days": chart_days, "series": chart_series},
        "signal_breakdown": dict(sig_counts),
        "top3_posts": top3,
        "n_posts_in_window": len(in_window),
        "degraded_sentinels": sentinels,
        "last_run_at": (latest_run or {}).get("finished_at"),
    }


def _tweet_url(handle: str | None, tweet_id: str | None) -> str | None:
    if not handle or not tweet_id:
        return None
    return f"https://x.com/{handle}/status/{tweet_id}"


# --- DashboardApp ---------------------------------------------------------


class DashboardApp:
    """Wraps a Flask app and provides start/stop/status CLI hooks."""

    def __init__(
        self,
        config: Config,
        data_dir: Path,
        db_path: Path,
    ):
        self.config = config
        self.data_dir = data_dir
        self.db_path = db_path
        self.runs_dir = data_dir / "runs"
        self.template_dir = Path(__file__).parent / "templates"
        self.static_dir = Path(__file__).parent / "static"
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html.j2"]),
        )
        # Make our helpers available in templates
        env.globals["MODEL_DISPLAY_NAMES"] = MODEL_DISPLAY_NAMES
        env.globals["MODEL_ACCENT_COLORS"] = MODEL_ACCENT_COLORS

        app = Flask(
            __name__,
            template_folder=str(self.template_dir),
            static_folder=str(self.static_dir),
        )
        app.config["JSON_SORT_KEYS"] = False
        self.app = app
        self._register_routes()

    def _build_cards(self, db_path) -> tuple[list[dict], dict | None]:
        """Build card payloads for all enabled models. Shared by /, /api/grid.json, /api/grid.html."""
        cards: list[dict] = []
        latest_run = _load_latest_run(self.runs_dir)
        store = Store(db_path)
        try:
            for m in self.config.enabled_models:
                posts = store.get_all_posts(m)
                cards.append(
                    serialize_grid_card(
                        m, posts, window_days=self.config.dashboard.window_days, latest_run=latest_run
                    )
                )
        finally:
            store.close()
        return cards, latest_run

    def _register_routes(self) -> None:
        app = self.app
        data_dir = self.data_dir
        db_path = self.db_path
        window_days = self.config.dashboard.window_days

        @app.route("/")
        def index():
            cards, _latest_run = self._build_cards(db_path)
            return render_template(
                "grid.html.j2",
                cards=cards,
                poll_seconds=self.config.dashboard.poll_seconds,
            )

        @app.route("/api/grid.html")
        def api_grid_html():
            # HTML fragment of just the cards; htmx polls this every Ns.
            # Returns innerHTML payload so the wrapping <main> element
            # persists and keeps its hx-trigger attribute attached.
            cards, _latest_run = self._build_cards(db_path)
            return render_template("_grid_cards.html.j2", cards=cards)

        @app.route("/api/grid.json")
        def api_grid():
            cards, _latest_run = self._build_cards(db_path)
            return jsonify({"cards": cards, "fetched_at": datetime.now(timezone.utc).isoformat()})

        @app.route("/model/<model_id>")
        def model_detail(model_id: str):
            if model_id not in self.config.enabled_models:
                abort(404)
            from .account_graph import build_force_directed

            store = Store(db_path)
            try:
                posts = store.get_all_posts(model_id)
                accounts = store.get_accounts(model_id)
            finally:
                store.close()
            # Re-derive edges from posts for the drill-down graph
            from .accounts import derive_edges, find_clusters

            posts_for_edges = [
                {
                    "id": p.get("tweet_id"),
                    "author_handle": p.get("author_handle"),
                    "in_reply_to_user_id": p.get("in_reply_to_user_id"),
                    "quoted_status_id": p.get("quoted_status_id"),
                    "entities": json.loads(p.get("entities") or "{}"),
                    "conversation_id": p.get("conversation_id"),
                }
                for p in posts
            ]
            edges = derive_edges(posts_for_edges, model_id)
            clusters = find_clusters(
                posts_for_edges,
                edges,
                min_commenters=self.config.clustering.min_commenters,
                min_posts=self.config.clustering.min_posts,
            )
            # Build graph nodes from accounts; if empty (first run), fall back
            # to unique authors in posts.
            nodes = list(accounts)
            if not nodes:
                from .accounts import Account as _Acc

                seen: set[str] = set()
                for p in posts:
                    h = p.get("author_handle")
                    if h and h not in seen:
                        seen.add(h)
                        nodes.append(_Acc(handle=h))
            graph_svg = build_force_directed(nodes, edges, width=800, height=600)
            role_counts: Counter[str] = Counter(a.get("role", "unknown") for a in accounts)
            return render_template(
                "model_detail.html.j2",
                model_id=model_id,
                display_name=MODEL_DISPLAY_NAMES.get(model_id, model_id),
                accent_color=MODEL_ACCENT_COLORS.get(model_id, "#9ca3af"),
                posts=posts[:200],
                clusters=clusters,
                graph_svg=graph_svg,
                role_counts=dict(role_counts),
                latest_run=_load_latest_run(self.runs_dir),
            )

        @app.route("/api/model/<model_id>.json")
        def api_model(model_id: str):
            if model_id not in self.config.enabled_models:
                abort(404)
            store = Store(db_path)
            try:
                posts = store.get_all_posts(model_id)
                accounts = store.get_accounts(model_id)
            finally:
                store.close()
            return jsonify(
                {
                    "model_id": model_id,
                    "display_name": MODEL_DISPLAY_NAMES.get(model_id, model_id),
                    "n_posts": len(posts),
                    "n_accounts": len(accounts),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    # --- process management ----------------------------------------------

    def start_background(self) -> int:
        """Spawn the Flask server in the background, write pid file, return pid."""
        import socket

        host = self.config.dashboard.host
        port = self.config.dashboard.port
        # Bind test
        with socket.socket() as s:
            try:
                s.bind((host, port))
            except OSError:
                raise RuntimeError(
                    f"port {port} in use; change config.yaml::dashboard.port"
                )
        log_path = self.data_dir / "dashboard.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(log_path, "a")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"from x_monitor.dashboard import DashboardApp; "
                f"from x_monitor.config import load_config; "
                f"from pathlib import Path; "
                f"c=load_config(Path('config.yaml')); "
                f"app=DashboardApp(c, Path('data'), Path('data/x_monitoring.db')); "
                f"app.app.run(host=c.dashboard.host, port=c.dashboard.port, "
                f"debug=False, use_reloader=False)",
            ],
            stdout=logf,
            stderr=logf,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        pid_path = self.data_dir / "dashboard.pid"
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    @staticmethod
    def stop_background(data_dir: Path) -> bool:
        """Send SIGTERM to the dashboard pid. Returns True if a process was found."""
        pid_path = data_dir / "dashboard.pid"
        if not pid_path.exists():
            return False
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        finally:
            try:
                pid_path.unlink()
            except OSError:
                pass
        return True

    @staticmethod
    def status(data_dir: Path) -> dict[str, Any]:
        pid_path = data_dir / "dashboard.pid"
        log_path = data_dir / "dashboard.log"
        out: dict[str, Any] = {"pid_file": str(pid_path)}
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
                out["pid"] = pid
                # Process lookup
                try:
                    os.kill(pid, 0)
                    out["running"] = True
                except ProcessLookupError:
                    out["running"] = False
            except (OSError, ValueError):
                out["running"] = False
        else:
            out["running"] = False
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding="utf-8").splitlines()
                out["log_tail"] = "\n".join(lines[-50:])
            except OSError:
                pass
        return out
