from __future__ import annotations
import pandas as pd

_DEMO_TABLES = pd.DataFrame({
    "full_name":         ["main.analytics.customers", "main.analytics.orders",
                          "main.analytics.transactions", "main.staging.raw_events"],
    "catalog_name":      ["main", "main", "main", "main"],
    "schema_name":       ["analytics", "analytics", "analytics", "staging"],
    "table_name":        ["customers", "orders", "transactions", "raw_events"],
    "table_description": [
        "Deduplicated customer master — one row per customer_id.",
        "Orders with customer foreign key reference.",
        "Transaction-level detail enriched with customer data.",
        "Raw event stream ingested from upstream systems.",
    ],
    "table_type":        ["MANAGED", "MANAGED", "EXTERNAL", "EXTERNAL"],
    "updated_at":        [pd.Timestamp.now() - pd.Timedelta(days=1),
                          pd.Timestamp.now() - pd.Timedelta(hours=5),
                          pd.Timestamp.now() - pd.Timedelta(minutes=30),
                          pd.Timestamp.now() - pd.Timedelta(days=3)],
})

_DEMO_COLUMNS = {
    "main.analytics.customers": pd.DataFrame({
        "column_name": ["customer_id", "email", "segment", "created_at"],
        "data_type":   ["BIGINT", "STRING", "STRING", "TIMESTAMP"],
        "comment":     ["Primary key.", "Customer email address.",
                        "Marketing segment label.", "Account creation timestamp."],
    }),
    "main.analytics.orders": pd.DataFrame({
        "column_name": ["order_id", "customer_id", "amount", "order_date"],
        "data_type":   ["BIGINT", "BIGINT", "DECIMAL(18,2)", "DATE"],
        "comment":     ["Unique order identifier.", "FK to customers.customer_id.",
                        "Order total in USD.", "Date the order was placed."],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "column_name": ["transaction_id", "order_id", "customer_id", "amount", "type"],
        "data_type":   ["BIGINT", "BIGINT", "BIGINT", "DECIMAL(18,2)", "STRING"],
        "comment":     ["Transaction PK.", "FK to orders.", "FK to customers.",
                        "Transaction amount.", "DEBIT or CREDIT."],
    }),
    "main.staging.raw_events": pd.DataFrame({
        "column_name": ["event_id", "customer_id", "event_type", "ts"],
        "data_type":   ["STRING", "BIGINT", "STRING", "TIMESTAMP"],
        "comment":     ["Unique event identifier.", "Customer associated with event.",
                        "Event classification (click, view, purchase).", "Event timestamp."],
    }),
}

_DEMO_GRANTS = {
    "main.analytics.customers": pd.DataFrame({
        "principal": ["finance_dept_id", "all_employees_id", "SELECT_ALL_USERS"],
        "privilege":  ["SELECT",          "SELECT",           "SELECT"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "principal": ["finance_dept_id", "SELECT_ALL_USERS"],
        "privilege":  ["SELECT",          "SELECT"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "principal": ["finance_dept_id"],
        "privilege":  ["SELECT"],
    }),
    "main.staging.raw_events": pd.DataFrame({
        "principal": ["all_employees_id"],
        "privilege":  ["SELECT"],
    }),
}

_DEMO_LINEAGE = {
    "main.analytics.customers": pd.DataFrame({
        "direction":        ["UPSTREAM", "UPSTREAM",                  "DOWNSTREAM"],
        "entity_full_name": ["main.staging.raw_events",
                             "main.bronze.customer_raw",              # not in authorized set → locked node
                             "main.analytics.orders"],
        "entity_type":      ["TABLE",    "TABLE",                     "TABLE"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "direction":        ["UPSTREAM",                    "DOWNSTREAM"],
        "entity_full_name": ["main.analytics.customers",   "main.analytics.transactions"],
        "entity_type":      ["TABLE",                       "TABLE"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "direction":        ["UPSTREAM"],
        "entity_full_name": ["main.analytics.orders"],
        "entity_type":      ["TABLE"],
    }),
    "main.staging.raw_events": pd.DataFrame(
        columns=["direction", "entity_full_name", "entity_type"]
    ),
}

_DEMO_RELATED = {
    "main.analytics.customers": pd.DataFrame({
        "full_name":    ["main.analytics.orders",     "main.analytics.transactions"],
        "table_name":   ["orders",                    "transactions"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Same schema",               "Shared column"],
    }),
    "main.analytics.orders": pd.DataFrame({
        "full_name":    ["main.analytics.customers",  "main.analytics.transactions"],
        "table_name":   ["customers",                 "transactions"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Same schema",               "Same schema"],
    }),
    "main.analytics.transactions": pd.DataFrame({
        "full_name":    ["main.analytics.customers",  "main.analytics.orders"],
        "table_name":   ["customers",                 "orders"],
        "catalog_name": ["main",                      "main"],
        "schema_name":  ["analytics",                 "analytics"],
        "relationship": ["Shared column",             "Same schema"],
    }),
    "main.staging.raw_events": pd.DataFrame(
        columns=["full_name", "table_name", "catalog_name", "schema_name", "relationship"]
    ),
}

_DEMO_GLOSSARY = pd.DataFrame({
    "term": ["Churn Rate", "Customer Lifetime Value (CLV)", "Monthly Recurring Revenue (MRR)", "Active User"],
    "definition": [
        "The percentage of customers who stop using your product or service during a given time period.",
        "The total amount of money a customer is expected to spend with your business during their lifetime.",
        "The total amount of predictable revenue that a company expects to receive every month.",
        "A user who has performed at least one meaningful action within the product in the last 30 days."
    ],
    "calculation": [
        "(Customers lost during period / Total customers at start of period) * 100",
        "Average Purchase Value * Average Purchase Frequency * Average Customer Lifespan",
        "Sum of all subscription revenues from active customers in a month",
        "COUNT(DISTINCT user_id) WHERE last_action_ts >= CURRENT_DATE - INTERVAL 30 DAYS"
    ],
    "domain": ["Sales & Marketing", "Finance", "Finance", "Product"],
    "steward": ["Jane Doe (Marketing)", "John Smith (Finance)", "John Smith (Finance)", "Alice Wong (Product)"],
    "related_tables": [
        ["main.analytics.customers", "main.analytics.orders"],
        ["main.analytics.customers", "main.analytics.transactions"],
        ["main.analytics.transactions"],
        ["main.staging.raw_events"]
    ]
})
