"""Dedicated runtime activation uses the same reviewed configuration guards.

These configuration tests need no database or provider access.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from x_monitor.config import load_config

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"
ACTIVATION = {
    "X_MONITOR_RARE_TYPES_ENABLED": "true",
    "X_MONITOR_RARE_TYPES_TARGETED_EXTRACTION_ENABLED": "true",
    "X_MONITOR_RARE_TYPES_ASSESSMENT_PATH": "reviewed-assessment.json",
    "X_MONITOR_RARE_TYPES_ASSESSMENT_DIGEST": "a" * 64,
}


class BackfillEnvironmentTests(unittest.TestCase):
    def test_same_configuration_in_all_deployed_environments(self):
        snapshots = []
        for name in ("staging", "production", "backfill"):
            with self.subTest(environment=name), patch.dict(
                os.environ,
                ACTIVATION | {"X_MONITOR_DEPLOYMENT_ENVIRONMENT": name},
                clear=True,
            ):
                cfg = load_config(CONFIG)
                self.assertTrue(cfg.discovery.rare_types.enabled)
                self.assertTrue(cfg.targeted_extraction.enabled)
                snapshots.append(cfg.model_dump())
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0], snapshots[2])

    def test_unlabelled_local_and_preview_still_rejected(self):
        for name in ("", "local", "preview"):
            with self.subTest(environment=name), patch.dict(
                os.environ,
                ACTIVATION | {"X_MONITOR_DEPLOYMENT_ENVIRONMENT": name},
                clear=True,
            ), self.assertRaisesRegex(ValueError, "rare-types activation requires"):
                load_config(CONFIG)

    def test_backfill_still_requires_complete_activation(self):
        for key in ACTIVATION.keys() - {"X_MONITOR_RARE_TYPES_ENABLED"}:
            values = ACTIVATION | {"X_MONITOR_DEPLOYMENT_ENVIRONMENT": "backfill"}
            del values[key]
            with self.subTest(missing=key), patch.dict(
                os.environ, values, clear=True
            ), self.assertRaisesRegex(ValueError, "assessment evidence|extraction switch"):
                load_config(CONFIG)
