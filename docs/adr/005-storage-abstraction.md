# ADR 005 — Per-entity storage abstraction

**Status:** Accepted
**Date:** 2026-05-08
**Deciders:** Platform team

---

## Context

Before this change, every entity persisted by the app (`src/cms.py`,
`src/pipelines.py`, `src/personalization.py`, `src/audit.py`) carried
its own copy of the same three-way switch:

```python
def get_active_posts():
    if not _duckdb_available():
        # session-state path
        ...
        return ...
    try:
        # DuckDB path
        ...
    except Exception as exc:
        log.warning("Could not load CMS posts: %s", exc)
        return []
```

The same pattern repeated ~13 times across four files. Adding a fifth
entity (e.g. comments, glossary edits) would have meant writing it
again. Two specific costs:

1. **Duplicated bug surface.** Two of the four modules had subtly
   different exception-handling shapes; a fix to one didn't
   automatically reach the others.
2. **Tests were brittle.** Most existing tests mocked
   `_duckdb_available` to `False` to force the demo path, which coupled
   tests to the runtime-routing implementation. Renaming or refactoring
   the routing function broke unrelated tests.

A senior-developer audit (TODO #4) recommended a Protocol-based
storage abstraction with one factory per entity.

### Alternatives considered

**A single `Storage` god-class with everything on it.**
Tempting because there's only one factory call site. But it conflates
unrelated entities — adding a CMS field would force every test that
imports `Storage` to update mocks, even tests in unrelated modules.
Worse, the "Databricks" backend implementation differs per entity (CMS
has no Databricks variant; audit has both DuckDB and Databricks),
forcing the god-class to be either an empty-method base or a
fat-interface anti-pattern. Rejected.

**`abc.ABC` instead of `typing.Protocol`.**
Explicit `class DuckDBCMSStorage(CMSStorage)` is more discoverable in
IDEs but forces every test fake to inherit from the same ABC. Tests
already had ad-hoc fakes inline — keeping them as plain classes that
satisfy a structural Protocol let us migrate one entity at a time
without rewriting fakes. Rejected.

**A repository / unit-of-work pattern with explicit transactions.**
Real ORMs need this; we don't. DuckDB writes are already serialised by
`_db_write_lock`, and the session-state backend has no concept of a
transaction. Adding the layer would be all overhead. Rejected.

**Status-quo: keep the duplicated branches.**
Accepted technical debt for as long as the entity count stayed small.
At four entities and 13 duplicated branches, the cost-benefit flipped.

---

## Decision

Per-entity Protocols, each with one or more concrete backends. Factory
functions in `src/storage/__init__.py` pick the backend at call time
based on `is_demo_mode()` and `_duckdb_available()`.

### Layout

```
src/storage/
  __init__.py             factories: get_<entity>_storage()
  cms_storage.py          CMSStorage           — Demo / DuckDB / Fake
  pipeline_storage.py     PipelineDefStorage   — Demo / DuckDB / Fake
                          PipelineRunStorage   — Demo / DuckDB / Fake
  preference_storage.py   PreferenceStorage    — Demo / DuckDB / Fake
                          SiteSettingStorage   — Demo / DuckDB / Fake
  audit_storage.py        AuditStorage         — Demo / DuckDB / Fake
                          BusinessNameOverrideStorage  — Demo / DuckDB / Fake
```

### Conventions

- **Protocols are runtime-checkable** so tests can do
  `isinstance(x, CMSStorage)` smoke tests for protocol coverage.
- **Demo backends** mirror the previous session-state behaviour
  literally (no behavioural change); `Site_Setting` and `Preference`
  demo backends are intentional no-ops to preserve pre-refactor
  behaviour where the in-process session cache was the only
  runtime-mutable knob without DuckDB.
- **Fake backends** are session-free in-memory dicts; they don't
  depend on Streamlit and are usable from any unit test via
  `mock.patch("src.<module>.get_<entity>_storage", return_value=fake)`.
- **Factories are not cached.** `is_demo_mode()` and
  `_duckdb_available()` re-evaluate per call so tests can flip env vars
  between calls and see consistent behaviour. Cost is microseconds.
- **The wrapper module** (`src/cms.py`, etc.) keeps its public API
  identical so callers don't change. New code can import the storage
  directly if it needs Protocol-typed access.

### Test pattern

Before:
```python
@patch("src.cms._duckdb_available", return_value=False)
def test_create_post(mock):
    create_post(...)
    assert st.session_state["_demo_cms_posts"] == [...]
```

After:
```python
def test_create_post():
    fake = FakeCMSStorage()
    with patch("src.cms.get_cms_storage", return_value=fake):
        create_post(...)
    assert fake.posts[0]["title"] == "Hello"
```

The new shape decouples the test from the routing implementation.

### Direct-Databricks variants removed (TODO #7)

`DatabricksAuditStorage` and `DatabricksBusinessNameOverrideStorage`
were initially added alongside the Demo / DuckDB pair so the app could
fall back to the SQL Warehouse when DuckDB was missing. After the
sidecar daemon (ADR 004) became the only intentional Databricks
writer, those classes were dead code — every Streamlit pod has DuckDB
locally in production, and writes go through the queue. They were
deleted in TODO #7 along with `_get_databricks_write_connection`.
`_get_write_connection` now raises a clear error if DuckDB is
unavailable instead of silently opening a fresh SQL Warehouse session
per write.

---

## Consequences

**Positive:**

- Adding a new entity is a recipe, not a question:
  1. Define `<Name>Storage(Protocol)`.
  2. Implement `Demo<Name>Storage`, `DuckDB<Name>Storage`,
     `Fake<Name>Storage`.
  3. Add a `get_<name>_storage()` factory.
  4. Replace the wrapper module's body with one-liners.
- 13 duplicated branches collapsed to ~50 lines of routing logic.
- Tests inject `Fake*Storage` rather than mocking `_duckdb_available`,
  which decoupled them from the runtime-routing implementation.

**Negative:**

- One more module to read for a contributor doing their first
  entity-level change. Mitigated by the regularity — once you've read
  one storage module, you've read them all.
- Protocol-based typing has weaker IDE support than ABC inheritance in
  some editors. Hasn't been a problem in practice.

**Out of scope:**

- A `CommentStorage` for `src/comments.py`. The pattern is the same;
  migration is mechanical. Deferred to a future ticket if the
  entity grows new fields.
- Migrating `src/pages/search.py` from
  `src.db.queries.get_column_business_names` to
  `BusinessNameOverrideStorage.get_for_table`. Mechanical follow-up.
