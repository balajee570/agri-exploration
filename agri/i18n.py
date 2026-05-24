"""Light-weight i18n helpers — English / Hindi toggle for crop names and key UI strings."""

from __future__ import annotations

from typing import Any

try:
    import streamlit as st
except ImportError:
    st = None

LANG_LABELS = {"en": "English", "hi": "हिन्दी"}


def current_lang() -> str:
    if st is None or not hasattr(st, "session_state"):
        return "en"
    return st.session_state.get("lang", "en")


def language_selector(location: str = "sidebar") -> str:
    if st is None:
        return "en"
    container = st.sidebar if location == "sidebar" else st
    choice = container.radio(
        "Language · भाषा",
        options=list(LANG_LABELS.keys()),
        index=list(LANG_LABELS.keys()).index(current_lang()),
        format_func=lambda k: LANG_LABELS[k],
        horizontal=True,
        key="lang_selector",
    )
    st.session_state["lang"] = choice
    return choice


def crop_name(crop: dict[str, Any], lang: str | None = None) -> str:
    lang = lang or current_lang()
    if lang == "hi" and crop.get("name_hi"):
        return f"{crop['name_hi']} ({crop['name_en']})"
    return crop["name_en"]
