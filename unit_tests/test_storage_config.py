from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from whitespace_tool.storage_config import load_storage_config


class StorageConfigTests(unittest.TestCase):
    def test_env_storage_config_works_without_local_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_config = Path(temp_dir) / "storage.json"
            env = {
                "BIGQUERY_PROJECT_ID": "render-project",
                "BIGQUERY_BRONZE_DATASET_ID": "bronze",
                "BIGQUERY_SILVER_DATASET_ID": "silver",
                "BIGQUERY_GOLD_DATASET_ID": "gold",
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_storage_config(missing_config)
        self.assertEqual(config["project_id"], "render-project")
        self.assertEqual(config["bronze_dataset_id"], "bronze")
        self.assertEqual(config["silver_dataset_id"], "silver")
        self.assertEqual(config["gold_dataset_id"], "gold")

    def test_inline_credentials_json_is_written_to_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            credentials_path = Path(temp_dir) / "service-account.json"
            env = {
                "BIGQUERY_PROJECT_ID": "render-project",
                "BIGQUERY_BRONZE_DATASET_ID": "bronze",
                "GOOGLE_APPLICATION_CREDENTIALS_JSON": '{"type":"service_account"}',
                "BIGQUERY_CREDENTIALS_PATH": str(credentials_path),
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_storage_config(Path(temp_dir) / "missing.json")
            self.assertEqual(config["credentials_json"], str(credentials_path))
            self.assertEqual(credentials_path.read_text(encoding="utf-8"), '{"type":"service_account"}')

    def test_inline_credentials_accepts_python_dict_style_paste(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            credentials_path = Path(temp_dir) / "service-account.json"
            env = {
                "BIGQUERY_PROJECT_ID": "render-project",
                "BIGQUERY_BRONZE_DATASET_ID": "bronze",
                "GOOGLE_APPLICATION_CREDENTIALS_JSON": "{'type':'service_account','project_id':'render-project'}",
                "BIGQUERY_CREDENTIALS_PATH": str(credentials_path),
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_storage_config(Path(temp_dir) / "missing.json")
            self.assertEqual(config["credentials_json"], str(credentials_path))
            self.assertEqual(credentials_path.read_text(encoding="utf-8"), '{"type":"service_account","project_id":"render-project"}')


if __name__ == "__main__":
    unittest.main()
