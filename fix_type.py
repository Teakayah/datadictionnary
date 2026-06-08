import re

with open("src/ui/cards/discovery.py", "r") as f:
    content = f.read()

new_block = """    # Decouple internal tab identifiers from localized labels.
    _disc_tabs = ["notable", "bookmarks", "recent", "recommended"]
    _disc_tab_labels = {
        "notable": t("personalization.tab_notable"),
        "bookmarks": t("personalization.tab_bookmarks"),
        "recent": t("personalization.tab_recent"),
        "recommended": t("personalization.tab_recommended"),
    }

    _disc_active = st.segmented_control(
        "discovery_tabs",
        options=_disc_tabs,
        format_func=lambda x: _disc_tab_labels[x],
        key="discovery_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )

    # Prevent deselecting all tabs (forces at least one to be active).
    if _disc_active is None:
        _disc_active = "notable"
        st.session_state["discovery_active_tab"] = _disc_active

    if _disc_active == "notable":
        _render_notable_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "bookmarks":
        _render_bookmarks_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "recent":
        _render_recent_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "recommended":
        _render_recommended_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)"""

old_block_pattern = r'    # Decouple internal tab identifiers from localized labels.*?_render_recommended_tab\(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn\)'

new_block = """    # Decouple internal tab identifiers from localized labels.
    _disc_tabs = ["notable", "bookmarks", "recent", "recommended"]
    _disc_tab_labels = {
        "notable": t("personalization.tab_notable"),
        "bookmarks": t("personalization.tab_bookmarks"),
        "recent": t("personalization.tab_recent"),
        "recommended": t("personalization.tab_recommended"),
    }

    _disc_active = st.segmented_control(
        "discovery_tabs",
        options=_disc_tabs,
        format_func=lambda x: _disc_tab_labels[x],
        key="discovery_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )

    # Prevent deselecting all tabs (forces at least one to be active).
    if not _disc_active:
        _disc_active = "notable"

    if _disc_active == "notable":
        _render_notable_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "bookmarks":
        _render_bookmarks_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "recent":
        _render_recent_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)
    elif _disc_active == "recommended":
        _render_recommended_tab(groups, get_authorized_tables_fn, pref_delete_fn, pref_upsert_fn)"""

content = re.sub(old_block_pattern, new_block, content, flags=re.DOTALL)

with open("src/ui/cards/discovery.py", "w") as f:
    f.write(content)
