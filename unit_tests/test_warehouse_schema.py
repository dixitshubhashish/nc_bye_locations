from __future__ import annotations

import unittest

from whitespace_tool.warehouse_bigquery import TABLE_PARTITION_SPECS, TABLE_SCHEMAS


class WarehouseSchemaTests(unittest.TestCase):
    def test_partition_fields_exist_in_table_schemas(self) -> None:
        for table_name, spec in TABLE_PARTITION_SPECS.items():
            schema_fields = {field["name"] for field in TABLE_SCHEMAS[table_name]}
            self.assertIn(
                spec["field"],
                schema_fields,
                f"{table_name} partitions on missing field {spec['field']}",
            )


if __name__ == "__main__":
    unittest.main()
