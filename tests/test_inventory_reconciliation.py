
import pandas as pd
import pytest

from src.ingestion.sync_shopify_inventory import build_reconciliation


def source_data(sku="SKU-001", quantity=10):
    return pd.DataFrame([{
        "sku": sku,
        "inventory_qty": quantity,
        "product_name": "Test Product",
    }])


def shopify_data(
    sku="SKU-001",
    quantity=10,
    tracked=True,
    inventory_item_id="gid://shopify/InventoryItem/1",
):
    return pd.DataFrame([{
        "sku": sku,
        "shopify_product_id": "gid://shopify/Product/1",
        "shopify_product_title": "Test Product",
        "shopify_variant_id": "gid://shopify/ProductVariant/1",
        "inventory_item_id": inventory_item_id,
        "shopify_available_qty": quantity,
        "tracked": tracked,
    }])


def test_matching_inventory():
    result = build_reconciliation(
        source_data(quantity=10),
        shopify_data(quantity=10),
    )
    assert result.loc[0, "status"] == "MATCH"
    assert result.loc[0, "quantity_difference"] == 0


def test_quantity_mismatch():
    result = build_reconciliation(
        source_data(quantity=15),
        shopify_data(quantity=10),
    )
    assert result.loc[0, "status"] == "MISMATCH"
    assert result.loc[0, "quantity_difference"] == 5


def test_missing_sku_in_shopify():
    result = build_reconciliation(
        source_data(sku="SKU-002"),
        shopify_data(sku="SKU-001"),
    )
    assert result.loc[0, "status"] == "MISSING_IN_SHOPIFY"


def test_duplicate_sku_in_shopify():
    shopify = pd.concat(
        [shopify_data(), shopify_data()],
        ignore_index=True,
    )
    result = build_reconciliation(source_data(), shopify)
    assert result.loc[0, "status"] == "DUPLICATE_SHOPIFY_SKU"


def test_untracked_inventory():
    result = build_reconciliation(
        source_data(),
        shopify_data(tracked=False),
    )
    assert result.loc[0, "status"] == "INVENTORY_NOT_TRACKED"


def test_missing_inventory_item():
    result = build_reconciliation(
        source_data(),
        shopify_data(inventory_item_id=""),
    )
    assert result.loc[0, "status"] == "MISSING_INVENTORY_ITEM"


def test_negative_source_quantity_rejected():
    with pytest.raises(ValueError, match="negative inventory"):
        build_reconciliation(
            source_data(quantity=-1),
            shopify_data(),
        )


def test_blank_source_sku_rejected():
    with pytest.raises(ValueError, match="missing or blank SKUs"):
        build_reconciliation(
            source_data(sku=" "),
            shopify_data(),
        )


def test_duplicate_source_sku_rejected():
    source = pd.concat(
        [source_data(), source_data()],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="Duplicate source SKUs"):
        build_reconciliation(source, shopify_data())


from src.ingestion.sync_shopify_inventory import append_audit_log
import src.ingestion.sync_shopify_inventory as inventory_sync


def test_audit_log_records_inventory_change(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory_sync, "OUTPUT_DIR", tmp_path)

    row = pd.Series({
        "sku": "TEST-001",
        "inventory_item_id": "test-item-1",
        "shopify_available_qty": 5,
        "inventory_qty": 12,
    })

    append_audit_log("test-run-1", row, "UPDATED")

    log = pd.read_csv(tmp_path / "inventory_audit_log.csv")

    assert len(log) == 1
    assert log.loc[0, "sku"] == "TEST-001"
    assert log.loc[0, "original_quantity"] == 5
    assert log.loc[0, "target_quantity"] == 12
    assert log.loc[0, "quantity_delta"] == 7
    assert log.loc[0, "outcome"] == "UPDATED"


def test_audit_log_appends_records(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory_sync, "OUTPUT_DIR", tmp_path)

    row = pd.Series({
        "sku": "TEST-002",
        "inventory_item_id": "test-item-2",
        "shopify_available_qty": 3,
        "inventory_qty": 8,
    })

    append_audit_log("run-1", row, "UPDATED")
    append_audit_log("run-2", row, "UPDATE_FAILED")

    log = pd.read_csv(tmp_path / "inventory_audit_log.csv")

    assert len(log) == 2
    assert list(log["run_id"]) == ["run-1", "run-2"]
    assert list(log["outcome"]) == ["UPDATED", "UPDATE_FAILED"]


def test_missing_inventory_level_at_location():
    result = build_reconciliation(
        source_data(),
        shopify_data(quantity=None),
    )
    assert result.loc[0, "status"] == "NO_INVENTORY_LEVEL_AT_LOCATION"


def test_set_inventory_handles_shopify_rejection(monkeypatch):
    monkeypatch.setattr(
        inventory_sync,
        "graphql_request",
        lambda access_token, query: {
            "data": {
                "inventorySetQuantities": {
                    "userErrors": [{
                        "field": ["quantities"],
                        "message": "The quantity changed before the update.",
                    }],
                    "inventoryAdjustmentGroup": None,
                }
            }
        },
    )

    row = pd.Series({
        "sku": "TEST-001",
        "shopify_available_qty": 5,
        "source_inventory_qty": 12,
        "inventory_item_id": "gid://shopify/InventoryItem/1",
    })

    result = inventory_sync.set_inventory("fake-token", row, "test-run")

    assert result.startswith("UPDATE_REJECTED:")


def test_set_inventory_handles_missing_mutation_result(monkeypatch):
    monkeypatch.setattr(
        inventory_sync,
        "graphql_request",
        lambda access_token, query: {"data": {}},
    )

    row = pd.Series({
        "sku": "TEST-001",
        "shopify_available_qty": 5,
        "source_inventory_qty": 12,
        "inventory_item_id": "gid://shopify/InventoryItem/1",
    })

    result = inventory_sync.set_inventory("fake-token", row, "test-run")

    assert result == "UPDATE_FAILED: Missing mutation result."


def test_set_inventory_uses_compare_and_set_quantities(monkeypatch):
    captured = {}

    def fake_graphql_request(access_token, query):
        captured["query"] = query
        return {
            "data": {
                "inventorySetQuantities": {
                    "userErrors": [],
                    "inventoryAdjustmentGroup": {
                        "createdAt": "2026-10-15T00:00:00Z",
                        "reason": "correction",
                        "changes": [{
                            "name": "available",
                            "delta": 7,
                            "quantityAfterChange": 12,
                        }],
                    },
                }
            }
        }

    monkeypatch.setattr(
        inventory_sync,
        "graphql_request",
        fake_graphql_request,
    )

    row = pd.Series({
        "sku": "TEST-001",
        "shopify_available_qty": 5,
        "source_inventory_qty": 12,
        "inventory_item_id": "gid://shopify/InventoryItem/1",
    })

    result = inventory_sync.set_inventory("fake-token", row, "test-run")

    assert result == "UPDATED"
    assert "changeFromQuantity: 5" in captured["query"]
    assert "quantity: 12" in captured["query"]
    assert "gid://shopify/InventoryItem/1" in captured["query"]