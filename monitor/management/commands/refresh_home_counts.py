"""Preserve the deployed maintenance entry point while refreshing both datasets."""

from monitor.management.commands.refresh_materializations import (
    Command as RefreshCommand,
)


class Command(RefreshCommand):
    def format_results(self, results):
        return {**results['home.brand_time_counts.v1'], 'materializations': results}
