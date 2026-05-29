"""
Test dataset generator for the Data Dictionary (research-funding organisation).

Produces a DuckDB file that the app reads when DUCKDB_PATH is set.
The generated file is excluded from git via the existing *.duckdb gitignore rule.

Usage:
    python scripts/generate_test_data.py                        # 800 tables → data/test_data.duckdb
    python scripts/generate_test_data.py --seed 42              # reproducible run
    python scripts/generate_test_data.py --tables 200           # smaller subset
    python scripts/generate_test_data.py --dept finance         # single department
    python scripts/generate_test_data.py --out data/custom.duckdb
    python scripts/generate_test_data.py --with-data            # create actual row data for Preview

Set in .env to activate:
    DUCKDB_PATH=data/test_data.duckdb
"""
from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

# ── constants ─────────────────────────────────────────────────────────────────

CATALOG   = "research_org"
DEPT_SCHEMAS = {
    "finance":  "finance",
    "research": "research",
    "hr":       "hr",
    "it":       "it",
}
DEPT_PRINCIPALS = {
    "finance":  "finance_group",
    "research": "research_group",
    "hr":       "hr_group",
    "it":       "it_group",
}
STEWARDS = {
    "finance":  "finance.steward@research-org.ca",
    "research": "research.steward@research-org.ca",
    "hr":       "hr.steward@research-org.ca",
    "it":       "it.steward@research-org.ca",
}

# ── table name pools ──────────────────────────────────────────────────────────

_FINANCE_TABLES = [
    ("grant_awards",                "Awarded grants with funding amounts and sponsor details"),
    ("budget_periods",              "Fiscal budget periods and allocation windows"),
    ("expenditure_lines",           "Individual expenditure line items against grants"),
    ("invoice_register",            "Vendor and sub-recipient invoices received"),
    ("payroll_runs",                "Bi-weekly payroll run records for grant-funded staff"),
    ("overhead_rates",              "Negotiated indirect cost and overhead rates by year"),
    ("cost_recovery_statements",    "Monthly cost recovery statements per project"),
    ("sub_award_agreements",        "Sub-award and sub-contract agreements"),
    ("indirect_cost_proposals",     "Indirect cost rate proposals submitted to sponsors"),
    ("audit_findings",              "Internal and external audit findings and resolutions"),
    ("vendor_contracts",            "Procurement contracts with external vendors"),
    ("travel_advance_requests",     "Staff travel advance requests and reconciliations"),
    ("equipment_purchases",         "Capital equipment purchases charged to grants"),
    ("fringe_benefit_rates",        "Employer fringe benefit rates applied to salaries"),
    ("fund_balances",               "Running fund balances by account and cost center"),
    ("cost_center_hierarchy",       "Organisational cost center tree"),
    ("account_codes",               "Chart of accounts used for grant expenditures"),
    ("payment_schedules",           "Scheduled payment milestones to sponsors"),
    ("financial_reports",           "Financial progress reports submitted to funders"),
    ("budget_amendments",           "Budget reallocation requests and approvals"),
    ("encumbrances",                "Committed but unspent funds (purchase orders)"),
    ("journal_entries",             "Manual journal entries and corrections"),
    ("cash_receipts",               "Cash and wire transfer receipts from sponsors"),
    ("foreign_currency_transactions", "Transactions in non-CAD currencies with FX rates"),
    ("grant_closeout_checklist",    "Final closeout tasks for expiring grants"),
    ("cost_sharing_commitments",    "Institutional cost-sharing commitments"),
    ("pre_award_budgets",           "Draft budgets at proposal stage"),
    ("no_cost_extensions",          "Approved no-cost extension requests"),
    ("sponsor_contacts",            "Key contacts at funding agencies"),
    ("funding_agency_requirements", "Special financial requirements per agency"),
    ("indirect_cost_exemptions",    "Items exempted from indirect cost calculation"),
    ("salary_effort_reports",       "Effort certification for grant-funded personnel"),
    ("audit_schedule",              "Planned audit dates and audit types"),
    ("grant_renewals",              "Renewal applications for expiring grants"),
    ("facilities_costs",            "Facilities usage charges by department"),
    ("subaward_monitoring_log",     "Monitoring activities for sub-recipients"),
    ("procurement_orders",          "Purchase orders raised against grants"),
    ("revenue_recognition",         "Revenue recognition schedule per grant"),
    ("tax_exempt_certificates",     "Tax exemption certificates by jurisdiction"),
    ("carryforward_balances",       "Approved carryforward of unspent funds"),
    ("cash_flow_projections",       "30-60-90 day cash flow forecasts"),
    ("grant_portfolio_summary",     "Aggregated portfolio view of all active grants"),
    ("sponsor_reporting_calendar",  "Upcoming financial report due dates"),
    ("expenditure_categories",      "Allowed expenditure categories per grant type"),
    ("funder_classifications",      "Classification of funders (federal, provincial, tri-council, etc.)"),
    ("project_account_mapping",     "Mapping of projects to GL account numbers"),
    ("internal_transfers",          "Internal fund transfers between departments"),
    ("advance_account_usage",       "Use of institutional advance accounts"),
    ("disallowed_costs_log",        "Costs flagged as disallowed by auditors"),
    ("grant_modification_requests", "Formal modification requests sent to sponsors"),
]

_RESEARCH_TABLES = [
    ("grant_applications",          "Grant applications submitted to funding agencies"),
    ("research_projects",           "Active and completed research projects"),
    ("project_milestones",          "Key milestones and deliverables per project"),
    ("publications",                "Peer-reviewed publications and preprints"),
    ("citation_metrics",            "Citation counts and h-index per publication"),
    ("ethics_protocols",            "Research ethics board protocols"),
    ("consent_forms",               "Participant informed consent form versions"),
    ("lab_inventory",               "Laboratory equipment and consumables inventory"),
    ("sample_registry",             "Biological and physical sample tracking"),
    ("instrument_bookings",         "Core facility instrument booking logs"),
    ("data_repositories",           "Research data repositories and DOIs"),
    ("collaboration_agreements",    "MOU and collaboration agreements with partners"),
    ("conference_presentations",    "Conference talks, posters, and workshops"),
    ("technical_reports",           "Internal technical and progress reports"),
    ("peer_review_assignments",     "Journal and grant peer review assignments"),
    ("research_methods",            "Standard operating procedures and methods"),
    ("data_management_plans",       "Data management plan versions per project"),
    ("open_access_compliance",      "Open access mandate compliance tracking"),
    ("research_datasets",           "Curated research datasets with metadata"),
    ("protocol_amendments",         "Amendments to approved ethics protocols"),
    ("principal_investigators",     "Registered principal investigators and their affiliations"),
    ("co_investigator_roles",       "Co-investigator assignments per project"),
    ("knowledge_translation",       "Knowledge translation and impact activities"),
    ("research_areas",              "Research area and discipline classifications"),
    ("funding_opportunity_tracker", "Funding opportunity leads and deadlines"),
    ("proposal_review_scores",      "Internal proposal review scores pre-submission"),
    ("animal_use_protocols",        "Animal care and use protocols"),
    ("biosafety_records",           "Biosafety level assessments and approvals"),
    ("field_study_logs",            "Field study location, date, and conditions"),
    ("reagent_orders",              "Ordered reagents and chemical tracking"),
    ("experiment_runs",             "Individual experiment run metadata"),
    ("sequencing_runs",             "Genomic and proteomic sequencing runs"),
    ("survey_instruments",          "Research survey questionnaires and versions"),
    ("interview_logs",              "Qualitative interview session logs"),
    ("focus_group_sessions",        "Focus group participant and session records"),
    ("systematic_reviews",          "Systematic review and meta-analysis projects"),
    ("research_software",           "Research software tools developed internally"),
    ("ip_disclosures",              "Intellectual property disclosures"),
    ("patent_applications",         "Patent applications arising from research"),
    ("spin_off_companies",          "Spin-off companies and commercialisation records"),
    ("research_training_grants",    "Grants specifically for trainee support"),
    ("postdoc_projects",            "Postdoctoral research project assignments"),
    ("graduate_theses",             "Graduate student thesis projects"),
    ("external_collaborators",      "External collaborator and visiting researcher records"),
    ("research_infrastructure",     "Major research infrastructure and platforms"),
    ("clinical_trial_registrations","Clinical trial registration identifiers"),
    ("regulatory_submissions",      "Regulatory body submissions (Health Canada, etc.)"),
    ("impact_assessments",          "Research impact and societal benefit assessments"),
    ("media_coverage",              "Press and media coverage of research outputs"),
    ("award_recognitions",          "Awards and prizes received for research"),
]

_HR_TABLES = [
    ("employees",                   "All current and former employees"),
    ("positions",                   "Approved positions and FTE allocations"),
    ("employment_contracts",        "Signed employment contracts by type"),
    ("leave_requests",              "Annual, sick, and special leave requests"),
    ("payroll_deductions",          "Employee payroll deductions and contributions"),
    ("benefits_enrollment",         "Health, dental, and pension plan enrollments"),
    ("performance_reviews",         "Annual and mid-year performance reviews"),
    ("training_completions",        "Mandatory and optional training completions"),
    ("job_postings",                "Internal and external job postings"),
    ("applicants",                  "Job applicants and recruitment pipeline"),
    ("onboarding_tasks",            "New hire onboarding task checklists"),
    ("graduate_students",           "Registered graduate students (MSc, PhD)"),
    ("postdoctoral_fellows",        "Postdoctoral fellow appointments"),
    ("visiting_scholars",           "Visiting researcher and scholar appointments"),
    ("compensation_bands",          "Salary bands by level and classification"),
    ("organizational_units",        "Department and unit hierarchy"),
    ("offboarding_records",         "Employee departure records and exit surveys"),
    ("accommodation_requests",      "Workplace accommodation requests"),
    ("disciplinary_records",        "Disciplinary actions (HR eyes only)"),
    ("union_grievances",            "Collective agreement grievance filings"),
    ("collective_agreements",       "Signed collective agreement documents"),
    ("probation_reviews",           "Probation period review outcomes"),
    ("reference_checks",            "Reference check notes for candidates"),
    ("interview_panels",            "Interview panel composition per posting"),
    ("equity_diversity_data",       "Voluntary self-identification data"),
    ("workplace_injuries",          "Workplace health and safety incidents"),
    ("overtime_approvals",          "Approved overtime hours by manager"),
    ("remote_work_agreements",      "Remote and hybrid work agreements"),
    ("tuition_reimbursements",      "Tuition assistance reimbursement requests"),
    ("employee_recognitions",       "Peer and manager recognition awards"),
    ("succession_planning",         "Identified successors for key roles"),
    ("talent_pool",                 "High-potential employee development pool"),
    ("secondment_agreements",       "Internal and external secondment records"),
    ("retiree_records",             "Retirement dates and pension elections"),
    ("reference_letter_log",        "Reference letters issued by the organisation"),
    ("hr_policies",                 "HR policy documents and version history"),
    ("classification_reviews",      "Position reclassification requests and outcomes"),
    ("flex_time_arrangements",      "Flexible work schedule arrangements"),
    ("childcare_support_claims",    "Childcare benefit and subsidy claims"),
    ("wellness_program_participation", "Employee wellness program enrollments"),
    ("staff_publications",          "Publications by non-research staff"),
    ("researcher_affiliations",     "Faculty and researcher departmental affiliations"),
    ("visiting_appointments",       "Adjunct and clinical appointment records"),
    ("honorary_appointments",       "Honorary degree and appointment records"),
    ("volunteer_activities",        "Staff volunteering and community engagement"),
    ("internship_placements",       "Student internship and co-op placements"),
    ("mentor_pairs",                "Formal mentoring relationship assignments"),
    ("career_development_plans",    "Individual development plan records"),
    ("exit_interview_themes",       "Anonymised themes from exit interviews"),
]

_IT_TABLES = [
    ("systems_inventory",           "All IT systems, servers, and appliances"),
    ("software_licenses",           "Software license entitlements and usage"),
    ("helpdesk_tickets",            "IT support tickets and resolutions"),
    ("security_incidents",          "Information security incidents and responses"),
    ("user_accounts",               "Active directory and application user accounts"),
    ("network_devices",             "Network switches, routers, and access points"),
    ("backup_jobs",                 "Scheduled and ad-hoc backup job logs"),
    ("etl_pipelines",               "ETL and data integration pipeline definitions"),
    ("api_registry",                "Internal and external API endpoints"),
    ("monitoring_alerts",           "Infrastructure and application monitoring alerts"),
    ("data_classifications",        "Data sensitivity and classification labels"),
    ("vulnerability_scans",         "Automated vulnerability scan results"),
    ("patch_events",                "Operating system and application patch history"),
    ("capacity_planning",           "Storage, compute, and network capacity forecasts"),
    ("sla_agreements",              "Service level agreements with internal clients"),
    ("cloud_resources",             "Cloud (AWS/Azure) resource inventory and costs"),
    ("access_reviews",              "Periodic user access privilege reviews"),
    ("data_governance_policies",    "Data governance policy documents and versions"),
    ("pipeline_run_logs",           "Individual ETL pipeline execution logs"),
    ("data_lineage_graph",          "Captured data lineage edges between tables"),
    ("change_management_requests",  "IT change request approvals"),
    ("disaster_recovery_tests",     "DR test exercises and results"),
    ("certificate_inventory",       "TLS/SSL certificate expiry tracking"),
    ("firewall_rules",              "Network firewall rule sets"),
    ("vpn_usage_logs",              "VPN connection session logs"),
    ("endpoint_compliance",         "Laptop and desktop compliance status"),
    ("shadow_it_detections",        "Unauthorised software and cloud service usage"),
    ("data_retention_schedule",     "Data retention periods by classification"),
    ("privacy_impact_assessments",  "Privacy impact assessments for new systems"),
    ("vendor_security_assessments", "Third-party security assessments"),
    ("storage_usage_stats",         "Storage consumption by department and project"),
    ("network_traffic_stats",       "Aggregated network traffic metrics"),
    ("application_performance",     "Application response time and error metrics"),
    ("database_usage_metrics",      "Database size, query counts, and slow queries"),
    ("identity_federation",         "IdP federation configurations and trust relationships"),
    ("mfa_enrollment",              "Multi-factor authentication enrollment status"),
    ("phishing_simulations",        "Phishing simulation campaigns and click rates"),
    ("data_loss_prevention_events", "DLP policy violation events"),
    ("privileged_access_log",       "Privileged account usage audit log"),
    ("server_decommission_log",     "Decommissioned server records"),
    ("ip_address_allocations",      "IP address space allocations"),
    ("dns_records",                 "Internal and external DNS record inventory"),
    ("service_catalog",             "IT service catalog with request procedures"),
    ("configuration_baselines",     "Approved configuration baselines per system type"),
    ("software_eol_tracker",        "Software end-of-life and upgrade deadlines"),
    ("devops_pipelines",            "CI/CD pipeline definitions and run history"),
    ("container_registry",          "Docker container image registry"),
    ("api_usage_metrics",           "API call volumes and latency by endpoint"),
    ("data_catalog_sync_log",       "Data catalog synchronisation job history"),
    ("rbac_role_definitions",       "Role-based access control role definitions"),
]

# ── column vocabulary ─────────────────────────────────────────────────────────

_COMMON_COLS = [
    ("created_at",          "TIMESTAMP", "Row creation timestamp"),
    ("updated_at",          "TIMESTAMP", "Last modification timestamp"),
    ("created_by",          "VARCHAR",   "Email of the user who created this record"),
    ("updated_by",          "VARCHAR",   "Email of the user who last updated this record"),
    ("status",              "VARCHAR",   "Record status (active, inactive, archived)"),
    ("notes",               "VARCHAR",   "Free-text notes"),
    ("is_deleted",          "BOOLEAN",   "Soft-delete flag"),
    ("version",             "INTEGER",   "Optimistic lock version counter"),
    ("external_reference",  "VARCHAR",   "Reference identifier in an external system"),
    ("source_system",       "VARCHAR",   "Originating system for this record"),
    ("data_quality_flag",   "VARCHAR",   "Data quality check result (PASS/WARN/FAIL)"),
    ("approved_by",         "VARCHAR",   "Email of approving authority"),
    ("approval_date",       "DATE",      "Date approval was granted"),
    ("effective_date",      "DATE",      "Date from which this record is effective"),
    ("expiry_date",         "DATE",      "Date on which this record expires"),
    ("fiscal_year",         "INTEGER",   "Fiscal year (e.g. 2025)"),
    ("fiscal_period",       "INTEGER",   "Fiscal period within the year (1–12)"),
    ("currency",            "VARCHAR",   "ISO 4217 currency code"),
    ("country_code",        "VARCHAR",   "ISO 3166-1 alpha-2 country code"),
    ("region",              "VARCHAR",   "Geographic or administrative region"),
    ("department_id",       "BIGINT",    "FK → organizational_units.department_id"),
    ("comments",            "VARCHAR",   "Additional comments from the submitter"),
    ("attachments_count",   "INTEGER",   "Number of attached documents"),
    ("last_reviewed_at",    "TIMESTAMP", "Date of last manual review"),
    ("reviewed_by",         "VARCHAR",   "Email of last reviewer"),
]

_FINANCE_COLS = [
    ("grant_id",            "VARCHAR",      "FK → grant_awards.grant_id"),
    ("fund_code",           "VARCHAR",      "General ledger fund code"),
    ("account_code",        "VARCHAR",      "Chart of accounts GL code"),
    ("cost_center_id",      "VARCHAR",      "Cost center identifier"),
    ("vendor_id",           "BIGINT",       "FK → vendor_contracts.vendor_id"),
    ("amount_cad",          "DECIMAL(18,2)","Amount in Canadian dollars"),
    ("amount_usd",          "DECIMAL(18,2)","Amount in US dollars"),
    ("indirect_rate",       "DOUBLE",       "Indirect cost rate applied (0.0–1.0)"),
    ("direct_cost",         "DECIMAL(18,2)","Direct costs before indirect"),
    ("indirect_cost",       "DECIMAL(18,2)","Calculated indirect cost amount"),
    ("total_cost",          "DECIMAL(18,2)","Total cost including indirect"),
    ("award_number",        "VARCHAR",      "Sponsor-assigned award number"),
    ("sponsor_id",          "BIGINT",       "FK → sponsor_contacts.sponsor_id"),
    ("invoice_number",      "VARCHAR",      "Vendor invoice number"),
    ("payment_date",        "DATE",         "Date payment was issued"),
    ("cheque_number",       "VARCHAR",      "Physical or electronic cheque number"),
    ("budget_line",         "VARCHAR",      "Budget line category (salary, travel, etc.)"),
    ("expenditure_type",    "VARCHAR",      "Expenditure classification code"),
    ("fringe_rate",         "DOUBLE",       "Fringe benefit rate applied"),
    ("overhead_rate",       "DOUBLE",       "Overhead rate for this cost center"),
    ("recovery_amount",     "DECIMAL(18,2)","Amount recovered from this transaction"),
    ("outstanding_balance", "DECIMAL(18,2)","Remaining uncommitted balance"),
    ("project_id",          "VARCHAR",      "FK → research_projects.project_id"),
    ("sub_award_id",        "VARCHAR",      "FK → sub_award_agreements.sub_award_id"),
    ("audit_status",        "VARCHAR",      "Audit review status (pending, cleared, flagged)"),
    ("cash_flow_date",      "DATE",         "Expected cash inflow or outflow date"),
    ("reconciliation_status","VARCHAR",     "Bank reconciliation status"),
    ("tax_exempt",          "BOOLEAN",      "Whether this transaction is tax-exempt"),
    ("withholding_amount",  "DECIMAL(18,2)","Withholding tax amount"),
    ("po_number",           "VARCHAR",      "Purchase order number"),
    ("encumbrance_amount",  "DECIMAL(18,2)","Amount encumbered but not yet spent"),
    ("carryforward_approved","BOOLEAN",     "Whether carryforward to next year was approved"),
    ("effort_percent",      "DOUBLE",       "Percentage of effort charged to this grant"),
    ("fte_charged",         "DOUBLE",       "FTE equivalent charged to this fund"),
    ("reporting_period",    "VARCHAR",      "Financial reporting period label"),
    ("amendment_number",    "INTEGER",      "Sequential budget amendment number"),
    ("disallowed_amount",   "DECIMAL(18,2)","Amount flagged as disallowed by auditors"),
    ("journal_entry_id",    "VARCHAR",      "Reference to source journal entry"),
]

_RESEARCH_COLS = [
    ("project_id",          "VARCHAR",   "FK → research_projects.project_id"),
    ("grant_id",            "VARCHAR",   "FK → grant_awards.grant_id"),
    ("researcher_id",       "BIGINT",    "FK → principal_investigators.researcher_id"),
    ("pi_email",            "VARCHAR",   "Principal investigator email"),
    ("ethics_protocol_id",  "VARCHAR",   "FK → ethics_protocols.protocol_id"),
    ("publication_doi",     "VARCHAR",   "Digital Object Identifier"),
    ("journal_name",        "VARCHAR",   "Journal or conference name"),
    ("impact_factor",       "DOUBLE",    "Journal impact factor at time of publication"),
    ("citation_count",      "INTEGER",   "Total citations as of last update"),
    ("h_index",             "INTEGER",   "Author h-index at time of publication"),
    ("open_access",         "BOOLEAN",   "Whether the publication is open access"),
    ("preprint_url",        "VARCHAR",   "URL of preprint (arXiv, bioRxiv, etc.)"),
    ("sample_id",           "VARCHAR",   "FK → sample_registry.sample_id"),
    ("experiment_id",       "VARCHAR",   "FK → experiment_runs.experiment_id"),
    ("data_size_gb",        "DOUBLE",    "Size of associated dataset in GB"),
    ("research_area",       "VARCHAR",   "Primary research area or discipline"),
    ("keywords",            "VARCHAR",   "Comma-separated keyword list"),
    ("methodology",         "VARCHAR",   "Research methodology used"),
    ("funding_agency",      "VARCHAR",   "Name of the funding agency"),
    ("tri_council_program", "VARCHAR",   "CIHR/NSERC/SSHRC program name if applicable"),
    ("project_start_date",  "DATE",      "Project start date"),
    ("project_end_date",    "DATE",      "Project end date"),
    ("collaborating_institution","VARCHAR","Name of partner institution"),
    ("data_sharing_agreement","BOOLEAN", "Whether a data sharing agreement is in place"),
    ("ethics_status",       "VARCHAR",   "Ethics approval status (pending, approved, expired)"),
    ("animal_use",          "BOOLEAN",   "Whether animal subjects are involved"),
    ("human_subjects",      "BOOLEAN",   "Whether human subjects are involved"),
    ("biosafety_level",     "INTEGER",   "Biosafety containment level (1–4)"),
    ("sequencing_platform", "VARCHAR",   "Sequencing instrument model"),
    ("genome_assembly",     "VARCHAR",   "Reference genome assembly version"),
    ("clinical_trial_id",   "VARCHAR",   "ClinicalTrials.gov or ISRCTN identifier"),
    ("grant_type",          "VARCHAR",   "Grant type (operating, equipment, training, etc.)"),
    ("total_award_value",   "DECIMAL(18,2)","Total dollar value of the award"),
    ("publication_year",    "INTEGER",   "Year of publication"),
    ("language",            "VARCHAR",   "Language of the publication or dataset"),
    ("country_of_study",    "VARCHAR",   "Primary country where research was conducted"),
    ("tech_readiness_level","INTEGER",   "Technology readiness level (1–9)"),
    ("ip_disclosed",        "BOOLEAN",   "Whether IP disclosure was filed"),
]

_HR_COLS = [
    ("employee_id",         "BIGINT",    "FK → employees.employee_id"),
    ("researcher_id",       "BIGINT",    "FK → principal_investigators.researcher_id (if applicable)"),
    ("manager_id",          "BIGINT",    "FK → employees.employee_id (manager)"),
    ("position_id",         "BIGINT",    "FK → positions.position_id"),
    ("contract_type",       "VARCHAR",   "Employment type (permanent, fixed-term, casual, etc.)"),
    ("employment_start",    "DATE",      "Employment start date"),
    ("employment_end",      "DATE",      "Employment end date (null if current)"),
    ("salary_band",         "VARCHAR",   "Compensation band identifier"),
    ("annual_salary",       "DECIMAL(18,2)","Annual base salary in CAD"),
    ("fte",                 "DOUBLE",    "Full-time equivalent (0.0–1.0)"),
    ("leave_days_taken",    "DOUBLE",    "Leave days taken in the current period"),
    ("leave_balance",       "DOUBLE",    "Remaining leave balance in days"),
    ("performance_score",   "DOUBLE",    "Performance review score (1.0–5.0)"),
    ("training_hours",      "DOUBLE",    "Mandatory training hours completed this year"),
    ("union_member",        "BOOLEAN",   "Whether the employee is in a bargaining unit"),
    ("collective_agreement","VARCHAR",   "Applicable collective agreement code"),
    ("hire_source",         "VARCHAR",   "How the candidate was sourced (job board, referral, etc.)"),
    ("probation_end_date",  "DATE",      "End of probationary period"),
    ("citizenship_status",  "VARCHAR",   "Work authorization status"),
    ("work_location",       "VARCHAR",   "Primary work location (campus, remote, hybrid)"),
    ("classification_code", "VARCHAR",   "Position classification code"),
    ("step_level",          "INTEGER",   "Step within the salary band"),
    ("vacation_entitlement","INTEGER",   "Annual vacation days entitlement"),
    ("benefit_plan_code",   "VARCHAR",   "Benefits plan enrollment code"),
    ("pension_plan",        "VARCHAR",   "Pension plan (HOOPP, CAAT, RRSP, etc.)"),
    ("tuition_approved",    "BOOLEAN",   "Whether tuition reimbursement was approved"),
    ("security_clearance",  "VARCHAR",   "Required security clearance level"),
    ("remote_approved",     "BOOLEAN",   "Whether remote work is formally approved"),
    ("years_of_service",    "DOUBLE",    "Total years of continuous service"),
    ("next_review_date",    "DATE",      "Scheduled next performance review date"),
    ("degree_level",        "VARCHAR",   "Highest educational degree (BSc, MSc, PhD, etc.)"),
    ("field_of_study",      "VARCHAR",   "Academic field of study"),
    ("languages_spoken",    "VARCHAR",   "Languages spoken (comma-separated)"),
    ("diversity_group",     "VARCHAR",   "Self-identified equity-seeking group (voluntary)"),
]

_IT_COLS = [
    ("system_id",           "BIGINT",    "FK → systems_inventory.system_id"),
    ("asset_tag",           "VARCHAR",   "Physical asset tag number"),
    ("hostname",            "VARCHAR",   "Server or device hostname"),
    ("ip_address",          "VARCHAR",   "Primary IP address"),
    ("os_version",          "VARCHAR",   "Operating system and version"),
    ("patch_level",         "VARCHAR",   "Current patch level identifier"),
    ("ticket_id",           "VARCHAR",   "FK → helpdesk_tickets.ticket_id"),
    ("priority",            "VARCHAR",   "Priority level (P1–P4)"),
    ("resolution_hours",    "DOUBLE",    "Time to resolve in hours"),
    ("pipeline_id",         "VARCHAR",   "FK → etl_pipelines.pipeline_id"),
    ("user_id",             "BIGINT",    "FK → user_accounts.user_id (= employee_id)"),
    ("access_level",        "VARCHAR",   "Access permission level (read, write, admin)"),
    ("license_key",         "VARCHAR",   "Software license key (masked)"),
    ("seat_count",          "INTEGER",   "Number of licensed seats"),
    ("seats_used",          "INTEGER",   "Active seats in use"),
    ("expiry_date",         "DATE",      "License or certificate expiry date"),
    ("vendor_name",         "VARCHAR",   "Software or hardware vendor name"),
    ("contract_id",         "VARCHAR",   "Associated procurement contract ID"),
    ("sla_hours",           "DOUBLE",    "SLA response time commitment in hours"),
    ("uptime_pct",          "DOUBLE",    "System uptime percentage (0–100)"),
    ("alert_severity",      "VARCHAR",   "Alert severity (critical, warning, info)"),
    ("environment",         "VARCHAR",   "Deployment environment (prod, staging, dev)"),
    ("data_source",         "VARCHAR",   "Source system for this pipeline"),
    ("data_destination",    "VARCHAR",   "Target system for this pipeline"),
    ("run_frequency",       "VARCHAR",   "Pipeline run schedule (daily, hourly, etc.)"),
    ("last_success_at",     "TIMESTAMP", "Timestamp of last successful run"),
    ("error_count",         "INTEGER",   "Number of errors in last 30 days"),
    ("records_processed",   "BIGINT",    "Records processed in last run"),
    ("storage_gb",          "DOUBLE",    "Storage consumed in GB"),
    ("cpu_cores",           "INTEGER",   "Number of CPU cores allocated"),
    ("ram_gb",              "DOUBLE",    "RAM allocated in GB"),
    ("backup_frequency",    "VARCHAR",   "Backup schedule (daily, weekly, etc.)"),
    ("encryption_status",   "VARCHAR",   "Encryption status (encrypted, unencrypted, partial)"),
    ("classification",      "VARCHAR",   "Data sensitivity classification (public, internal, confidential, restricted)"),
    ("mfa_enabled",         "BOOLEAN",   "Whether MFA is enforced for this system"),
    ("vulnerability_count", "INTEGER",   "Open vulnerability count"),
    ("cvss_score",          "DOUBLE",    "Maximum CVSS vulnerability score"),
    ("compliance_status",   "VARCHAR",   "Compliance framework status (SOC2, ISO27001, etc.)"),
]

_DEPT_COLS = {
    "finance":  _FINANCE_COLS,
    "research": _RESEARCH_COLS,
    "hr":       _HR_COLS,
    "it":       _IT_COLS,
}

# ── glossary ──────────────────────────────────────────────────────────────────

_GLOSSARY_TERMS = [
    # Finance
    ("Indirect Cost Rate",     "finance", "The negotiated percentage applied to direct costs to recover institutional overhead (facilities, administration, etc.).",
     "indirect_cost / direct_cost × 100", ["grant_awards", "overhead_rates", "indirect_cost_proposals"]),
    ("Sub-Award",              "finance", "A grant or contract issued by the primary award recipient to another organisation to perform a portion of the funded work.",
     "N/A — categorical", ["sub_award_agreements", "subaward_monitoring_log"]),
    ("Fringe Benefit Rate",    "finance", "Employer-paid benefits (CPP, EI, health, pension) expressed as a percentage of gross salary.",
     "fringe_costs / gross_salary × 100", ["fringe_benefit_rates", "payroll_runs"]),
    ("Cost Sharing",           "finance", "Institutional or third-party contribution to a project not charged to the sponsor — often a funder requirement.",
     "N/A — categorical", ["cost_sharing_commitments", "grant_awards"]),
    ("F&A Rate",               "finance", "Facilities and Administrative rate — US equivalent of Canada's indirect cost rate for federally funded grants.",
     "Same formula as Indirect Cost Rate", ["overhead_rates", "indirect_cost_proposals"]),
    ("Encumbrance",            "finance", "A commitment of funds via a purchase order before actual expenditure is recorded.",
     "N/A — balance sheet item", ["encumbrances", "fund_balances"]),
    ("No-Cost Extension",      "finance", "An approved extension of a grant's end date without additional funding.",
     "N/A — categorical", ["no_cost_extensions", "grant_awards"]),
    ("Direct Cost",            "finance", "Costs specifically identifiable to a sponsored project (salaries, supplies, travel).",
     "total_cost − indirect_cost", ["expenditure_lines", "budget_periods"]),
    ("Carryforward",           "finance", "Unspent funds from one budget period authorised to be spent in the next.",
     "N/A — balance sheet item", ["carryforward_balances", "fund_balances"]),
    ("Effort Certification",   "finance", "The formal process by which grant-funded personnel confirm their percentage of effort on each project.",
     "effort_percent per grant per person", ["salary_effort_reports", "expenditure_lines"]),
    # Research
    ("Principal Investigator", "research", "The lead researcher accountable for the scientific conduct and financial management of a funded project.",
     "N/A — role designation", ["principal_investigators", "research_projects", "grant_applications"]),
    ("Ethics Protocol",        "research", "A formal application to a Research Ethics Board (REB) describing research involving human participants.",
     "N/A — categorical", ["ethics_protocols", "consent_forms", "protocol_amendments"]),
    ("Impact Factor",          "research", "A measure of the average number of citations received per paper published in a journal in the preceding two years.",
     "citations_in_year / articles_in_prior_two_years", ["citation_metrics", "publications"]),
    ("Open Access",            "research", "A publishing model providing free, unrestricted online access to peer-reviewed research.",
     "N/A — boolean flag", ["open_access_compliance", "publications"]),
    ("Data Management Plan",   "research", "A document describing how research data will be collected, stored, shared, and preserved.",
     "N/A — document artifact", ["data_management_plans", "research_projects"]),
    ("Technology Readiness Level", "research", "A scale (1–9) measuring the maturity of a technology from basic research to operational deployment.",
     "Assessed qualitatively per project", ["research_projects", "ip_disclosures"]),
    ("Tri-Council",            "research", "Collective name for Canada's three federal research funding agencies: CIHR, NSERC, and SSHRC.",
     "N/A — categorical", ["grant_applications", "grant_awards"]),
    ("Knowledge Translation",  "research", "The process of moving research evidence into practice, policy, or products to benefit society.",
     "N/A — activity tracking", ["knowledge_translation", "publications"]),
    ("h-index",                "research", "An author-level metric: h papers each cited at least h times.",
     "largest h where at least h papers have ≥h citations", ["citation_metrics", "principal_investigators"]),
    ("Biosafety Level",        "research", "A set of containment precautions required for work with potentially hazardous biological agents (1=lowest, 4=highest).",
     "N/A — ordinal scale", ["biosafety_records", "lab_inventory"]),
    # HR
    ("Full-Time Equivalent",   "hr", "A unit that measures employee workload: 1.0 FTE = one full-time employee; 0.5 FTE = half-time.",
     "hours_worked / standard_full_time_hours", ["positions", "employees", "salary_effort_reports"]),
    ("Postdoctoral Fellow",    "hr", "A researcher who holds a doctoral degree and is engaged in a temporary period of mentored research training.",
     "N/A — employment classification", ["postdoctoral_fellows", "employment_contracts"]),
    ("Tenure-Track",           "hr", "A faculty appointment leading to a review for permanent tenure based on research, teaching, and service.",
     "N/A — categorical", ["positions", "employees"]),
    ("Sessional Lecturer",     "hr", "An instructor hired on a course-by-course basis without long-term employment commitment.",
     "N/A — employment classification", ["employment_contracts", "positions"]),
    ("Collective Agreement",   "hr", "A binding contract between the employer and a union specifying wages, benefits, and working conditions.",
     "N/A — legal document", ["collective_agreements", "union_grievances"]),
    ("Step Level",             "hr", "An increment within a salary band reflecting years of experience at that classification.",
     "Determined by years of service and performance", ["compensation_bands", "employees"]),
    ("Probation Period",       "hr", "A defined initial period of employment during which performance is assessed before confirmation.",
     "N/A — categorical", ["probation_reviews", "employment_contracts"]),
    # IT
    ("ETL Pipeline",           "it", "A workflow that Extracts data from a source, Transforms it, and Loads it into a destination system.",
     "N/A — operational process", ["etl_pipelines", "pipeline_run_logs"]),
    ("Data Classification",    "it", "A taxonomy assigning sensitivity levels to data (public, internal, confidential, restricted) to guide access and handling.",
     "N/A — categorical", ["data_classifications", "systems_inventory"]),
    ("SLA",                    "it", "Service Level Agreement — a commitment specifying availability, response time, and support scope for an IT service.",
     "N/A — contractual", ["sla_agreements", "helpdesk_tickets"]),
    ("RBAC",                   "it", "Role-Based Access Control — an access management model where permissions are assigned to roles, not individuals.",
     "N/A — security framework", ["rbac_role_definitions", "user_accounts", "access_reviews"]),
    ("CVSS Score",             "it", "Common Vulnerability Scoring System — a 0–10 score rating the severity of a software vulnerability.",
     "Calculated from exploitability and impact metrics", ["vulnerability_scans", "patch_events"]),
    ("Mean Time to Resolve",   "it", "Average elapsed time between incident detection and full resolution.",
     "sum(resolution_hours) / count(tickets)", ["helpdesk_tickets", "security_incidents"]),
    ("Data Lineage",           "it", "Documentation of the origin, movement, and transformation of data as it flows through systems.",
     "N/A — graph metadata", ["data_lineage_graph", "etl_pipelines"]),
    ("Shadow IT",              "it", "Technology used within an organisation without explicit IT approval or knowledge.",
     "N/A — detection-based", ["shadow_it_detections", "software_licenses"]),
    ("Uptime SLA",             "it", "The guaranteed percentage of time a system is available (e.g. 99.9% = 8.7 h downtime/year).",
     "available_minutes / total_minutes × 100", ["sla_agreements", "application_performance"]),
    ("Zero Trust",             "it", "A security model that assumes no user or system is inherently trusted, requiring continuous verification.",
     "N/A — security framework", ["access_reviews", "mfa_enrollment", "firewall_rules"]),
    ("Data Retention",         "it", "The policy defining how long different categories of data must be kept before secure deletion.",
     "N/A — policy", ["data_retention_schedule", "data_classifications"]),
    ("Configuration Baseline", "it", "An approved reference configuration for a system type used to detect drift or unauthorised changes.",
     "N/A — security benchmark", ["configuration_baselines", "systems_inventory"]),
]

# ── helpers ───────────────────────────────────────────────────────────────────

def _rng_col_count(rng: random.Random) -> int:
    """Return a column count: avg ≈ 20, min = 10, max = 220."""
    tier = rng.random()
    if tier < 0.82:
        return rng.randint(10, 18)   # avg 14 → contributes 11.5
    elif tier < 0.92:
        return rng.randint(18, 40)   # avg 29 → contributes 2.9
    elif tier < 0.97:
        return rng.randint(40, 90)   # avg 65 → contributes 3.25
    elif tier < 0.99:
        return rng.randint(90, 160)  # avg 125 → contributes 2.5
    else:
        return rng.randint(160, 220) # avg 190 → contributes 0.19
    # Weighted avg ≈ 20.3


def _rand_ts(rng: random.Random, days_back: int = 730) -> str:
    base = datetime(2023, 1, 1)
    delta = timedelta(days=rng.randint(0, days_back), hours=rng.randint(0, 23))
    return (base + delta).strftime("%Y-%m-%d %H:%M:%S")


def _rand_email(rng: random.Random, dept: str) -> str:
    names = ["sarah.okonkwo", "marc.tremblay", "priya.nair", "james.whitfield",
             "liu.wei", "amara.diallo", "finn.berg", "caroline.leblanc",
             "reza.tehrani", "sofia.bertrand", "kwame.asante", "eva.lindqvist"]
    return f"{rng.choice(names)}@research-org.ca"


def _dq_score(rng: random.Random, n_cols_with_desc: int, n_total_cols: int) -> tuple[str, str, str]:
    """Completeness = % of ALL columns (any type) that have a definition."""
    col_coverage = n_cols_with_desc / n_total_cols if n_total_cols > 0 else 0
    # Add small random noise (±3 pts) so scores aren't all identical
    raw = col_coverage * 100 + rng.uniform(-3, 3)
    score = str(round(max(0, min(100, raw))))
    status = "PASS" if col_coverage >= 0.70 else rng.choice(["PASS", "WARN"])
    n = rng.randint(1, 48)
    unit = "hours" if n < 24 else "days"
    freshness = f"{n % 24 + 1} {unit}" if unit == "hours" else f"{n // 24} days"
    return score, status, freshness


# ── main generator ────────────────────────────────────────────────────────────

def generate(
    n_tables_per_dept: int,
    seed: int,
    out_path: Path,
    depts: list[str],
    with_data: bool,
) -> None:
    rng = random.Random(seed)

    tables_rows:      list[dict] = []
    columns_rows:     list[dict] = []
    permissions_rows: list[dict] = []
    lineage_rows:     list[dict] = []
    tags_rows:        list[dict] = []
    dq_rows:          list[dict] = []
    glossary_rows:    list[dict] = []

    # For lineage DAG construction
    dept_tables: dict[str, list[str]] = {d: [] for d in depts}

    # ── build table + column metadata ────────────────────────────────────────
    dept_pools = {
        "finance":  list(_FINANCE_TABLES),
        "research": list(_RESEARCH_TABLES),
        "hr":       list(_HR_TABLES),
        "it":       list(_IT_TABLES),
    }

    for dept in depts:
        schema   = DEPT_SCHEMAS[dept]
        pool     = dept_pools[dept]
        dept_col_pool = _DEPT_COLS[dept]
        principal = DEPT_PRINCIPALS[dept]
        steward   = STEWARDS[dept]

        # Expand pool if needed — track names to prevent duplicates
        suffix_words = ["log", "history", "archive", "staging", "summary",
                        "detail", "monthly", "quarterly", "report", "audit",
                        "snapshot", "raw", "processed", "enriched", "v2", "ext"]
        existing_names = {n for n, _ in pool}
        base_len = len(pool)
        attempts = 0
        while len(pool) < n_tables_per_dept and attempts < 10_000:
            attempts += 1
            src_name, src_desc = pool[rng.randint(0, base_len - 1)]
            sfx = rng.choice(suffix_words)
            candidate = f"{src_name}_{sfx}"
            if candidate not in existing_names:
                existing_names.add(candidate)
                pool.append((candidate, f"{src_desc} ({sfx})"))

        selected = rng.sample(pool, n_tables_per_dept)

        for tbl_name, tbl_desc in selected:
            full_name = f"{CATALOG}.{schema}.{tbl_name}"
            dept_tables[dept].append(full_name)

            # Sparse descriptions: 75% of tables have a description
            has_desc = rng.random() < 0.75
            comment  = tbl_desc if has_desc else None

            # Sparse friendly names: 60% of tables get bilingual friendly
            # names + definitions, exercising both the present and fallback
            # display paths in the UI.
            has_friendly = rng.random() < 0.60
            if has_friendly:
                pretty   = tbl_name.replace("_", " ").title()
                _name_en = pretty
                _name_fr = pretty  # placeholder; real FR strings come from UC
                _def_en  = tbl_desc
                _def_fr  = tbl_desc
            else:
                _name_en = _name_fr = _def_en = _def_fr = None

            tables_rows.append({
                "full_name":    full_name,
                "catalog_name": CATALOG,
                "schema_name":  schema,
                "table_name":   tbl_name,
                "table_type":   rng.choice(["MANAGED", "MANAGED", "MANAGED", "EXTERNAL"]),
                "comment":      comment,
                "updated_at":   _rand_ts(rng),
                "steward_email": steward if rng.random() < 0.6 else None,
                "business_name_en":       _name_en,
                "business_name_fr":       _name_fr,
                "business_definition_en": _def_en,
                "business_definition_fr": _def_fr,
            })

            # ── columns ──────────────────────────────────────────────────────
            n_cols = _rng_col_count(rng)

            # 1. Mandatory identity column
            mandatory = [(f"{tbl_name}_id", "BIGINT", f"Primary key for {tbl_name}")]

            # 2. Always-present timestamps (just 2 to keep small tables lean)
            always_common = [
                ("created_at", "TIMESTAMP", "Row creation timestamp"),
                ("updated_at", "TIMESTAMP", "Last modification timestamp"),
            ]

            # 3. Sample from dept pool and common pool without overlap
            always_names     = {c[0] for c in always_common} | {f"{tbl_name}_id"}
            available_dept   = [c for c in dept_col_pool if c[0] not in always_names]
            available_common = [c for c in _COMMON_COLS   if c[0] not in always_names
                                and c[0] not in {d[0] for d in available_dept}]

            # Dept cols: up to half of target, capped at 12
            n_dept   = min(max(n_cols // 3, 2), 12, len(available_dept))
            # Common cols: small fixed sample (2–4)
            n_common = min(max((n_cols - 3 - n_dept) // 4, 0), 4, len(available_common))

            dept_sample   = rng.sample(available_dept,   n_dept)
            common_sample = rng.sample(available_common, n_common)

            col_list = mandatory + always_common + dept_sample + common_sample

            # 4. Pad to n_cols with synthetic columns
            pad_i = 0
            while len(col_list) < n_cols:
                pad_i += 1
                kind = rng.choice(["attribute", "metric", "flag", "code", "amount", "count"])
                if kind == "flag":
                    col_list.append((f"{kind}_{pad_i:02d}", "BOOLEAN", f"Boolean indicator flag {pad_i}"))
                elif kind in ("metric", "amount"):
                    col_list.append((f"{kind}_{pad_i:02d}", "DOUBLE",  f"Numeric measurement {pad_i}"))
                elif kind == "count":
                    col_list.append((f"{kind}_{pad_i:02d}", "INTEGER", f"Count field {pad_i}"))
                else:
                    col_list.append((f"{kind}_{pad_i:02d}", "VARCHAR", f"Categorical field {pad_i}"))

            col_list = col_list[:n_cols]

            _n_cols_with_desc = 0
            for col_name, data_type, col_comment in col_list:
                has_col_desc = rng.random() < 0.65
                if has_col_desc:
                    _n_cols_with_desc += 1
                columns_rows.append({
                    "table_full_name": full_name,
                    "column_name":     col_name,
                    "data_type":       data_type,
                    "comment":         col_comment if has_col_desc else None,
                })

            # ── permissions ───────────────────────────────────────────────────
            permissions_rows.append({
                "table_full_name": full_name,
                "principal":       principal,
                "privilege":       "SELECT",
            })

            # ~40 public tables (SELECT_ALL_USERS)
            if tbl_name in {"organizational_units", "hr_policies", "employees",
                            "positions", "research_areas", "funding_agency_requirements",
                            "expenditure_categories", "service_catalog",
                            "data_governance_policies", "research_methods"} \
                    or rng.random() < 0.025:
                permissions_rows.append({
                    "table_full_name": full_name,
                    "principal":       "SELECT_ALL_USERS",
                    "privilege":       "SELECT",
                })

            # Cross-dept access (~8% of tables get a second group)
            cross_map = {
                "finance":  ["research_group"],
                "research": ["finance_group", "it_group"],
                "hr":       ["finance_group"],
                "it":       ["research_group", "hr_group"],
            }
            if rng.random() < 0.08:
                extra = rng.choice(cross_map[dept])
                permissions_rows.append({
                    "table_full_name": full_name,
                    "principal":       extra,
                    "privilege":       "SELECT",
                })

            # ── object tags ────────────────────────────────────────────────────
            row_count = rng.randint(110, 300)
            tags_rows.append({"object_type": "TABLE", "object_full_name": full_name,
                               "tag_key": "row_count", "tag_value": str(row_count)})
            tags_rows.append({"object_type": "TABLE", "object_full_name": full_name,
                               "tag_key": "department", "tag_value": dept})

            # ── data quality ───────────────────────────────────────────────────
            score, status, freshness = _dq_score(rng, _n_cols_with_desc, len(col_list))
            dq_rows.append({
                "table_full_name": full_name,
                "dq_score":        score,
                "last_run_status": status,
                "freshness":       freshness,
            })

        # Schema-level tag
        tags_rows.append({"object_type": "SCHEMA",
                          "object_full_name": f"{CATALOG}.{schema}",
                          "tag_key": "owner", "tag_value": steward})

    # ── lineage DAG ───────────────────────────────────────────────────────────
    # Tier every table in a dept: 20% source, 60% mid, 20% gold
    for dept in depts:
        tables = dept_tables[dept]
        rng.shuffle(tables)
        n = len(tables)
        n_source = max(1, int(n * 0.20))
        n_gold   = max(1, int(n * 0.20))

        source_tier = set(tables[:n_source])
        gold_tier   = set(tables[n - n_gold:])
        mid_tier    = set(tables[n_source: n - n_gold])

        # Mid tables get 1–2 upstreams from source or other mid tables
        eligible_up = list(source_tier) + list(mid_tier)
        for tbl in mid_tier:
            k = rng.randint(1, min(2, len(eligible_up)))
            for up in rng.sample(eligible_up, k):
                if up == tbl:
                    continue
                lineage_rows.append({"table_full_name": tbl, "direction": "UPSTREAM",
                                     "entity_full_name": up, "entity_type": "TABLE"})
                lineage_rows.append({"table_full_name": up, "direction": "DOWNSTREAM",
                                     "entity_full_name": tbl, "entity_type": "TABLE"})

        # Gold tables get 2–4 upstreams, potentially cross-schema
        it_sources = dept_tables.get("it", [])
        for tbl in gold_tier:
            upstream_pool = list(mid_tier) + list(source_tier)
            # Cross-schema lineage: finance gold tables can pull from research
            if dept == "finance" and "research" in dept_tables:
                upstream_pool += rng.sample(dept_tables["research"],
                                            min(5, len(dept_tables["research"])))
            if dept == "hr" and "finance" in dept_tables:
                upstream_pool += rng.sample(dept_tables["finance"],
                                            min(3, len(dept_tables["finance"])))
            if it_sources and dept != "it":
                upstream_pool += rng.sample(it_sources, min(2, len(it_sources)))

            k = rng.randint(2, min(4, len(upstream_pool)))
            for up in rng.sample(upstream_pool, k):
                if up == tbl:
                    continue
                lineage_rows.append({"table_full_name": tbl, "direction": "UPSTREAM",
                                     "entity_full_name": up, "entity_type": "TABLE"})
                lineage_rows.append({"table_full_name": up, "direction": "DOWNSTREAM",
                                     "entity_full_name": tbl, "entity_type": "TABLE"})

    # ── glossary ──────────────────────────────────────────────────────────────
    # Build a lookup of table name → full_name for related_tables resolution
    tbl_name_to_full: dict[str, str] = {
        r["table_name"]: r["full_name"] for r in tables_rows
    }
    for term, domain, definition, calculation, related_tbl_names in _GLOSSARY_TERMS:
        related_fulls = [tbl_name_to_full[n] for n in related_tbl_names if n in tbl_name_to_full]
        glossary_rows.append({
            "term":           term,
            "definition":     definition,
            "calculation":    calculation,
            "domain":         domain.title() + " Office",
            "steward":        STEWARDS.get(domain, "admin@research-org.ca"),
            "related_tables": related_fulls,
        })

    # ── build DataFrames ──────────────────────────────────────────────────────
    tables_df      = pd.DataFrame(tables_rows)
    columns_df     = pd.DataFrame(columns_rows)
    permissions_df = pd.DataFrame(permissions_rows)
    lineage_df     = pd.DataFrame(lineage_rows)
    tags_df        = pd.DataFrame(tags_rows)
    dq_df          = pd.DataFrame(dq_rows)
    glossary_df    = pd.DataFrame(glossary_rows)

    print(f"  tables:      {len(tables_df):,}")
    print(f"  columns:     {len(columns_df):,}  (avg {len(columns_df)/max(len(tables_df),1):.1f}/table)")
    print(f"  permissions: {len(permissions_df):,}")
    print(f"  lineage:     {len(lineage_df):,} edges")
    print(f"  tags:        {len(tags_df):,}")
    print(f"  dq_cache:    {len(dq_df):,}")
    print(f"  glossary:    {len(glossary_df):,} terms")

    # ── write DuckDB (mirrors write_duckdb() in sync_metadata.py) ────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp.duckdb")

    if tmp_path.exists():
        tmp_path.unlink()

    con = duckdb.connect(str(tmp_path))

    # Tables live in the "dictionary_cache" schema so that the app's 3-part SQL
    # (data_governance.dictionary_cache.table_name) resolves correctly when the
    # file is ATTACHed AS data_governance. This mirrors the Databricks catalog
    # layout and avoids any prefix-stripping hacks in the app.
    SCHEMA = "dictionary_cache"
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    reload_frames = {
        "tables_metadata":  tables_df,
        "columns_metadata": columns_df,
        "permissions_cache": permissions_df,
        "lineage_cache":    lineage_df,
        "object_tags":      tags_df,
        "data_quality_cache": dq_df,
        # glossary lives in its own table — app reads it via run_query
        "glossary":         glossary_df,
    }

    empty_schemas = {
        "audit_log": "event_id VARCHAR, event_type VARCHAR, object_type VARCHAR, "
                     "object_name VARCHAR, actor_email VARCHAR, old_value VARCHAR, "
                     "new_value VARCHAR, created_at TIMESTAMP",
        # business_name_overrides lives in user_data in production; we create
        # it empty here so load-test SQL that LEFT JOINs it (mirroring
        # search_all_metadata) can run without ATTACH gymnastics.
        "business_name_overrides": (
            "table_full_name VARCHAR, column_name VARCHAR, "
            "business_name VARCHAR, definition VARCHAR, "
            "edited_by VARCHAR, edited_at TIMESTAMP"
        ),
    }

    for tbl, df in reload_frames.items():
        if df.empty:
            con.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.{tbl} AS SELECT * FROM df LIMIT 0")
        else:
            con.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.{tbl} AS SELECT * FROM df")

    for tbl, schema_sql in empty_schemas.items():
        con.execute(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{tbl} ({schema_sql})")

    con.execute(f"CREATE INDEX IF NOT EXISTS idx_perm_principal ON {SCHEMA}.permissions_cache (principal)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_perm_table    ON {SCHEMA}.permissions_cache (table_full_name)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_cols_table    ON {SCHEMA}.columns_metadata  (table_full_name)")

    # ── optional: create actual row data for Preview feature ─────────────────
    if with_data:
        _write_row_data(con, tables_rows, columns_rows, tags_rows, rng)

    con.close()
    os.replace(tmp_path, out_path)
    print(f"\n✅  Written to {out_path}")


def _write_row_data(con, tables_rows, columns_rows, tags_rows, rng: random.Random) -> None:
    """Create actual data tables with sample rows so Preview works locally."""
    from datetime import date

    # Build column map: full_name → [(col_name, data_type), ...]
    col_map: dict[str, list[tuple[str, str]]] = {}
    for r in columns_rows:
        col_map.setdefault(r["table_full_name"], []).append((r["column_name"], r["data_type"]))

    # Build row count map from tags
    row_count_map: dict[str, int] = {}
    for t in tags_rows:
        if t["tag_key"] == "row_count":
            row_count_map[t["object_full_name"]] = int(t["tag_value"])

    statuses    = ["active", "inactive", "pending", "approved", "rejected", "archived"]
    varchar_vals = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
    base_date   = date(2023, 1, 1)

    print("\n  Writing row data for Preview feature…")
    for tbl in tables_rows:
        full_name = tbl["full_name"]
        catalog, schema, tname = full_name.split(".")
        n_rows = row_count_map.get(full_name, rng.randint(110, 300))
        cols = col_map.get(full_name, [])
        if not cols:
            continue

        col_defs = ", ".join(f'"{c}" VARCHAR' for c, _ in cols)
        # Store under schema only (no catalog prefix) — the file is ATTACHed as the
        # Databricks catalog name by the app, so data_governance.<schema>.<table> resolves.
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        con.execute(f'CREATE OR REPLACE TABLE "{schema}"."{tname}" ({col_defs})')

        rows = []
        for i in range(1, n_rows + 1):
            row = []
            for col_name, dtype in cols:
                if dtype == "BIGINT" or dtype == "INTEGER":
                    row.append(str(rng.randint(1, 99999)))
                elif dtype == "DOUBLE" or "DECIMAL" in dtype:
                    row.append(f"{rng.uniform(0, 10000):.2f}")
                elif dtype == "BOOLEAN":
                    row.append("true" if rng.random() > 0.5 else "false")
                elif dtype == "TIMESTAMP":
                    delta = timedelta(days=rng.randint(0, 730))
                    row.append((datetime(2023, 1, 1) + delta).strftime("%Y-%m-%d %H:%M:%S"))
                elif dtype == "DATE":
                    delta = timedelta(days=rng.randint(0, 730))
                    row.append((base_date + delta).isoformat())
                elif col_name == "status":
                    row.append(rng.choice(statuses))
                else:
                    row.append(rng.choice(varchar_vals) + f"_{i:04d}")
            rows.append(row)

        placeholders = ", ".join(["?" ] * len(cols))
        col_names = ", ".join(f'"{c}"' for c, _ in cols)
        con.executemany(
            f'INSERT INTO "{schema}"."{tname}" ({col_names}) VALUES ({placeholders})',
            rows
        )


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a realistic DuckDB test dataset.")
    parser.add_argument("--out",    default="data/test_data.duckdb",
                        help="Output DuckDB path (default: data/test_data.duckdb)")
    parser.add_argument("--seed",   type=int, default=0,
                        help="Random seed for reproducible runs (default: 0)")
    parser.add_argument("--tables", type=int, default=200,
                        help="Tables per department (default: 200 → 800 total)")
    parser.add_argument("--dept",   choices=list(DEPT_SCHEMAS) + ["all"], default="all",
                        help="Generate a single department subset (default: all)")
    parser.add_argument("--with-data", action="store_true",
                        help="Also create actual row data for the Preview feature")
    args = parser.parse_args()

    depts = list(DEPT_SCHEMAS) if args.dept == "all" else [args.dept]
    total = args.tables * len(depts)

    print(f"Generating {args.tables} tables × {len(depts)} dept(s) = {total} tables")
    print(f"Seed: {args.seed}  |  Output: {args.out}")

    generate(
        n_tables_per_dept=args.tables,
        seed=args.seed,
        out_path=Path(args.out),
        depts=depts,
        with_data=args.with_data,
    )


if __name__ == "__main__":
    main()
