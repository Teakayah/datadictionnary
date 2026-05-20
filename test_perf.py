import time
import pandas as pd
import streamlit as st

class MockSessionState(dict):
    pass
st.session_state = MockSessionState()

import src.db.queries
from src.demo.data import _DEMO_TABLES
large_df = pd.concat([_DEMO_TABLES] * 1000, ignore_index=True)

@st.cache_data(ttl="1h", show_spinner=False)
def get_authorized_tables_fn(groups):
    return large_df

from src.db.queries import get_authorized_table_names
src.db.queries.get_authorized_tables = get_authorized_tables_fn

groups = ("group1", "group2")

# warm up
_ = get_authorized_table_names(groups)

start = time.perf_counter()
for _ in range(100):
    _ = get_authorized_table_names(groups)
end = time.perf_counter()

print(f"Time with cached set: {end - start:.4f}")

start_inline = time.perf_counter()
for _ in range(100):
    _ = set(get_authorized_tables_fn(groups)["full_name"].tolist()) if groups else set()
end_inline = time.perf_counter()

print(f"Time inline unoptimized: {end_inline - start_inline:.4f}")
