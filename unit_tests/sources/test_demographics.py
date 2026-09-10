"""Coverage for whitespace_tool/sources/demographics.py (25% covered at time
of writing).

Follows the fake-google.cloud.bigquery-module-in-sys.modules pattern already
used by unit_tests/test_needs_review_and_backfills.py (_fake_bigquery_modules
/ _FakeBigQueryModuleMixin) rather than inventing a new one - this keeps a
test path from ever importing the real google.cloud.bigquery package.
`fetch_bigquery_demographics` itself is exercised by patching
`_bigquery_client` directly (it's the documented seam, and it's simpler than
faking a full BigQuery RowIterator), so the fake module injection is only
needed for the ImportError-avoidance path inside fetch_bigquery_demographics.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from whitespace_tool.sources import demographics


def _fake_bigquery_modules():
    fake_bigquery = types.SimpleNamespace()
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.bigquery = fake_bigquery
    return {
        "google": types.ModuleType("google"),
        "google.cloud": fake_cloud,
        "google.cloud.bigquery": fake_bigquery,
    }


class _FakeBigQueryModuleMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._bq_mods = patch.dict(sys.modules, _fake_bigquery_modules())
        self._bq_mods.start()
        self.addCleanup(self._bq_mods.stop)


class NumberTests(unittest.TestCase):
    """_number: Census null sentinels and blank/None values collapse to None."""

    def test_census_null_sentinels_become_none(self) -> None:
        for sentinel in ("-666666666", "-888888888", "-999999999"):
            self.assertIsNone(demographics._number(sentinel))

    def test_none_and_empty_string_become_none(self) -> None:
        self.assertIsNone(demographics._number(None))
        self.assertIsNone(demographics._number(""))

    def test_valid_numeric_string_converts_to_float(self) -> None:
        self.assertEqual(demographics._number("42500"), 42500.0)
        self.assertEqual(demographics._number(37.5), 37.5)

    def test_non_numeric_garbage_becomes_none_not_a_crash(self) -> None:
        # A malformed value should degrade to missing data, not blow up the
        # whole demographics fetch.
        self.assertIsNone(demographics._number("not-a-number"))


class RowValueTests(unittest.TestCase):
    """_row_value: dict rows use .get, non-dict (BigQuery Row-like) use []."""

    def test_dict_row_uses_get(self) -> None:
        row = {"population": 100}
        self.assertEqual(demographics._row_value(row, "population"), 100)
        self.assertIsNone(demographics._row_value(row, "missing_field"))

    def test_non_dict_row_uses_getitem(self) -> None:
        class FakeRow:
            def __init__(self, data):
                self._data = data

            def __getitem__(self, key):
                return self._data[key]

            def keys(self):
                return self._data.keys()

        row = FakeRow({"population": 250})
        self.assertEqual(demographics._row_value(row, "population"), 250)
        with self.assertRaises(KeyError):
            demographics._row_value(row, "missing_field")


class FetchBigqueryDemographicsTests(_FakeBigQueryModuleMixin):
    """fetch_bigquery_demographics: builds a dict[zip, ZipDemographics] from
    query result rows. A plain dict works as a fake row: it supports both
    .get() (via _row_value) and .keys() (the "field" in row.keys() checks)."""

    def _fake_client(self, rows):
        class FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def result(self):
                return self._rows

        class FakeClient:
            def query(self_inner, query):
                return FakeResult(rows)

        return FakeClient()

    def test_full_row_populates_all_fields_and_pads_zip(self) -> None:
        row = {
            "zip_code": "501",  # short zip should be zero-padded to 5 digits
            "population": "1000",
            "median_household_income": "55000",
            "median_age": "34.2",
            "city": "Holtsville",
            "county": "Suffolk",
            "state_code": "NY",
            "state_name": "New York",
            "latitude": "40.8",
            "longitude": "-73.0",
            "households": "400",
            "income_per_capita": "27000",
            "poverty": "12.5",
            "employed_population": "600",
            "unemployed_population": "40",
            "housing_units": "420",
        }
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client([row])):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "census_2020")

        self.assertEqual(list(result.keys()), ["00501"])
        demo = result["00501"]
        self.assertEqual(demo.zip_code, "00501")
        self.assertEqual(demo.population, 1000.0)
        self.assertEqual(demo.median_household_income, 55000.0)
        self.assertEqual(demo.median_age, 34.2)
        self.assertEqual(demo.source, "census_2020")
        self.assertEqual(demo.city, "Holtsville")
        self.assertEqual(demo.county, "Suffolk")
        self.assertEqual(demo.state_code, "NY")
        self.assertEqual(demo.state_name, "New York")
        self.assertEqual(demo.latitude, 40.8)
        self.assertEqual(demo.longitude, -73.0)
        self.assertEqual(demo.households, 400.0)
        self.assertEqual(demo.income_per_capita, 27000.0)
        self.assertEqual(demo.poverty, 12.5)
        self.assertEqual(demo.employed_population, 600.0)
        self.assertEqual(demo.unemployed_population, 40.0)
        self.assertEqual(demo.housing_units, 420.0)

    def test_zip_longer_than_five_digits_is_truncated(self) -> None:
        row = {
            "zip_code": "123456",
            "population": None,
            "median_household_income": None,
            "median_age": None,
        }
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client([row])):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "src")

        self.assertEqual(list(result.keys()), ["12345"])

    def test_null_sentinel_values_become_none_in_output(self) -> None:
        row = {
            "zip_code": "10001",
            "population": "-999999999",
            "median_household_income": "-666666666",
            "median_age": "-888888888",
        }
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client([row])):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "src")

        demo = result["10001"]
        self.assertIsNone(demo.population)
        self.assertIsNone(demo.median_household_income)
        self.assertIsNone(demo.median_age)

    def test_missing_optional_columns_stay_none_rather_than_key_error(self) -> None:
        # Row dict intentionally omits every optional field. The "field" in
        # row.keys() guard should prevent a KeyError and leave them None.
        row = {
            "zip_code": "94103",
            "population": "500",
            "median_household_income": "80000",
            "median_age": "29",
        }
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client([row])):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "src")

        demo = result["94103"]
        self.assertEqual(demo.population, 500.0)
        self.assertIsNone(demo.city)
        self.assertIsNone(demo.county)
        self.assertIsNone(demo.state_code)
        self.assertIsNone(demo.state_name)
        self.assertIsNone(demo.latitude)
        self.assertIsNone(demo.longitude)
        self.assertIsNone(demo.households)
        self.assertIsNone(demo.income_per_capita)
        self.assertIsNone(demo.poverty)
        self.assertIsNone(demo.employed_population)
        self.assertIsNone(demo.unemployed_population)
        self.assertIsNone(demo.housing_units)

    def test_default_source_name_used_when_not_provided_by_caller(self) -> None:
        # load_demographics() defaults source.get("name", "bigquery_demographics")
        # before calling fetch_bigquery_demographics - verify the source_name
        # argument (whatever it is) is what lands on each ZipDemographics.
        row = {"zip_code": "10001", "population": "1", "median_household_income": "1", "median_age": "1"}
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client([row])):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "bigquery_demographics")

        self.assertEqual(result["10001"].source, "bigquery_demographics")

    def test_multiple_rows_produce_multiple_entries(self) -> None:
        rows = [
            {"zip_code": "10001", "population": "1", "median_household_income": "1", "median_age": "1"},
            {"zip_code": "10002", "population": "2", "median_household_income": "2", "median_age": "2"},
        ]
        with patch.object(demographics, "_bigquery_client", return_value=self._fake_client(rows)):
            result = demographics.fetch_bigquery_demographics("proj", "SELECT 1", "src")

        self.assertEqual(set(result.keys()), {"10001", "10002"})


class ResolveBigqueryConnectionTests(unittest.TestCase):
    """resolve_bigquery_connection: source config falls back to storage
    config, and a relative credentials_json path (when supplied by the
    source) is resolved against config["_config_dir"]."""

    def test_uses_source_values_when_present(self) -> None:
        with patch.object(demographics, "load_storage_config", return_value={"project_id": "storage-proj"}):
            project_id, credentials_json = demographics.resolve_bigquery_connection(
                {"project_id": "source-proj", "credentials_json": "/abs/path/creds.json"},
                {"_config_dir": "/config/dir"},
            )
        self.assertEqual(project_id, "source-proj")
        self.assertEqual(credentials_json, "/abs/path/creds.json")

    def test_falls_back_to_storage_config_when_source_missing_values(self) -> None:
        with patch.object(
            demographics,
            "load_storage_config",
            return_value={"project_id": "storage-proj", "credentials_json": "storage-creds.json"},
        ):
            project_id, credentials_json = demographics.resolve_bigquery_connection(
                {}, {"_config_dir": "/config/dir"}
            )
        self.assertEqual(project_id, "storage-proj")
        # Storage-provided credentials_json is NOT joined against
        # _config_dir - only a source-provided relative path is, per the
        # `source.get("credentials_json") and credentials_json` guard.
        self.assertEqual(credentials_json, "storage-creds.json")

    def test_missing_project_id_everywhere_raises_value_error(self) -> None:
        with patch.object(demographics, "load_storage_config", return_value={}):
            with self.assertRaises(ValueError):
                demographics.resolve_bigquery_connection({}, {"_config_dir": "/config/dir"})

    def test_relative_source_credentials_path_resolved_against_config_dir(self) -> None:
        with patch.object(demographics, "load_storage_config", return_value={}):
            project_id, credentials_json = demographics.resolve_bigquery_connection(
                {"project_id": "proj", "credentials_json": "creds/service-account.json"},
                {"_config_dir": "/config/dir"},
            )
        self.assertEqual(project_id, "proj")
        self.assertEqual(credentials_json, str(__import__("pathlib").Path("/config/dir") / "creds/service-account.json"))

    def test_absolute_source_credentials_path_left_untouched(self) -> None:
        with patch.object(demographics, "load_storage_config", return_value={}):
            _, credentials_json = demographics.resolve_bigquery_connection(
                {"project_id": "proj", "credentials_json": "/already/absolute.json"},
                {"_config_dir": "/config/dir"},
            )
        self.assertEqual(credentials_json, "/already/absolute.json")


class LoadDemographicsTests(unittest.TestCase):
    """load_demographics: dispatches on source["type"], only "bigquery" is
    supported."""

    def test_bigquery_type_dispatches_to_resolve_and_fetch(self) -> None:
        config = {
            "demographics_source": {
                "type": "bigquery",
                "query": "SELECT * FROM demo",
                "name": "my_source",
            },
            "_config_dir": "/config/dir",
        }
        fake_result = {"10001": object()}
        with patch.object(
            demographics, "resolve_bigquery_connection", return_value=("proj", "/creds.json")
        ) as resolve, patch.object(
            demographics, "fetch_bigquery_demographics", return_value=fake_result
        ) as fetch:
            result = demographics.load_demographics(config)

        resolve.assert_called_once_with(config["demographics_source"], config)
        fetch.assert_called_once_with("proj", "SELECT * FROM demo", "my_source", "/creds.json")
        self.assertIs(result, fake_result)

    def test_bigquery_type_defaults_source_name_when_absent(self) -> None:
        config = {
            "demographics_source": {"type": "bigquery", "query": "SELECT 1"},
            "_config_dir": "/config/dir",
        }
        with patch.object(demographics, "resolve_bigquery_connection", return_value=("proj", None)), patch.object(
            demographics, "fetch_bigquery_demographics", return_value={}
        ) as fetch:
            demographics.load_demographics(config)

        fetch.assert_called_once_with("proj", "SELECT 1", "bigquery_demographics", None)

    def test_unsupported_source_type_raises_value_error(self) -> None:
        config = {"demographics_source": {"type": "csv"}, "_config_dir": "/config/dir"}
        with self.assertRaises(ValueError):
            demographics.load_demographics(config)


if __name__ == "__main__":
    unittest.main()
