"""Django management command: harvest_preview.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U4 (R10, R11, R21).

Wrapper around x_monitor.harvest_preview.build_preview. Prints the
preview report to stdout; exits 1 when the R11 coverage invariant is
violated (CI fail signal).

NO network calls — preview is OFFLINE (R21 / M8).
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from x_monitor.harvest_preview import (
    build_preview,
    coverage_invariant_holds,
    render_preview,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class Command(BaseCommand):
    help = (
        "Print the harvest cycle preview (calls + brand coverage) "
        "offline from config.yaml + harvest_policy.yaml. Exits 1 when "
        "an enabled brand has no call_ids (R11 invariant)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--config", default=str(REPO_ROOT / "config.yaml"),
            help="Path to config.yaml (default: repo-root/config.yaml).",
        )
        parser.add_argument(
            "--policy",
            default=str(REPO_ROOT / "config" / "harvest_policy.yaml"),
            help=(
                "Path to harvest policy YAML (default: "
                "config/harvest_policy.yaml). Falls back to "
                "config.x_query_specs when missing (pre-U5 mode)."
            ),
        )
        parser.add_argument(
            "--list-id", default=None,
            help=(
                "Override X list id for Call A. Defaults to "
                "x_monitor_list_id from config.yaml."
            ),
        )
        parser.add_argument(
            "--fail-on-invariant-violation",
            action="store_true",
            help=(
                "Exit 1 when the R11 coverage invariant is violated "
                "(any enabled brand lacks paths or unmapped)."
            ),
        )

    def handle(self, *args, **options) -> None:
        cfg = Path(options["config"])
        pol = Path(options["policy"]) if options["policy"] else None
        list_id_override = options["list_id"]
        fail_on_violation = options.get("fail_on_invariant_violation", False)

        if not cfg.exists():
            raise CommandError(f"config not found: {cfg}")

        report = build_preview(
            config_path=cfg,
            policy_path=pol,
            x_monitor_list_id=list_id_override,
        )
        render_preview(report, self.stdout)

        if fail_on_violation and not coverage_invariant_holds(report):
            self.stdout.write(self.style.ERROR(
                "\nR11 invariant violated: an enabled brand has no "
                "call_ids or is not in the policy."
            ))
            raise CommandError("harvest_preview R11 invariant violation")