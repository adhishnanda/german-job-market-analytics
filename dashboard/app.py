"""Streamlit entry point for the German Job Market Analytics dashboard."""

from __future__ import annotations

import streamlit as st


def main() -> None:
    """Render the dashboard."""
    st.set_page_config(page_title="German Job Market Analytics", layout="wide")
    st.title("German Job Market Analytics")
    st.info("Dashboard under construction — run the ETL pipeline first.")


if __name__ == "__main__":
    main()
