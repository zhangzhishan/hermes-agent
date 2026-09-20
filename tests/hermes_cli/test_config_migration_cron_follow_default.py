"""Local migration contract for cron jobs that intentionally follow model.default."""

import os
from unittest.mock import patch

import yaml


def test_v33_migration_preserves_disabled_model_drift_guard(tmp_path):
    from hermes_cli.config import migrate_config
    from hermes_cli.config_defaults import DEFAULT_CONFIG

    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "_config_version": 33,
                "model": {"default": "gpt-5.6-sol"},
                "cron": {"model_drift_guard": False},
            }
        ),
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        migrate_config(interactive=False, quiet=True)

    migrated = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert migrated["_config_version"] == DEFAULT_CONFIG["_config_version"]
    assert migrated["model"]["default"] == "gpt-5.6-sol"
    assert migrated["cron"]["model_drift_guard"] is False
