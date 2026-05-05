## $(date +%Y-%m-%d) - Streamlit Micro-UX Enhancements
**Learning:** In Streamlit, adding `help="..."` to elements like `st.selectbox` and `st.text_area` acts as a tooltip and provides accessible context (ARIA) without needing custom components. Also, setting `index=None` on `st.selectbox` prevents auto-selection, acting like a proper search input placeholder.
**Action:** Use `help` for adding tooltips and accessible context in Streamlit form elements. Use `index=None` on selectboxes that function as search inputs to show the placeholder text initially.
