# ADR 003 — Streamlit instead of FastAPI + React

**Status:** Accepted  
**Date:** 2026-04-30  
**Deciders:** Platform team

---

## Context

The Business Data Dictionary is an internal tool for non-technical business users. The primary interactions are:

- Search (type a term, see a list of matching tables with descriptions)
- Table detail (click a result, see columns, grants, lineage, comments)
- Glossary browsing
- Bookmarking and commenting (low-frequency writes)

The team building the tool is small (two to three engineers) with strong Python skills and limited frontend experience. Time-to-first-demo was a key constraint: the tool needed to be usable by business stakeholders within two weeks of the decision to build it.

### Option A — FastAPI + React

A REST or GraphQL API in FastAPI with a React (or Next.js) frontend.

Advantages:
- Full control over the UI — any design system, any interaction pattern
- Standard HTTP semantics enable conventional load testing tools (k6, wrk, Gatling)
- Stateless API is easy to scale horizontally

Disadvantages:
- Requires maintaining two codebases (Python API + JavaScript frontend)
- React component development, state management (Redux or Zustand), and build tooling add significant overhead for a two-person team
- Time-to-first-demo is weeks, not days
- API authentication (session tokens, CSRF, CORS) requires explicit implementation
- CI must cover both Python and JavaScript test suites

### Option B — Streamlit

A single Python file that defines both the UI and the business logic. Streamlit handles the WebSocket connection, session state, and server-side rendering.

Advantages:
- Single Python codebase. The same team that writes the data pipeline writes the UI.
- Rapid iteration: adding a new tab or card is tens of lines of Python
- Built-in session state management removes the need for external state stores
- OIDC authentication is implemented once in Python; no separate frontend auth concern
- Existing Streamlit `AppTest` framework enables pytest-based integration tests without a browser

Disadvantages:
- Interactive features (button clicks, widget state) are driven over a binary WebSocket protocol (protobuf). Conventional HTTP load testing tools cannot exercise real interactions — only the page-shell HTTP endpoint is testable with tools like Locust's HTTP user class.
- The workaround for load testing is to test the query layer directly (DuckDB reads) using a separate `DuckDBQueryUser` class in Locust. This reflects the actual performance-sensitive path: DuckDB search queries, not HTTP page delivery.
- Multi-page routing (Streamlit's file-based `pages/` directory) was not used because the app has a custom tab navigation model with permission-aware tab visibility. A single entry point (`app.py`) is simpler to reason about for this use case.
- `app.py` grows large without discipline. The refactoring roadmap (`REFACTORING.md`) addresses this by extracting modules into `src/`.

---

## Decision

Use Streamlit for the initial version of the Business Data Dictionary.

The business user audience, small team size, and rapid-iteration requirement favor a Python-native approach over a two-tier web architecture. The WebSocket interaction model is a known limitation for HTTP load testing, which is mitigated by testing the DuckDB query layer directly.

A migration to FastAPI + a lightweight frontend remains a valid long-term option if the team grows or if more complex UI interactions are required, but is out of scope for v0.x.

---

## Consequences

**Positive:**
- Single Python codebase with pytest integration tests
- New screens can be added in hours, not days
- OIDC auth, permission enforcement, and DuckDB queries are all in one language

**Negative:**
- Full end-to-end interaction testing requires Playwright or a similar browser automation tool; pytest AppTest covers rendering but not real click flows
- HTTP load testing (Locust `DictionaryHTTPUser`) tests only page delivery, not the actual app logic. The `DuckDBQueryUser` in `tests/load/locustfile.py` fills this gap by directly executing the search SQL that the app would run
- Streamlit's execution model (top-to-bottom re-run on every interaction) requires careful use of `st.cache_data` and `st.session_state` to avoid redundant database queries
- `app.py` at 4 000+ lines is currently a monolith. Extraction to `src/` modules is tracked in `REFACTORING.md`
