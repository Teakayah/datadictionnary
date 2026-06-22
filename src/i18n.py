from __future__ import annotations
"""Internationalisation (i18n) for the Data Dictionary.

Public API:
    LOCALES       — dict of all loaded locale data, keyed by language code
    get_locale()  — detect preferred language from browser Accept-Language header
    t(key, **kw)  — look up a dotted i18n key in the active locale
    set_locale()  — persist a locale choice into session state

Dependencies: os, json, streamlit (no databricks/msal imports — safe in tests).
"""


import json as _json
import os
import streamlit as st


def _load_locales() -> dict:
    # Resolve relative to this file's parent's parent (the repo root locale/ dir).
    base = os.path.join(os.path.dirname(__file__), "..", "locale")
    result: dict = {}
    for lang in ("en", "fr"):
        try:
            with open(os.path.join(base, f"{lang}.json"), encoding="utf-8") as f:
                result[lang] = _json.load(f)
        except Exception:
            result[lang] = {}
    return result


# Loaded once per process start — no caching decorator so restarts always
# pick up locale file changes without needing a cache-clear.
LOCALES: dict = _load_locales()


def _lookup(d: dict, parts: list) -> str | None:
    if not parts or not isinstance(d, dict):
        return None
    for p in parts:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d if isinstance(d, str) else None


def get_locale() -> str:
    """Detect preferred locale from the browser Accept-Language header."""
    try:
        header = st.context.headers.get("Accept-Language", "en")
        primary = header.split(",")[0].split(";")[0].split("-")[0].strip().lower()
        return "fr" if primary == "fr" else "en"
    except Exception:
        return "en"


def _ensure_locale() -> None:
    if "locale" not in st.session_state:
        st.session_state["locale"] = get_locale()


def format_number(val: int | float) -> str:
    """Format a number according to the active locale."""
    _ensure_locale()
    lang = st.session_state.get("locale", "en")

    lang = st.session_state.get("locale", "en")
    # Very basic locale-aware formatting using standard python string formatting
    lang = st.session_state.get("locale", "en")
    if lang == "fr":
        # French uses non-breaking space as thousand separator and comma as decimal
        if isinstance(val, int):
            return f"{val:,}".replace(",", "\xa0")
        else:
            return f"{val:,.2f}".replace(",", "\xa0").replace(".", ",")
    else:
        # Default/English uses comma as thousand separator and dot as decimal
        if isinstance(val, int):
            return f"{val:,}"
        else:
            return f"{val:,.2f}"

def format_date(dt, format_type="long") -> str:
    """Format a datetime object according to the active locale."""
    if not dt or not hasattr(dt, "strftime"):
        return str(dt or "")

    _ensure_locale()

    # 🌍 Globe: Extract hardcoded strftime which breaks localization
    month_key = str(dt.month)
    month_name = t(f"date.months.{month_key}")

    if format_type == "short":
        return t("date.short", day=f"{dt.day:02d}", month=month_name)
    else:
        time_str = dt.strftime("%H:%M")
        return t("date.long", day=f"{dt.day:02d}", month=month_name, year=dt.year, time=time_str)


def t(key: str, **kwargs) -> str:
    """Look up a dotted key (e.g. 'nav.search') in the active locale.

    Falls back to English if the key is missing in the active locale.
    Supports str.format() style placeholders: t('search.results_count', count=5).
    """
    _ensure_locale()
    lang = st.session_state.get("locale", "en")

    lang = st.session_state.get("locale", "en")
    # Pluralization support
    count_vars = ["count", "n"]
    count_val = None
    for cv in count_vars:
        if cv in kwargs and isinstance(kwargs[cv], (int, float)):
            count_val = kwargs[cv]
            break

    lang = st.session_state.get("locale", "en")

    if count_val is not None:
        suffix = "zero" if count_val == 0 else "one" if count_val == 1 else "other"
        plural_key = f"{key}_{suffix}"
        parts = plural_key.split(".")
        val = _lookup(LOCALES.get(lang, {}), parts) or _lookup(LOCALES.get("en", {}), parts)
        if val is not None:
            try:
                return val.format(**kwargs)
            except (KeyError, IndexError):
                pass

    parts = key.split(".")
    val = _lookup(LOCALES.get(lang, {}), parts) or _lookup(LOCALES.get("en", {}), parts) or key
    try:
        return val.format(**kwargs) if kwargs else val
    except (KeyError, IndexError):
        return val


def set_locale(lang: str) -> None:
    """Persist locale choice; button click already triggers the rerun."""
    st.session_state["locale"] = lang
