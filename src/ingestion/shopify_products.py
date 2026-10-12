"""
Shopify Product Ingestion
=========================

Reads synthetic product data from CSV and creates products
in a Shopify development store using the Admin GraphQL API.

Source CSV columns:

    product_id
    product_name
    category
    product_type
    vendor
    price
    cost
    sku
    inventory_qty
    rating
    review_count
    created_at
    status

Pipeline:

CSV
 ↓
Python validation
 ↓
Shopify GraphQL productCreate
 ↓
Shopify Product
 ↓
Shopify GraphQL productVariantsBulkCreate
 ↓
Product Variant
 ↓
Price + SKU + Cost
 ↓
Source-to-Shopify Mapping CSV

Author: Abbas Nadani Ahmad
Project: Puffy Growth Analytics Platform
"""

from pathlib import Path
import time
import os

import pandas as pd
import requests
from dotenv import load_dotenv
import argparse


# ============================================================
# 1. PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

PRODUCTS_FILE = DATA_DIR / "products.csv"

MAPPING_FILE = (
    OUTPUT_DIR / "shopify_product_mapping.csv"
)


# ============================================================
# 2. LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv(
    PROJECT_ROOT / ".env"
)

SHOPIFY_STORE_DOMAIN = os.getenv(
    "SHOPIFY_STORE_DOMAIN"
)

SHOPIFY_CLIENT_ID = os.getenv(
    "SHOPIFY_CLIENT_ID"
)

SHOPIFY_CLIENT_SECRET = os.getenv(
    "SHOPIFY_CLIENT_SECRET"
)

SHOPIFY_API_VERSION = os.getenv(
    "SHOPIFY_API_VERSION",
    "2026-07",
)


# ============================================================
# 3. VALIDATE ENVIRONMENT
# ============================================================

required_variables = {
    "SHOPIFY_STORE_DOMAIN":
        SHOPIFY_STORE_DOMAIN,

    "SHOPIFY_CLIENT_ID":
        SHOPIFY_CLIENT_ID,

    "SHOPIFY_CLIENT_SECRET":
        SHOPIFY_CLIENT_SECRET,

    "SHOPIFY_API_VERSION":
        SHOPIFY_API_VERSION,
}

missing_variables = [
    name
    for name, value in required_variables.items()
    if not value
]

if missing_variables:

    raise RuntimeError(
        "Missing environment variables: "
        + ", ".join(missing_variables)
    )


# ============================================================
# 4. SHOPIFY GRAPHQL ENDPOINT
# ============================================================

GRAPHQL_URL = (
    f"https://{SHOPIFY_STORE_DOMAIN}"
    f"/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
)


# ============================================================
# 5. GET ACCESS TOKEN
# ============================================================

def get_access_token() -> str:
    """
    Obtain an Admin API access token.

    Credentials are never printed.
    """

    token_url = (
        f"https://{SHOPIFY_STORE_DOMAIN}"
        "/admin/oauth/access_token"
    )

    payload = {
        "client_id":
            SHOPIFY_CLIENT_ID,

        "client_secret":
            SHOPIFY_CLIENT_SECRET,

        "grant_type":
            "client_credentials",
    }

    response = requests.post(
        token_url,
        json=payload,
        timeout=30,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "Shopify authentication failed.\n"
            f"HTTP status: "
            f"{response.status_code}\n"
            f"Response: "
            f"{response.text}"
        )

    response_data = response.json()

    access_token = (
        response_data.get(
            "access_token"
        )
    )

    if not access_token:

        raise RuntimeError(
            "Shopify authentication succeeded "
            "but no access_token was returned.\n"
            f"Response: {response_data}"
        )

    return access_token


# ============================================================
# 6. GRAPHQL REQUEST HELPER
# ============================================================

def graphql_request(
    access_token: str,
    query: str,
    variables: dict | None = None,
) -> dict:
    """
    Execute a Shopify Admin GraphQL request.

    Retries only temporary transport and HTTP failures.
    GraphQL user errors are returned immediately and never retried.
    """

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token,
    }

    payload = {
        "query": query,
        "variables": variables or {},
    }

    retryable_status_codes = {
        429,
        500,
        502,
        503,
    }

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                GRAPHQL_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )

        except requests.RequestException as error:
            if attempt == max_attempts:
                raise RuntimeError(
                    "Shopify GraphQL request failed after "
                    f"{max_attempts} attempts: {error}"
                ) from error

            wait_seconds = 2 ** (attempt - 1)

            print(
                "    Temporary network failure. "
                f"Retrying in {wait_seconds} second(s)..."
            )

            time.sleep(wait_seconds)
            continue

        if response.status_code == 200:
            break

        if (
            response.status_code in retryable_status_codes
            and attempt < max_attempts
        ):
            wait_seconds = 2 ** (attempt - 1)

            retry_after = response.headers.get("Retry-After")

            if retry_after:
                try:
                    wait_seconds = max(
                        wait_seconds,
                        float(retry_after),
                    )
                except ValueError:
                    pass

            print(
                f"    Shopify returned HTTP "
                f"{response.status_code}. Retrying in "
                f"{wait_seconds} second(s)..."
            )

            time.sleep(wait_seconds)
            continue

        raise RuntimeError(
            "Shopify GraphQL request failed.\n"
            f"HTTP status: {response.status_code}\n"
            f"Response: {response.text}"
        )

    response_data = response.json()

    if response_data.get("errors"):
        raise RuntimeError(
            "GraphQL returned errors:\n"
            + str(response_data["errors"])
        )

    return response_data

    # --------------------------------------------------------
    # GraphQL-level errors
    # --------------------------------------------------------

    if response_data.get("errors"):

        raise RuntimeError(
            "GraphQL returned errors:\n"
            + str(
                response_data["errors"]
            )
        )

    return response_data


# ============================================================
# 7. PRODUCT CREATE MUTATION
# ============================================================

PRODUCT_CREATE_MUTATION = """
mutation ProductCreate(
    $product: ProductCreateInput!
) {

    productCreate(
        product: $product
    ) {

        product {
            id
            title
            handle
            productType
            vendor
            status
            tags

            variants(first: 1) {
                nodes {
                    id
                    title
                    price
                    sku

                    inventoryItem {
                        id
                        sku
                        tracked
                        unitCost {
                            amount
                            currencyCode
                        }
                    }
                }
            }
        }

        userErrors {
            field
            message
        }
    }
}
"""
# ============================================================
# 8. PRODUCT VARIANT BULK CREATE MUTATION
# ============================================================
PRODUCT_VARIANTS_BULK_UPDATE_MUTATION = """
mutation ProductVariantsBulkUpdate(
    $productId: ID!,
    $variants: [ProductVariantsBulkInput!]!
) {
    productVariantsBulkUpdate(
        productId: $productId
        variants: $variants
    ) {
        productVariants {
            id
            title
            price
            sku
        }
        userErrors {
            field
            message
        }
    }
}
"""

# ============================================================
# 9. BUILD PRODUCT INPUT
# ============================================================

def build_product_input(
    row: pd.Series,
) -> dict:
    """
    Convert one CSV row into Shopify
    ProductCreateInput.

    Mapping:

    product_name → title
    category     → tags
    product_type → productType
    vendor       → vendor
    status       → status
    """

    product_name = row.get(
        "product_name"
    )

    if pd.isna(product_name):

        raise ValueError(
            "product_name is empty."
        )

    title = str(
        product_name
    ).strip()

    if not title:

        raise ValueError(
            "product_name is empty."
        )

    product_input = {
        "title": title,
    }

    # --------------------------------------------------------
    # Product type
    # --------------------------------------------------------

    product_type = row.get(
        "product_type"
    )

    if pd.notna(product_type):

        product_type_value = str(
            product_type
        ).strip()

        if product_type_value:

            product_input[
                "productType"
            ] = product_type_value

    # --------------------------------------------------------
    # Vendor
    # --------------------------------------------------------

    vendor = row.get(
        "vendor"
    )

    if pd.notna(vendor):

        vendor_value = str(
            vendor
        ).strip()

        if vendor_value:

            product_input[
                "vendor"
            ] = vendor_value

    # --------------------------------------------------------
    # Category → Shopify tag
    # --------------------------------------------------------

    category = row.get(
        "category"
    )

    if pd.notna(category):

        category_value = str(
            category
        ).strip()

        if category_value:

            product_input[
                "tags"
            ] = [
                category_value
            ]

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------
    status = row.get(
        "status"
    )

    if pd.notna(status):

        status_value = (
            str(status)
            .strip()
            .upper()
        )

        allowed_statuses = {
            "ACTIVE",
            "DRAFT",
            "ARCHIVED",
        }

        if status_value in allowed_statuses:

            product_input[
                "status"
            ] = status_value

    return product_input
# ============================================================
# 10. BUILD VARIANT INPUT
# ============================================================

def build_variant_input(
    row: pd.Series,
) -> dict:
    """
    Convert CSV pricing/SKU/cost data into
    ProductVariantsBulkInput.

    Mapping:

    price → variant.price

    sku   → variant.inventoryItem.sku

    cost  → variant.inventoryItem.cost
    """

    variant_input = {}

    # --------------------------------------------------------
    # Price
    # --------------------------------------------------------

    price = row.get(
        "price"
    )

    if pd.notna(price):

        try:

            price_value = float(
                price
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                f"Invalid price for product "
                f"{row.get('product_id')}: "
                f"{price}"
            )

        if price_value < 0:

            raise ValueError(
                f"Price cannot be negative "
                f"for product "
                f"{row.get('product_id')}: "
                f"{price_value}"
            )

        variant_input[
            "price"
        ] = f"{price_value:.2f}"

    # --------------------------------------------------------
    # Inventory item
    # --------------------------------------------------------

    inventory_item = {}

    # --------------------------------------------------------
    # SKU
    # --------------------------------------------------------

    sku = row.get(
        "sku"
    )

    if pd.notna(sku):

        sku_value = str(
            sku
        ).strip()

        if sku_value:

            inventory_item[
                "sku"
            ] = sku_value

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    cost = row.get(
        "cost"
    )

    if pd.notna(cost):

        try:

            cost_value = float(
                cost
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                f"Invalid cost for product "
                f"{row.get('product_id')}: "
                f"{cost}"
            )

        if cost_value < 0:

            raise ValueError(
                f"Cost cannot be negative "
                f"for product "
                f"{row.get('product_id')}: "
                f"{cost_value}"
            )

        inventory_item[
            "cost"
        ] = f"{cost_value:.2f}"

    # --------------------------------------------------------
    # Track inventory
    # --------------------------------------------------------

    inventory_item[
        "tracked"
    ] = True

    if inventory_item:

        variant_input[
            "inventoryItem"
        ] = inventory_item

    return variant_input
# ============================================================
# 11. CREATE PRODUCT
# ============================================================

def create_product(
    access_token: str,
    product_input: dict,
) -> dict:
    """
    Create a Shopify product using productCreate.

    productCreate does NOT accept a variants field in
    ProductCreateInput for API version 2026-07.

    The product is created first. Variant configuration
    happens separately.
    """

    variables = {
        "product":
            product_input
    }

    response = graphql_request(
        access_token=access_token,
        query=PRODUCT_CREATE_MUTATION,
        variables=variables,
    )

    product_create = (
        response
        .get("data", {})
        .get("productCreate")
    )

    if not product_create:

        raise RuntimeError(
            "Shopify returned no "
            "productCreate response."
        )

    user_errors = (
        product_create.get(
            "userErrors",
            []
        )
    )

    if user_errors:

        raise RuntimeError(
            "Shopify productCreate userErrors:\n"
            + str(user_errors)
        )

    product = (
        product_create.get(
            "product"
        )
    )

    if not product:

        raise RuntimeError(
            "Shopify returned no product object."
        )

    return product
# ============================================================
# 12. CREATE PRODUCT VARIANT
# ============================================================

def update_default_product_variant(
    access_token: str,
    product_id: str,
    default_variant_id: str,
    variant_input: dict,
) -> dict:
    """Update Shopify's automatically created default variant."""

    variant_input = variant_input.copy()
    variant_input["id"] = default_variant_id

    response = graphql_request(
        access_token=access_token,
        query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
        variables={
            "productId": product_id,
            "variants": [variant_input],
        },
    )

    variant_update = (
        response.get("data", {})
        .get("productVariantsBulkUpdate")
    )

    if not variant_update:
        raise RuntimeError(
            "Shopify returned no productVariantsBulkUpdate response."
        )

    if variant_update.get("userErrors"):
        raise RuntimeError(
            "Shopify productVariantsBulkUpdate userErrors:\n"
            + str(variant_update["userErrors"])
        )

    variants = variant_update.get("productVariants", [])

    if not variants:
        raise RuntimeError("Shopify returned no product variant.")

    return variants[0]

# ============================================================
# 13. LOAD PRODUCTS CSV
# ============================================================

def load_products() -> pd.DataFrame:
    """
    Load and validate products.csv using
    the exact 13-column schema.
    """

    if not PRODUCTS_FILE.exists():

        raise FileNotFoundError(
            "Product CSV not found:\n"
            f"{PRODUCTS_FILE}"
        )

    df = pd.read_csv(
        PRODUCTS_FILE
    )

    if df.empty:

        raise ValueError(
            "products.csv is empty."
        )

    required_columns = [
        "product_id",
        "product_name",
        "category",
        "product_type",
        "vendor",
        "price",
        "cost",
        "sku",
        "inventory_qty",
        "rating",
        "review_count",
        "created_at",
        "status",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Missing required columns "
            "in products.csv:\n"
            + ", ".join(
                missing_columns
            )
            + "\n\nAvailable columns:\n"
            + ", ".join(
                df.columns
            )
        )

    validate_product_data(df)
    return df

def validate_product_data(df: pd.DataFrame) -> None:
    """Validate product values before sending any record to Shopify."""

    errors = []

    required_text_columns = [
        "product_id",
        "product_name",
        "sku",
    ]

    for column in required_text_columns:
        invalid = (
            df[column].isna()
            | df[column].astype(str).str.strip().eq("")
        )

        if invalid.any():
            errors.append(
                f"{column} has {invalid.sum()} blank value(s)."
            )

    numeric_rules = {
        "price": lambda values: values >= 0,
        "cost": lambda values: values >= 0,
        "inventory_qty": lambda values: values >= 0,
        "rating": lambda values: values.between(0, 5),
        "review_count": lambda values: values >= 0,
    }

    for column, rule in numeric_rules.items():
        numeric_values = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        invalid = numeric_values.isna() | ~rule(numeric_values)

        if invalid.any():
            errors.append(
                f"{column} has {invalid.sum()} invalid value(s)."
            )

    duplicate_skus = df[
        df["sku"].astype(str).str.strip().duplicated(
            keep=False
        )
    ]["sku"].dropna().unique()

    if len(duplicate_skus):
        errors.append(
            "SKU values must be unique. Duplicates: "
            + ", ".join(
                map(str, duplicate_skus[:10])
            )
        )

    valid_statuses = {
        "ACTIVE",
        "DRAFT",
        "ARCHIVED",
    }

    normalized_statuses = (
        df["status"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    invalid_statuses = (
        ~normalized_statuses.isin(valid_statuses)
    )

    if invalid_statuses.any():
        errors.append(
            "status contains unsupported value(s): "
            + ", ".join(
                sorted(
                    normalized_statuses[
                        invalid_statuses
                    ].unique()
                )
            )
        )

    if errors:
        raise ValueError(
            "Product data-quality validation failed:\n- "
            + "\n- ".join(errors)
        )


# ============================================================
# 14. INGEST PRODUCTS
# ============================================================
def load_existing_mapping() -> pd.DataFrame:
    """Load the prior source-to-Shopify mapping, if one exists."""

    if not MAPPING_FILE.exists():
        return pd.DataFrame()

    mapping_df = pd.read_csv(MAPPING_FILE)

    required_columns = {
        "source_product_id",
        "ingestion_status",
    }

    missing_columns = required_columns - set(mapping_df.columns)

    if missing_columns:
        raise ValueError(
            "Existing mapping is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    return mapping_df


def get_successful_source_product_ids(
    mapping_df: pd.DataFrame,
) -> set[str]:
    """Return source IDs that were already ingested successfully."""

    if mapping_df.empty:
        return set()

    successful_rows = mapping_df[
        mapping_df["ingestion_status"] == "SUCCESS"
    ]

    return set(
        successful_rows["source_product_id"]
        .dropna()
        .astype(str)
    )

def ingest_products(
    access_token: str,
    df: pd.DataFrame,
    successful_source_product_ids: set[str] | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Create products and their initial variants.
    Already-successful source IDs are skipped to prevent duplicates.
    """

    df = df.copy()
    successful_source_product_ids = (
        successful_source_product_ids or set()
    )
    source_product_ids = df["product_id"].astype(str)
    pending_df = df[
        ~source_product_ids.isin(
            successful_source_product_ids
        )
    ].copy()
    skipped = len(df) - len(pending_df)
    if limit is not None:
        df = pending_df.head(limit).copy()
    else:
        df = pending_df
    results = []
    total = len(df)

    print()

    print("=" * 70)
    print("SHOPIFY PRODUCT INGESTION")
    print("=" * 70)

    print(
        f"Products to process: "
        f"{total}"
    )

    print()

    if skipped:
        print(
            f"Skipped - already ingested: {skipped}"
        )

    # --------------------------------------------------------
    # Process products
    # --------------------------------------------------------

    for position, (
        index,
        row
    ) in enumerate(
        df.iterrows(),
        start=1,
    ):

        source_product_id = row.get(
            "product_id",
            index,
        )

        product_name = str(
            row.get(
                "product_name",
                "",
            )
        ).strip()

        print(
            f"[{position}/{total}] "
            f"Creating: "
            f"{product_name}"
        )

        try:

            # ------------------------------------------------
            # Build product payload
            # ------------------------------------------------

            product_input = (
                build_product_input(
                    row
                )
            )

            # ------------------------------------------------
            # Create product
            # ------------------------------------------------

            product = create_product(
                access_token=access_token,
                product_input=product_input,
            )

            shopify_product_id = (
                product.get("id")
            )

            print(
                "    Product created."
            )

            print(
                "    Shopify Product ID: "
                f"{shopify_product_id}"
            )

            # ------------------------------------------------
            # Build variant payload
            # ------------------------------------------------

            variant_input = (
                build_variant_input(
                    row
                )
            )

            # ------------------------------------------------
            # Create/configure variant
            # ------------------------------------------------

            default_variant_id = product["variants"]["nodes"][0]["id"]

            variant = update_default_product_variant(
                access_token=access_token,
                product_id=shopify_product_id,
                default_variant_id=default_variant_id,
                variant_input=variant_input,
            )

            shopify_variant_id = (
                variant.get("id")
            )

            print(
                "    Variant created."
            )

            print(
                "    Shopify Variant ID: "
                f"{shopify_variant_id}"
            )

            # ------------------------------------------------
            # Save mapping
            # ------------------------------------------------

            result = {

                # Source
                "source_product_id":
                    source_product_id,

                "source_product_name":
                    product_name,

                # Shopify product
                "shopify_product_id":
                    shopify_product_id,

                "shopify_product_title":
                    product.get(
                        "title"
                    ),

                "shopify_handle":
                    product.get(
                        "handle"
                    ),

                "shopify_product_type":
                    product.get(
                        "productType"
                    ),

                "shopify_vendor":
                    product.get(
                        "vendor"
                    ),

                "shopify_status":
                    product.get(
                        "status"
                    ),

                # Shopify variant
                "shopify_variant_id":
                    shopify_variant_id,

                "shopify_variant_title":
                    variant.get(
                        "title"
                    ),

                "shopify_variant_price":
                    variant.get(
                        "price"
                    ),

                "shopify_variant_sku":
                    variant.get(
                        "sku"
                    ),

                # Source analytics fields
                "source_category":
                    row.get(
                        "category"
                    ),

                "source_price":
                    row.get(
                        "price"
                    ),

                "source_cost":
                    row.get(
                        "cost"
                    ),

                "source_sku":
                    row.get(
                        "sku"
                    ),

                "source_inventory_qty":
                    row.get(
                        "inventory_qty"
                    ),

                "source_rating":
                    row.get(
                        "rating"
                    ),

                "source_review_count":
                    row.get(
                        "review_count"
                    ),

                "source_created_at":
                    row.get(
                        "created_at"
                    ),

                "source_status":
                    row.get(
                        "status"
                    ),

                # Pipeline
                "ingestion_status":
                    "SUCCESS",

                "error":
                    None,
            }

            results.append(
                result
            )

            print(
                "    SUCCESS"
            )

        except Exception as error:

            print(
                "    FAILED: "
                f"{error}"
            )

            results.append({

                "source_product_id":
                    source_product_id,

                "source_product_name":
                    product_name,

                "shopify_product_id":
                    None,

                "shopify_product_title":
                    None,

                "shopify_handle":
                    None,

                "shopify_product_type":
                    None,

                "shopify_vendor":
                    None,

                "shopify_status":
                    None,

                "shopify_variant_id":
                    None,

                "shopify_variant_title":
                    None,

                "shopify_variant_price":
                    None,

                "shopify_variant_sku":
                    None,

                "source_category":
                    row.get(
                        "category"
                    ),

                "source_price":
                    row.get(
                        "price"
                    ),

                "source_cost":
                    row.get(
                        "cost"
                    ),

                "source_sku":
                    row.get(
                        "sku"
                    ),

                "source_inventory_qty":
                    row.get(
                        "inventory_qty"
                    ),

                "source_rating":
                    row.get(
                        "rating"
                    ),

                "source_review_count":
                    row.get(
                        "review_count"
                    ),

                "source_created_at":
                    row.get(
                        "created_at"
                    ),

                "source_status":
                    row.get(
                        "status"
                    ),

                "ingestion_status":
                    "FAILED",

                "error":
                    str(error),
            })

        # ----------------------------------------------------
        # Small pause between requests
        # ----------------------------------------------------

        time.sleep(
            0.5
        )

    return pd.DataFrame(
        results
    )


# ============================================================
# 15. SAVE MAPPING
# ============================================================

def save_mapping(
    existing_mapping_df: pd.DataFrame,
    new_mapping_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge newly attempted records into the existing mapping.
    A new result replaces an older result for the same source ID.
    """
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    if existing_mapping_df.empty:
        combined_mapping_df = new_mapping_df.copy()
    elif new_mapping_df.empty:
        combined_mapping_df = existing_mapping_df.copy()
    else:
        new_source_ids = set(
            new_mapping_df["source_product_id"]
            .astype(str)
        )
        retained_existing_df = existing_mapping_df[
            ~existing_mapping_df["source_product_id"]
            .astype(str)
            .isin(new_source_ids)
        ]
        combined_mapping_df = pd.concat(
            [
                retained_existing_df,
                new_mapping_df,
            ],
            ignore_index=True,
        )
    if not combined_mapping_df.empty:
        combined_mapping_df = (
            combined_mapping_df
            .drop_duplicates(
                subset=["source_product_id"],
                keep="last",
            )
        )
    combined_mapping_df.to_csv(
        MAPPING_FILE,
        index=False,
    )
    print()
    print("=" * 70)
    print("MAPPING FILE SAVED")
    print("=" * 70)
    print(MAPPING_FILE)
    return combined_mapping_df


# ============================================================
# 16. MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Ingest synthetic products into Shopify."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help=(
            "Maximum number of not-yet-ingested products "
            "to process. Default: 1."
        ),
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1.")

    print()

    print("=" * 70)
    print("PUFFY GROWTH ANALYTICS PLATFORM")
    print("Shopify Product Ingestion")
    print("=" * 70)

    print()

    print(
        f"Store: "
        f"{SHOPIFY_STORE_DOMAIN}"
    )

    print(
        f"API version: "
        f"{SHOPIFY_API_VERSION}"
    )

    print(
        f"Product CSV: "
        f"{PRODUCTS_FILE}"
    )

    # ========================================================
    # LOAD CSV
    # ========================================================

    df = load_products()
    existing_mapping_df = load_existing_mapping()
    successful_source_product_ids = (
        get_successful_source_product_ids(
            existing_mapping_df
        )
    )

    print()

    print(
        f"Loaded "
        f"{len(df):,} products "
        "from CSV."
    )

    print()

    print(
        "CSV columns:"
    )

    for column in df.columns:

        print(
            f"  - {column}"
        )

    # ========================================================
    # AUTHENTICATE
    # ========================================================

    print()

    print(
        "Authenticating with Shopify..."
    )

    access_token = (
        get_access_token()
    )

    print(
        "Authentication successful."
    )

    # ========================================================
    # TEST MODE
    # ========================================================
    #
    # IMPORTANT:
    #
    # Start with ONE product.
    #
    # After the first product succeeds,
    # change:
    #
    #     limit=1
    #
    # to:
    #
    #     limit=None
    #
    # ========================================================

    new_mapping_df = ingest_products(
        access_token=access_token,
        df=df,
        successful_source_product_ids=successful_source_product_ids,
        limit=args.limit,
    )

    # ========================================================
    # SAVE MAPPING
    # ========================================================

    mapping_df = save_mapping(
        existing_mapping_df=existing_mapping_df,
        new_mapping_df=new_mapping_df,
    )
    # ========================================================
    # SUMMARY
    # ========================================================
    successful = (
        mapping_df[
            "ingestion_status"
        ]
        == "SUCCESS"
    ).sum()

    failed = (
        mapping_df[
            "ingestion_status"
        ]
        == "FAILED"
    ).sum()

    print()

    print("=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)

    print(
        f"Successful: "
        f"{successful}"
    )

    print(
        f"Failed:     "
        f"{failed}"
    )

    print(
        f"Total:      "
        f"{len(mapping_df)}"
    )

    print()

    if failed:

        print(
            "Review the 'error' column in:"
        )

        print(
            MAPPING_FILE
        )

    else:

        print(
            "Product ingestion completed successfully."
        )


# ============================================================
# 17. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()