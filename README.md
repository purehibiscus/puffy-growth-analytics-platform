\# Puffy Growth Analytics Platform



A portfolio project simulating an analytics platform for an e-commerce business, combining Shopify data ingestion, inventory reconciliation, analytics engineering, and growth measurement.



\## Project Overview



The project explores how an e-commerce analytics team can integrate operational data, validate data quality, reconcile inventory, and prepare reliable datasets for business reporting.



The current implemented workflow focuses on Shopify inventory reconciliation using a synthetic product catalogue as the authoritative source for the demo store's inventory quantities.



\## Technology Stack



\- Python

\- Pandas

\- Shopify Admin GraphQL API

\- Requests and python-dotenv

\- Pytest

\- CSV-based reconciliation and audit outputs



Additional project areas include dbt, experimentation, dashboards, notebooks, and AI-related workflows; their implementation status varies.



\## Current Inventory Reconciliation Results



The inventory reconciliation workflow was tested against 100 synthetic products in a Shopify development store.



| Metric | Verified result |

|---|---:|

| Products reconciled | 100 |

| Products matching after synchronization | 100 |

| Final match rate | 100% |

| Quantity mismatches after synchronization | 0 |

| Exceptions requiring review after synchronization | 0 |

| Mismatches corrected during the synchronization run | 99 |

| Absolute quantity variance before synchronization | 267,285 units |

| Absolute quantity variance after synchronization | 0 units |

| Automated tests passing | 11 |



These results describe the test run performed on October 12, 2026. The source CSV was treated as authoritative for this demo; this does not establish that the source quantities represent live physical stock.



\## Inventory Reconciliation Workflow



1\. Load the source product inventory from CSV.

2\. Retrieve Shopify products, variants, and inventory quantities.

3\. Match records using SKU.

4\. Detect quantity mismatches, missing SKUs, duplicate SKUs, untracked inventory, and missing inventory items.

5\. Generate a reconciliation report.

6\. Apply quantity updates only when explicitly requested with `--apply`.

7\. Record attempted updates in an append-only CSV audit log.



The default execution mode is a dry run and does not request inventory changes.



\## Repository Structure



```text

.

â”œâ”€â”€ data/

â”‚   â”œâ”€â”€ synthetic/       # Synthetic inputs for development

â”‚   â””â”€â”€ processed/       # Generated outputs; excluded from Git

â”œâ”€â”€ src/

â”‚   â”œâ”€â”€ ingestion/       # Shopify ingestion and inventory sync

â”‚   â”œâ”€â”€ validation/      # Data validation components

â”‚   â””â”€â”€ warehouse/       # Warehouse-related components

â”œâ”€â”€ tests/               # Automated tests

â”œâ”€â”€ dbt/                 # Analytics engineering work

â”œâ”€â”€ dashboard/           # Dashboard work

â”œâ”€â”€ experimentation/     # Experimentation work

â”œâ”€â”€ notebooks/           # Analysis notebooks

â”œâ”€â”€ ai/                  # AI-related project work

â”œâ”€â”€ .env.example         # Environment variable template

â”œâ”€â”€ .gitignore

â”œâ”€â”€ requirements.txt

â””â”€â”€ README.md

```



\## Setup



Requires Python 3.12 or a compatible Python environment.



1\. Clone the repository.

2\. Create and activate a virtual environment.

3\. Install the dependencies:



```bash

python -m pip install -r requirements.txt

```



4\. Copy `.env.example` to `.env` and configure your Shopify development-store credentials and API version.

5\. Ensure the development store and location are configured for the inventory script before running it.



Never commit `.env`, access tokens, client secrets, or other credentials.



\## Run the Tests



```bash

python -m pytest tests/test\_inventory\_reconciliation.py -v

```



The current test suite covers matching quantities, mismatches, missing and duplicate SKUs, inventory tracking, missing inventory item IDs, invalid source quantities, and audit-log behavior.



\## Run Inventory Reconciliation



Preview the reconciliation without applying inventory updates:



```bash

python -m src.ingestion.sync\_shopify\_inventory

```



Only after reviewing the report and confirming that the source quantities are appropriate should an authorized user explicitly run:



```bash

python -m src.ingestion.sync\_shopify\_inventory --apply

```



\*\*Caution:\*\* `--apply` changes inventory in the configured Shopify store. Use a development store and review the report before applying changes.



\## Outputs and Auditability



Generated reconciliation reports and operational exports are stored under `data/processed/`, which is excluded from Git.



The inventory audit log records the run ID, timestamp, SKU, inventory item ID, original quantity, target quantity, quantity delta, and outcome for attempted updates.



\## Project Status



The inventory reconciliation workflow and its 11 automated tests are implemented and passing. Other folders represent additional project work and should not be interpreted as fully implemented production services.



This is a portfolio simulation, not a claim of production deployment or a guarantee of live inventory accuracy.



\## Future Improvements



\- Add freshness and completeness monitoring.

\- Expand automated data-quality tests.

\- Build analytics models and documented business metrics.

\- Develop growth, acquisition, and experimentation dashboards.

\- Add CI checks and deployment documentation.

\- Improve operational alerting and audit-log failure handling.
