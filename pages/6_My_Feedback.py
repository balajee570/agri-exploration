"""My Feedback — local-only log of crop recommendations that didn't work."""

from __future__ import annotations

import json

import streamlit as st

from agri import DATA_DIR
from agri.i18n import language_selector

st.set_page_config(page_title="My Feedback · KrishiCast", page_icon="📓", layout="wide")
language_selector()
st.title("📓 My Feedback")
st.markdown(
    "Recommendations you've flagged as 'didn't work for me' are recorded here. "
    "This is a personal logbook — nothing leaves the device / your Streamlit session."
)

path = DATA_DIR / "feedback.jsonl"
if not path.exists():
    st.info("No feedback recorded yet. Use the 👎 button on any recommendation card.")
    st.stop()

entries = []
for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    try:
        entries.append(json.loads(line))
    except json.JSONDecodeError:
        continue

if not entries:
    st.info("No feedback recorded yet.")
    st.stop()

st.markdown(f"### {len(entries)} entries")
import pandas as pd
df = pd.DataFrame(entries)
st.dataframe(df, use_container_width=True, hide_index=True)

if st.button("🗑️ Clear all feedback", type="secondary"):
    path.unlink(missing_ok=True)
    st.rerun()
