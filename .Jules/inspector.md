## 2026-06-03 - Dialog/Tabs testing in Streamlit
**Learning:** Testing functions wrapped in `@st.dialog` using `AppTest` often fails because the nested dialog layout state might not easily expose buttons or properties when directly triggering the component.
**Action:** Extract the inner dialog logic to a private helper function, or unwrap the dialog via `_show_delete_cms_dialog.__wrapped__("arg")` to assert internal button clicks properly without crashing with "open() is not a valid Streamlit command".

## 2026-06-03 - DuckDB testing in Pytest
**Learning:** Instantiating DuckDB instances globally during pytest collection can cause `numpy: cannot load module more than once per process` and other import errors.
**Action:** Isolate DuckDB initialization inside the test scope or use `patch` on `_DuckDBConn` during specific test runs instead of declaring module-level static DuckDB instances across different fixture boundaries.

## 2026-06-03 - Mocking DB connections across multiple calls
**Learning:** When testing database storage classes that obtain connections multiple times (e.g. `create` then `list_unread`), patching the connection getter with `return_value=mock_conn` results in reusing the exact same connection instance. If the first operation's `__exit__` closes the connection, the next operation fails with "Connection has already been closed".
**Action:** When mocking connection factory functions like `get_db_connection`, use `side_effect=TestDuckDBConn` to yield a fresh connection on each call, or ensure the mock's context manager does not prematurely close the underlying connection.
