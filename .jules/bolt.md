## 2024-05-24 - Pandas iteration and vectorized operations
**Learning:** `iterrows()` is extremely slow for Streamlit UI rendering and background sync operations compared to `itertuples()`. Also, using `.apply()` with `str()` conversions for empty string checks is inefficient and bugs out on `NaN` (because `str(NaN) == 'nan'`).
**Action:** Replaced `iterrows()` with `itertuples(index=False)` everywhere in `src/ui/cards.py`, and refactored empty string checks to use vectorized `.str.strip().str.len() > 0`.
