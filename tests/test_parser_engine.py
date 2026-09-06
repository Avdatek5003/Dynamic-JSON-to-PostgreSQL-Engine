import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from parser_engine import PostgreSQLConverterEngine


@pytest.fixture
def engine():
    #Bu unit testlerde gerçek PostgreSQL bağlantısı kullanılmıyor sorun yok
    return PostgreSQLConverterEngine(
        {
            "dbname": "test",
            "user": "test",
            "password": "test",
            "host": "localhost",
            "port": "5432",
        }
    )


def test_identifier_normalization(engine):
    assert engine.identifier_duzelt("Customer Data") == "customer_data"
    assert engine.identifier_duzelt("postal-code") == "postal_code"
    assert engine.identifier_duzelt("order id") == "order_id"
    assert engine.identifier_duzelt("123-value") == "field_123_value"


def test_identifier_has_postgresql_length_limit(engine):
    long_name = "a" * 100

    result = engine.identifier_duzelt(long_name)

    assert len(result) <= 63
    assert result != long_name


def test_type_inference(engine):
    assert engine.sql_tipi_belirle(True) == "BOOLEAN"
    assert engine.sql_tipi_belirle(10) == "BIGINT"
    assert engine.sql_tipi_belirle(10.5) == "NUMERIC"
    assert engine.sql_tipi_belirle("text") == "TEXT"
    assert engine.sql_tipi_belirle(None) is None


def test_type_reconciliation(engine):
    assert engine.tipleri_birlestir("BIGINT", "BIGINT") == "BIGINT"
    assert engine.tipleri_birlestir("BIGINT", "NUMERIC") == "NUMERIC"
    assert engine.tipleri_birlestir("BIGINT", "TEXT") == "TEXT"
    assert engine.tipleri_birlestir(None, "BOOLEAN") == "BOOLEAN"


def test_nested_object_flattening(engine):
    data = {
        "name": "Ahmet",
        "shipping address": {
            "city": "Kocaeli",
            "postal-code": "41000",
        },
    }

    result = engine.sozlugu_duzlestir(data)

    assert result["name"] == "Ahmet"
    assert result["shipping_address_city"] == "Kocaeli"
    assert result["shipping_address_postal_code"] == "41000"


def test_nested_arrays_generate_child_tables(engine):
    data = {
        "customer data": {
            "name": "Ahmet",
            "orders": [
                {
                    "order id": 1001,
                    "items": [
                        {
                            "product-name": "Keyboard",
                            "quantity": 1,
                        },
                        {
                            "product-name": "Mouse",
                            "quantity": 2,
                        },
                    ],
                }
            ],
        }
    }

    engine.process_data(
        "json",
        data
    )

    expected_tables = {
        "json",
        "json_customer_data_orders",
        "json_customer_data_orders_items",
    }

    assert expected_tables.issubset(
        engine.veritabani_semasi.keys()
    )


def test_child_table_contains_foreign_key_metadata(engine):
    data = {
        "orders": [
            {
                "order id": 1001
            }
        ]
    }

    engine.process_data(
        "customer",
        data
    )

    child_schema = engine.veritabani_semasi[
        "customer_orders"
    ]

    assert "customer_id" in child_schema["sutunlar"]

    assert {
        "ust_tablo": "customer",
        "ya_sutunu": "customer_id",
    } in child_schema["yabanci_anahtarlar"]


def test_primitive_array_is_converted_to_rows(engine):
    data = {
        "tags": [
            "python",
            "postgresql",
            "json"
        ]
    }

    engine.process_data(
        "project",
        data
    )

    assert "project_tags" in engine.veritabani_semasi

    tag_records = [
        record
        for table_name, record
        in engine.eklenecek_kayitlar
        if table_name == "project_tags"
    ]

    assert len(tag_records) == 3

    assert {
        record["deger"]
        for record in tag_records
    } == {
        "python",
        "postgresql",
        "json",
    }


def test_clear_state(engine):
    engine.process_data(
        "example",
        {
            "name": "test"
        }
    )

    assert engine.veritabani_semasi
    assert engine.eklenecek_kayitlar

    engine.clear_state()

    assert engine.veritabani_semasi == {}
    assert engine.eklenecek_kayitlar == []