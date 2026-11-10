from __future__ import annotations
"""CMS admin section — list / create / delete posts.

Used only from ``cards/admin.py``'s ``render_admin_page``. Kept as its own
file so ``admin.py`` stays under the 400-line ceiling and the CMS admin
write surface (create_post, delete_post) lives next to its renderer.

The read-only banner that surfaces these posts on the discovery tab lives
in ``cards/discovery.py::render_cms_banner``.
"""


import html as _html

import streamlit as st

from src.cms import _EXPIRY_DAYS, PostParams, create_post, delete_post, get_all_posts
from src.i18n import t
from src.ui.cards._shared import _POST_COLOR, _render_empty_state


@st.dialog(t("cms.confirm_delete_title"))
def _show_delete_cms_dialog(post_id: str):
    st.write(t("cms.confirm_delete_prompt"))
    _s, _c = st.columns(2)
    with _s:
        if st.button(t("cms.confirm_delete_button"), help=t("help.btn_confirm_delete_post"), type="primary", use_container_width=True):
            with st.spinner(t("common.deleting")):
                delete_post(post_id)
                st.toast(t("common.deleted"))
            st.rerun()
    with _c:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("cms.create_title"), width="large")
def _show_cms_create_dialog():
    """Render a Streamlit dialog for creating new CMS posts.

    Handles form inputs (type, title, body, links) and triggers the save action.
    """
    key_map = {
        "announcement": "cms.type_announcement",
        "featured_table": "cms.type_featured",
        "guide": "cms.type_guide",
    }
    post_type = st.radio(
        t("cms.post_type"),
        options=list(key_map.keys()),
        format_func=lambda x: t(key_map[x]),
        horizontal=True,
        key="cms_create_type",
    )

    title = st.text_input(t("cms.post_title"), placeholder=t("cms.post_title_placeholder"), max_chars=120, key="cms_create_title")
    body  = st.text_area(t("cms.post_body"), placeholder=t("cms.post_body_placeholder"), max_chars=500, height=100, key="cms_create_body")

    table_ref = None
    if post_type == "featured_table":
        table_ref = st.text_input(
            t("cms.post_table_ref"),
            placeholder=t("cms.post_table_ref_placeholder"),
            key="cms_create_tableref",
        )

    expiry_key = st.selectbox(
        t("cms.post_expiry"),
        options=list(_EXPIRY_DAYS.keys()),
        format_func=lambda x: t(f"cms.expiry_{x}"),
        index=0,
        key="cms_create_expiry",
    )
    expiry_days = _EXPIRY_DAYS[expiry_key]

    _save, _cancel = st.columns([1, 1], gap="small")
    with _save:
        if st.button(t("common.save"), type="primary", use_container_width=True, key="cms_save_btn"):
            with st.spinner(t("common.saving")):
                if not title.strip():
                    st.error(t("cms.error_title_required"))
                    return
                if post_type == "featured_table" and not (table_ref or "").strip():
                    st.error(t("cms.error_table_ref_required"))
                    return
                actor = st.session_state.get("user_email", "admin")
                create_post(PostParams(
                    post_type=post_type,
                    title=title.strip(),
                    body=body.strip(),
                    table_ref=(table_ref or "").strip() or None,
                    author_email=actor,
                    expiry_days=expiry_days,
                ))
                st.toast(t("common.saved"))
                st.rerun()
    with _cancel:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True, key="cms_cancel_btn"):
            st.rerun()


def _render_admin_cms_section():
    _cms_h, _cms_btn = st.columns([9, 1], gap="small")
    with _cms_h:
        st.markdown(
            f'<div class="dd-section-header" style="margin-top:32px;">'
            f'<span class="dd-eyebrow">§ {_html.escape(t("cms.section_title"))}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with _cms_btn:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("＋", key="cms_new_post", help=t("cms.new_post"), use_container_width=True):
            _show_cms_create_dialog()

    posts = get_all_posts()
    if not posts:
        _render_empty_state("📣", t("cms.no_posts"))
        return

    type_labels = {
        "announcement":  t("cms.type_announcement"),
        "featured_table": t("cms.type_featured"),
        "guide":         t("cms.type_guide"),
    }

    for post in posts:
        color    = _POST_COLOR.get(post["post_type"], "var(--ink-40)")
        lbl      = type_labels.get(post["post_type"], post["post_type"])
        from src.i18n import format_date
        created  = post["created_at"]
        expires  = post["expires_at"]
        date_str = format_date(created)
        exp_str  = format_date(expires) if expires else t("cms.no_expiry")
        from datetime import datetime, timezone; UTC = timezone.utc
        if expires is None:
            is_expired = False
        else:
            now = datetime.now(UTC)
            # Make naive datetimes (legacy rows) comparable to aware "now".
            cmp_expires = expires if expires.tzinfo else expires.replace(tzinfo=UTC)
            is_expired = cmp_expires < now

        date_range = t("cms.date_range", start=date_str, end=exp_str)
        row_html = (
            f'<div style="border-left:3px solid {color};padding:8px 12px;'
            f'background:var(--paper-deep);border-radius:0 4px 4px 0;'
            f'opacity:{"0.5" if is_expired else "1"};">'
            f'<span style="font-family:var(--font-mono);font-size:10px;'
            f'text-transform:uppercase;color:{color};letter-spacing:.08em;">{_html.escape(lbl)}</span>'
            f'<span style="font-family:var(--font-sans);font-size:14px;color:var(--ink);'
            f'margin-left:10px;">{_html.escape(post["title"])}</span>'
            f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);'
            f'margin-left:10px;">{_html.escape(date_range)}</span>'
            f'</div>'
        )

        _row_col, _del_col = st.columns([11, 1], gap="small")
        with _row_col:
            st.markdown(row_html, unsafe_allow_html=True)
        with _del_col:
            st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
            if st.button(
                "✕", key=f"cms_admin_del_{post['post_id']}",
                help=t("cms.delete_post"),
                use_container_width=True,
            ):
                _show_delete_cms_dialog(post["post_id"])
