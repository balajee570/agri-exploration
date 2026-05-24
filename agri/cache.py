"""Cache wrappers that work with or without Streamlit at import time."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

try:
    import streamlit as st

    def cached(ttl_seconds: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return st.cache_data(ttl=ttl_seconds, show_spinner=False)

except ImportError:  # tests / non-Streamlit contexts

    def cached(ttl_seconds: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            return wrapper

        return decorator


TTL_FORECAST = 60 * 60
TTL_ARCHIVE = 24 * 60 * 60
TTL_CLIMATE = 24 * 60 * 60
TTL_GEOCODE = 7 * 24 * 60 * 60
TTL_POWER = 24 * 60 * 60
