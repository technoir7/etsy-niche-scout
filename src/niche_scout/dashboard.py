"""Local Streamlit dashboard for browsing Etsy Niche Scout outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import streamlit as st

from niche_scout.comparison import compare_dataframes
from niche_scout.config import ROOT_DIR, load_clustering
from niche_scout.exporters import ranked_to_dataframe
from niche_scout.main import load_ranked_payload


def _default_payload_path() -> Path:
    return ROOT_DIR / "data/processed/latest.json"


def _load_payload(path: Path):
    return load_ranked_payload(path)


def render_dashboard(payload_path: Path, compare_payload_path: Path | None = None) -> None:
    payload = _load_payload(payload_path)
    keywords_df = ranked_to_dataframe(payload.ranked_keywords)
    families_df = pd.DataFrame([family.model_dump() for family in payload.families])
    listing_lookup = {result.normalized_query: result for result in payload.search_results}
    compare_payload = _load_payload(compare_payload_path) if compare_payload_path else None
    compare_keywords_df = ranked_to_dataframe(compare_payload.ranked_keywords) if compare_payload else pd.DataFrame()
    compare_families_df = pd.DataFrame([family.model_dump() for family in compare_payload.families]) if compare_payload else pd.DataFrame()

    st.set_page_config(page_title="Etsy Niche Scout", layout="wide")
    st.title("Etsy Niche Scout")
    st.caption(f"Run: {payload.run_id or 'n/a'}")
    if compare_payload:
        st.caption(f"Comparing against: {compare_payload.run_id or compare_payload_path}")

    st.sidebar.header("Data")
    st.sidebar.write(str(payload_path))
    min_score = st.sidebar.slider("Minimum blended score", 0, 100, 50)
    query_filter = st.sidebar.text_input("Keyword search", "")
    cluster_filter = st.sidebar.multiselect(
        "Clusters",
        options=sorted(keywords_df["cluster_label"].dropna().unique().tolist()) if not keywords_df.empty else [],
    )

    filtered = keywords_df.copy()
    if "blended_score" in filtered.columns:
        filtered = filtered[filtered["blended_score"].fillna(filtered["total_score"]) >= min_score]
    if query_filter:
        filtered = filtered[filtered["query"].str.contains(query_filter, case=False, na=False)]
    if cluster_filter:
        filtered = filtered[filtered["cluster_label"].isin(cluster_filter)]

    tab_names = ["Run Overview", "Keyword Table", "Cluster View", "Listing Inspector", "Reports / Exports"]
    if compare_payload:
        tab_names.append("Comparison")
    overview = st.tabs(tab_names)

    with overview[0]:
        col1, col2, col3 = st.columns(3)
        col1.metric("Keywords", len(keywords_df))
        col2.metric("Clusters", len(families_df))
        col3.metric(
            "Top Score",
            f"{keywords_df['blended_score'].max():.1f}" if "blended_score" in keywords_df and not keywords_df.empty else "n/a",
        )
        st.subheader("Top Opportunities")
        st.dataframe(filtered.head(15), use_container_width=True)

    with overview[1]:
        table_columns = [
            column
            for column in [
                "query",
                "cluster_label",
                "blended_score",
                "total_score",
                "family_type",
                "median_price",
                "search_volume",
                "competition",
                "import_impact_score",
                "warnings",
            ]
            if column in filtered.columns
        ]
        st.dataframe(filtered[table_columns], use_container_width=True, hide_index=True)

    with overview[2]:
        st.subheader("Families")
        st.dataframe(families_df, use_container_width=True, hide_index=True)

    with overview[3]:
        keyword_options = filtered["query"].tolist() if not filtered.empty else keywords_df["query"].tolist()
        selected = st.selectbox("Keyword", options=keyword_options)
        if selected:
            selected_row = keywords_df[keywords_df["query"] == selected].iloc[0]
            if "warnings" in selected_row and selected_row["warnings"]:
                st.warning(str(selected_row["warnings"]))
            normalized_query = str(selected_row["normalized_query"])
            search_result = listing_lookup.get(normalized_query)
            if search_result:
                listings_df = pd.DataFrame([listing.model_dump() for listing in search_result.listings])
                st.dataframe(listings_df, use_container_width=True, hide_index=True)
            else:
                st.info("No listing payload was found for this keyword.")

    with overview[4]:
        processed_dir = ROOT_DIR / "data/processed"
        reports_dir = ROOT_DIR / "data/reports"
        csv_path = processed_dir / "latest.csv"
        families_csv_path = processed_dir / "families-latest.csv"
        listings_csv_path = processed_dir / "listings-latest.csv"
        json_path = processed_dir / "latest.json"
        md_path = reports_dir / "latest.md"
        for label, path in [
            ("Keywords CSV", csv_path),
            ("Families CSV", families_csv_path),
            ("Listings CSV", listings_csv_path),
            ("JSON", json_path),
            ("Markdown", md_path),
        ]:
            if path.exists():
                st.download_button(label=f"Download {label}", data=path.read_bytes(), file_name=path.name)

    if compare_payload:
        with overview[5]:
            comparison = compare_dataframes(
                keywords_df,
                compare_keywords_df,
                (payload.run_id or "baseline", compare_payload.run_id or "comparison"),
                load_clustering(),
            )
            st.subheader("Keyword Deltas")
            changes_df = pd.DataFrame([item.model_dump() for item in comparison.changed_keywords])
            st.dataframe(changes_df, use_container_width=True, hide_index=True)

            st.subheader("Family Deltas")
            if not families_df.empty and not compare_families_df.empty:
                family_delta = families_df.merge(
                    compare_families_df,
                    on="cluster_name",
                    how="outer",
                    suffixes=("_baseline", "_comparison"),
                )
                if "family_score_baseline" in family_delta.columns and "family_score_comparison" in family_delta.columns:
                    family_delta["family_score_delta"] = (
                        family_delta["family_score_comparison"].fillna(0) - family_delta["family_score_baseline"].fillna(0)
                    )
                st.dataframe(family_delta, use_container_width=True, hide_index=True)
            st.write("New keywords:", comparison.new_keywords[:20])
            st.write("Removed keywords:", comparison.removed_keywords[:20])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", default=str(_default_payload_path()))
    parser.add_argument("--compare-payload", default=None)
    args = parser.parse_args()
    render_dashboard(Path(args.payload), Path(args.compare_payload) if args.compare_payload else None)


if __name__ == "__main__":
    main()
