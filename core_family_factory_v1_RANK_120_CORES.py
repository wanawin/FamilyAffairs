#!/usr/bin/env python3
# Core Family Factory v1
# Rank all 120 Pick-4 AABC core families and create starter member matrices.

from __future__ import annotations

import itertools
import re
from collections import Counter
from io import StringIO

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Core Family Factory v1", layout="wide")

BUILD_MARKER = "BUILD: core_family_factory_v1__2026-06-16_RANK_120_CORES_MEMBER_MATRIX_STARTER"

st.title("Core Family Factory v1")
st.caption(BUILD_MARKER)
st.info(
    "Step 1 of the full-family app: rank all 120 AABC core families by hit count, "
    "show member behavior, and export build-order files. No betting logic is changed or simulated."
)


def read_upload(file) -> pd.DataFrame:
    raw = file.getvalue().decode("utf-8", errors="replace")
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(StringIO(raw), dtype=str)
    try:
        return pd.read_csv(StringIO(raw), sep="\t", dtype=str)
    except Exception:
        return pd.read_csv(StringIO(raw), sep=None, engine="python", dtype=str)


def norm4(x) -> str:
    digits = re.findall(r"\d", str(x))
    if len(digits) < 4:
        return ""
    return "".join(digits[:4])


def sorted_digits4(x) -> str:
    s = norm4(x)
    if len(s) != 4:
        return ""
    return "".join(sorted(s))


def classify_pick4_family(result4: str):
    s = sorted_digits4(result4)
    if len(s) != 4:
        return "", "", "", False

    c = Counter(s)
    counts = sorted(c.values(), reverse=True)

    # exact one-pair double only: AABC / ABBC / ABCC
    if counts != [2, 1, 1]:
        return "", s, "", False

    repeat_digit = next(d for d, n in c.items() if n == 2)
    core_id = "".join(sorted(c.keys()))
    member = s
    return core_id, member, repeat_digit, True


def all_120_cores():
    return ["".join(c) for c in itertools.combinations("0123456789", 3)]


def core_members(core_id: str):
    digs = list(str(core_id))
    out = []
    for d in digs:
        out.append("".join(sorted(digs + [d])))
    return sorted(out)


def infer_member_matrix(member_counts: dict, core_id: str):
    rows = []
    for m in core_members(core_id):
        rows.append({"core_id": core_id, "member": m, "hit_count": int(member_counts.get(m, 0))})
    df = pd.DataFrame(rows).sort_values(["hit_count", "member"], ascending=[False, True]).reset_index(drop=True)
    labels = ["strongest_candidate", "middle_candidate", "suppressed_candidate"]
    df["matrix_slot"] = [labels[i] for i in range(len(df))]
    return df


def build_factory_outputs(hist: pd.DataFrame):
    cols_lower = {str(c).strip().lower(): c for c in hist.columns}

    result_col = None
    for c in ["result4", "result", "winning number", "winningnumber", "number"]:
        if c in cols_lower:
            result_col = cols_lower[c]
            break
    if result_col is None:
        raise ValueError("Could not find a result column. Expected Result4 or Result.")

    date_col = cols_lower.get("date")
    stream_col = cols_lower.get("streamkey")

    df = hist.copy()
    df["Result4_factory"] = df[result_col].map(norm4)
    df = df[df["Result4_factory"].str.len() == 4].copy()

    fam = df["Result4_factory"].map(classify_pick4_family)
    df["core_id"] = fam.map(lambda x: x[0])
    df["member"] = fam.map(lambda x: x[1])
    df["repeat_digit"] = fam.map(lambda x: x[2])
    df["is_aabc_single_pair"] = fam.map(lambda x: x[3])

    doubles = df[df["is_aabc_single_pair"]].copy()

    counts = doubles.groupby("core_id").size().rename("hit_count").reset_index()
    allcores = pd.DataFrame({"core_id": all_120_cores()})
    rank = allcores.merge(counts, on="core_id", how="left").fillna({"hit_count": 0})
    rank["hit_count"] = rank["hit_count"].astype(int)
    rank["members"] = rank["core_id"].map(lambda x: ",".join(core_members(x)))

    total_draws = len(df)
    total_doubles = len(doubles)
    rank["pct_of_all_draws"] = (rank["hit_count"] / total_draws * 100).round(3) if total_draws else 0
    rank["pct_of_aabc_doubles"] = (rank["hit_count"] / total_doubles * 100).round(3) if total_doubles else 0
    rank = rank.sort_values(["hit_count", "core_id"], ascending=[False, True]).reset_index(drop=True)
    rank.insert(0, "build_order", range(1, len(rank) + 1))

    member_counts_by_core = doubles.groupby(["core_id", "member"]).size().reset_index(name="hit_count")
    matrix_rows = []
    for core in all_120_cores():
        sub = member_counts_by_core[member_counts_by_core["core_id"] == core]
        lookup = dict(zip(sub["member"], sub["hit_count"]))
        matrix_rows.append(infer_member_matrix(lookup, core))
    matrix = pd.concat(matrix_rows, ignore_index=True)

    last5 = pd.DataFrame()
    if date_col:
        tmp = doubles.copy()
        tmp["Date_factory"] = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp = tmp.dropna(subset=["Date_factory"]).sort_values("Date_factory")
        keep_cols = ["core_id", "member", "Result4_factory", "Date_factory"]
        if stream_col:
            keep_cols.append(stream_col)
        last5 = tmp.groupby("core_id", group_keys=False).tail(5)[keep_cols].copy()
        last5["Date_factory"] = last5["Date_factory"].dt.strftime("%Y-%m-%d")

    core_hist_cols = []
    for c in [date_col, stream_col, result_col]:
        if c and c not in core_hist_cols:
            core_hist_cols.append(c)
    core_history = doubles[core_hist_cols + ["Result4_factory", "core_id", "member", "repeat_digit"]].copy()

    summary = pd.DataFrame([
        {"metric": "total_valid_pick4_rows", "value": total_draws},
        {"metric": "total_AABC_single_pair_double_rows", "value": total_doubles},
        {"metric": "AABC_double_rate_pct", "value": round(total_doubles / total_draws * 100, 2) if total_draws else 0},
        {"metric": "cores_ranked", "value": 120},
    ])

    return summary, rank, matrix, last5, core_history


history_file = st.file_uploader("Upload full clean Pick-4 history", type=["csv", "txt", "tsv"])

if not history_file:
    st.stop()

try:
    hist = read_upload(history_file)
    st.success(f"Loaded history: {len(hist):,} rows")
    summary, rank, matrix, last5, core_history = build_factory_outputs(hist)
except Exception as e:
    st.error(f"Factory build failed: {e}")
    st.stop()

st.subheader("Factory Summary")
st.dataframe(summary, use_container_width=True, hide_index=True)

st.subheader("Build Order — All 120 Core Families")
st.dataframe(rank, use_container_width=True, hide_index=True)

top_n = st.slider("Show member matrix starter for top N cores", 5, 120, 25)
top_cores = rank.head(top_n)["core_id"].tolist()

st.subheader(f"Member Matrix Starter — Top {top_n}")
st.caption("Starter heuristic only: strongest/middle/suppressed by historical member hit count.")
st.dataframe(matrix[matrix["core_id"].isin(top_cores)], use_container_width=True, hide_index=True)

if not last5.empty:
    st.subheader("Last 5 Win Rows Per Core")
    st.dataframe(last5[last5["core_id"].isin(top_cores)], use_container_width=True, hide_index=True)

st.subheader("Downloads")

st.download_button(
    "Download core build order CSV",
    rank.to_csv(index=False).encode("utf-8"),
    file_name="core_family_build_order_120.csv",
    mime="text/csv",
)

st.download_button(
    "Download member matrix starter CSV",
    matrix.to_csv(index=False).encode("utf-8"),
    file_name="core_family_member_matrix_starter.csv",
    mime="text/csv",
)

st.download_button(
    "Download core history rows CSV",
    core_history.to_csv(index=False).encode("utf-8"),
    file_name="core_family_history_rows_AABC_only.csv",
    mime="text/csv",
)

if not last5.empty:
    st.download_button(
        "Download last 5 win rows per core CSV",
        last5.to_csv(index=False).encode("utf-8"),
        file_name="core_family_last5_win_rows.csv",
        mime="text/csv",
    )

st.info(
    "Next factory module will adapt the saved CORE025 truth/separator schema templates "
    "for each target core, then export core-specific app packages."
)
