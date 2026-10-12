# Puffy Growth Analytics Platform

A portfolio project simulating an e-commerce analytics platform, combining Shopify data ingestion, inventory reconciliation, customer and order validation, revenue integrity checks, and growth analytics foundations.

## Project Overview

The project explores how an e-commerce analytics team can integrate operational data, validate data quality, reconcile inventory, and prepare reliable datasets for business reporting.

The implemented workflows cover:

- **Inventory reconciliation:** Compare synthetic product inventory against a Shopify development store, identify discrepancies, and support controlled inventory synchronization.
- **Customer data validation:** Check customer identifiers, required fields, duplicates, date validity, numeric values, and marketing consent data types.
- **Order data validation:** Validate order and order-item identifiers, customer and product relationships, timestamps, statuses, quantities, and financial fields.
- **Revenue reconciliation:** Compare order-level item revenue against expected subtotals and validate net revenue using the financial rules defined by the synthetic dataset.
- **Automated testing:** Use pytest to test reconciliation logic, validation rules, and edge cases.

The project uses synthetic e-commerce datasets for local analytics and a Shopify development store for the inventory synchronization workflow. It is a portfolio simulation, not a claim of production deployment.

## Technology Stack

- Python 3.12
- Pandas
- Shopify Admin GraphQL API
- Requests and python-dotenv
- Pytest
- CSV-based data processing, reconciliation reports, and audit outputs
- Git and GitHub

Additional project areas include dbt, experimentation, dashboards, notebooks, and AI-related workflows. Their implementation status varies.

## Implemented Workflows

### 1. Shopify Inventory Reconciliation

The inventory reconciliation workflow compares a synthetic product catalogue against inventory quantities in a Shopify development store. The source CSV is treated as authoritative for this demonstration.

#### Verified results

| Metric | Result |
|---|---:|
| Products reconciled | 100 |
| Products matching after synchronization | 100 |
| Final match rate | 100% |
| Remaining quantity mismatches | 0 |
| Remaining exceptions | 0 |
| Mismatches corrected during synchronization | 99 |
| Absolute quantity variance before synchronization | 267,285 units |
| Absolute quantity variance after synchronization | 0 units |

These results describe the inventory test run performed on October 12, 2026. The source CSV was authoritative for the demo; these results do not establish the accuracy of live physical stock.

#### Workflow

1. Load source product inventory from CSV.
2. Retrieve Shopify products, variants, and inventory quantities.
3. Match records using SKU.
4. Detect quantity mismatches, missing or duplicate SKUs, untracked inventory, and missing inventory item IDs.
5. Generate a reconciliation report.
6. Apply quantity updates only when explicitly requested with `--apply`.
7. Record attempted updates in an audit log.

The default execution mode is a dry run and does not request inventory changes.

### 2. Customer Data Validation

The customer validation module checks the integrity and consistency of customer data before downstream analytics.

Checks include:

- Required columns and missing or blank values.
- Missing or duplicate customer IDs and hashed customer identifiers.
- Valid customer types, countries, and acquisition-source fields.
- Parseable first-purchase dates.
- Numeric, non-negative lifetime order counts and lifetime revenue.
- Valid boolean marketing opt-in values.

Missing loyalty tiers are permitted by the validation rules.

#### Verified results

| Metric | Result |
|---|---:|
| Customer records validated | 25,000 |
| Validation errors | 0 |
| Automated tests | 9 |

### 3. Order and Order-Item Validation

The order validation module checks order records and their relationships with customers, products, and order items.

Checks include:

- Required fields and missing or duplicate identifiers.
- Order-to-customer relationships.
- Item-to-order and item-to-product relationships.
- Parseable order timestamps.
- Valid order and fulfillment statuses.
- Numeric and non-negative order financial fields.
- Valid item quantities and monetary values.

Negative item gross margins are allowed because they can represent loss-making transactions.

#### Verified results

| Metric | Result |
|---|---:|
| Order records validated | 30,000 |
| Order-item records validated | 30,000 |
| Invalid customer, order, or product references found in the initial dataset checks | 0 |
| Validation errors | 0 |
| Automated tests | 11 |

### 4. Revenue Reconciliation

The revenue reconciliation module aggregates item-level revenue by order, joins it to order-level financial data, and flags differences outside a configurable tolerance.

For the synthetic dataset, the defined financial rules are:

**Expected item revenue**

`Subtotal - Discount`

**Expected net revenue**

`Subtotal - Discount + Shipping + Tax - Refund Amount`

These are the conventions defined by this project's synthetic dataset. Actual e-commerce accounting and revenue recognition can require additional rules depending on the business and its reporting requirements.

#### Verified results

| Metric | Result |
|---|---:|
| Orders analyzed | 30,000 |
| Orders without item records | 0 |
| Item revenue mismatches | 0 |
| Net revenue mismatches | 0 |
| Net revenue match rate across each order status | 100% |

The reconciliation covers paid, fulfilled, partially refunded, refunded, and cancelled orders.

#### Generated reports

The script `scripts/check_revenue_reconciliation.py` generates:

- `data/processed/revenue_reconciliation.csv` — detailed order-level reconciliation, expected values, differences, and match flags.
- `data/processed/revenue_reconciliation_summary.csv` — order counts, net revenue, refunds, and mismatch counts grouped by order status.

The reports are generated locally and the `data/processed/` directory is excluded from Git.

## Automated Testing

The complete test suite covers inventory reconciliation, customer validation, order validation, and revenue reconciliation.

| Test module | Tests |
|---|---:|
| Inventory reconciliation | 11 |
| Customer validation | 9 |
| Order validation | 11 |
| Revenue reconciliation | 5 |
| **Total** | **36** |

**Latest verified result: 36 tests passed.**

Run the full suite from the project root:

```bash
python -m pytest -q
```

## Repository Structure

```text
.
├── data/
│   ├── synthetic/       # Synthetic development datasets
│   └── processed/       # Generated outputs; excluded from Git
├── src/
│   ├── ingestion/       # Shopify ingestion and reconciliation
│   │   ├── reconcile_revenue.py
│   │   ├── validate_customers.py
│   │   ├── validate_orders.py
│   │   └── sync_shopify_inventory.py
│   ├── validation/      # Additional validation components
│   └── warehouse/      # Warehouse-related components
├── scripts/
│   └── check_revenue_reconciliation.py
├── tests/
│   ├── test_inventory_reconciliation.py
│   ├── test_customer_validation.py
│   ├── test_order_validation.py
│   └── test_revenue_reconciliation.py
├── dbt/                 # Analytics engineering work
├── dashboard/           # Dashboard work
├── experimentation/     # Experimentation work
├── notebooks/           # Analysis notebooks
├── ai/                  # AI-related project work
├── .env.example         # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

Requires Python 3.12 or a compatible Python environment.

1. Clone the repository:

   ```bash
   git clone https://github.com/purehibiscus/puffy-growth-analytics-platform.git
   cd puffy-growth-analytics-platform
   ```

2. Create and activate a virtual environment if needed.

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure `.env` from `.env.example` only if running the Shopify integration. Set the required development-store credentials and API version.

5. Ensure the development store, location, and required API permissions are configured before running inventory reconciliation.

**Security:** Never commit `.env`, access tokens, client secrets, or other credentials.

## Run Data Validation and Revenue Reconciliation

Run the full automated test suite:

```bash
python -m pytest -q
```

Generate the revenue reconciliation reports:

```bash
python scripts/check_revenue_reconciliation.py
```

The script reads the synthetic order and order-item CSV files and saves both reports under `data/processed/`.

## Run Inventory Reconciliation

Preview the inventory reconciliation without applying updates:

```bash
python -m src.ingestion.sync_shopify_inventory
```

Only after reviewing the report and confirming that the source quantities are appropriate should an authorized user explicitly run:

```bash
python -m src.ingestion.sync_shopify_inventory --apply
```

**Caution:** The `--apply` option changes inventory in the configured Shopify store. Use a development store and review the report before applying changes.

## Outputs and Auditability

Generated reconciliation reports and operational exports are stored under `data/processed/`, which is excluded from Git.

The inventory audit log records the run ID, timestamp, SKU, inventory item ID, original quantity, target quantity, quantity delta, and outcome for attempted updates.

Revenue reconciliation reports preserve the order-level inputs, expected financial values, differences, and match flags for investigation.

## Project Status

**Implemented and tested:**
- Shopify inventory reconciliation and controlled synchronization.
- Customer data validation.
- Order and order-item validation.
- Order-level revenue reconciliation and summary reporting.
- 36 automated tests passing.

**Additional development areas:** dbt analytics models, dashboards, experimentation, notebooks, and AI-related workflows have varying levels of implementation and should not be interpreted as fully deployed production services.

This project demonstrates data-quality engineering, financial consistency checks, operational reconciliation, and reproducible reporting using synthetic e-commerce data. It does not guarantee live inventory accuracy or establish that synthetic results generalize to a real business.

## Future Improvements

- Add data freshness and completeness monitoring.
- Introduce scheduled execution and CI-based test checks.
- Expand analytics models and documented business metrics using dbt.
- Develop growth, acquisition, retention, and experimentation dashboards.
- Add operational alerting and improve audit-log failure handling.
- Integrate approved customer and order APIs when the required permissions are available.
- Document data lineage, metric definitions, and production deployment considerations.
