#!/usr/bin/env python3
"""Reproduce the MIS 5480 Anthropic Economic Index analysis and scatterplot.

Examples
--------
From the original 2026-06-26 Claude.ai release:
    python analysis.py --source /path/to/aei_claude_ai_2026-06-26.csv

From the cleaned 22-occupation CSV included in this repository:
    python analysis.py

All outputs are written beside this script. Python 3.10+ is recommended.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Enable chart generation without a display.
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np
from scipy.stats import pearsonr


REPO = Path(__file__).resolve().parent
RAW_FILENAME = "aei_claude_ai_2026-06-26.csv"
CSV_FILENAME = "filtered_data.csv"
CHART_FILENAME = "scatterplot.png"

RAW_FILTER = {
    "date_start": "2026-05-01",
    "geo_id": "GLOBAL",
    "geo_level": "global",
    "category_name": "soc_occupation",
    "hierarchy_level": "1",
}

METRICS = {
    "pct": "claude_usage_share_pct",
    "collaboration_bucket_automation_pct": "automation_pct",
    "collaboration_bucket_augmentation_pct": "augmentation_pct",
    "human_only_time_mean": "human_only_estimated_hours",
    "human_with_ai_time_mean": "with_ai_estimated_minutes",
}

OUTPUT_COLUMNS = [
    "month", "geo_id", "soc_major_code", "occupation_group",
    "claude_usage_share_pct", "automation_pct", "augmentation_pct",
    "human_only_estimated_hours", "with_ai_estimated_minutes",
    "estimated_time_saved_pct_from_means",
]


def calculate_time_saved_pct(human_only_hours: float, with_ai_minutes: float) -> float:
    """Ratio of group mean *estimated* durations, not observed task savings."""
    baseline_minutes = human_only_hours * 60.0
    if baseline_minutes <= 0:
        raise ValueError("Estimated human-only task duration must be positive.")
    return 100.0 * (baseline_minutes - with_ai_minutes) / baseline_minutes


def read_from_raw(path: Path) -> list[dict[str, object]]:
    """Filter the large original CSV as a stream, then pivot five metrics per SOC group."""
    groups: dict[str, dict[str, object]] = {}
    matched_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = set(RAW_FILTER) | {"metric_id", "value", "node_name", "node_external_id"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Original dataset is missing columns: {sorted(required - set(reader.fieldnames or []))}")

        for row in reader:
            if not all(row[key] == value for key, value in RAW_FILTER.items()):
                continue
            metric = METRICS.get(row["metric_id"])
            if metric is None:
                continue
            matched_rows += 1
            soc_code = row["node_external_id"].strip()
            name = row["node_name"].strip()
            if not soc_code or not name:
                raise ValueError("A matching occupational group is missing a code or name.")
            record = groups.setdefault(soc_code, {
                "month": "2026-05", "geo_id": "GLOBAL",
                "soc_major_code": soc_code, "occupation_group": name,
            })
            if record["occupation_group"] != name:
                raise ValueError(f"Inconsistent names for SOC group {soc_code}.")
            if metric in record:
                raise ValueError(f"Duplicate SOC group + metric: {soc_code} / {metric}")
            record[metric] = float(row["value"])

    rows = []
    for soc_code, record in sorted(groups.items(), key=lambda item: int(item[0])):
        missing = set(METRICS.values()) - set(record)
        if missing:
            raise ValueError(f"Missing metrics for SOC {soc_code}: {sorted(missing)}")
        record["estimated_time_saved_pct_from_means"] = calculate_time_saved_pct(
            float(record["human_only_estimated_hours"]),
            float(record["with_ai_estimated_minutes"]),
        )
        rows.append(record)

    if len(rows) != 22 or matched_rows != 110:
        raise ValueError(
            f"Unexpected data coverage: {len(rows)} groups and {matched_rows} metric rows "
            "(expected 22 groups x 5 metrics = 110)."
        )
    print(f"Raw dataset: filtered {matched_rows} metric rows into {len(rows)} SOC major groups.")
    return rows


def read_from_filtered(path: Path) -> list[dict[str, object]]:
    """Read the compact source, verify its content, and recalculate savings."""
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(OUTPUT_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Filtered file is missing columns: {sorted(missing)}")
        for record in reader:
            if record["month"] != "2026-05" or record["geo_id"] != "GLOBAL":
                raise ValueError("Expected May 2026 global observations only.")
            cleaned: dict[str, object] = {
                field: record[field]
                for field in ("month", "geo_id", "soc_major_code", "occupation_group")
            }
            for metric in METRICS.values():
                cleaned[metric] = float(record[metric])
            recomputed = calculate_time_saved_pct(
                float(cleaned["human_only_estimated_hours"]),
                float(cleaned["with_ai_estimated_minutes"]),
            )
            if abs(float(record["estimated_time_saved_pct_from_means"]) - recomputed) > 0.001:
                raise ValueError(f"Time savings mismatch: {record['occupation_group']}")
            cleaned["estimated_time_saved_pct_from_means"] = recomputed
            rows.append(cleaned)

    codes = [str(row["soc_major_code"]) for row in rows]
    if len(rows) != 22 or len(set(codes)) != 22:
        raise ValueError("Expected exactly 22 unique SOC major occupation groups.")
    rows.sort(key=lambda record: int(str(record["soc_major_code"])))
    print("Loaded and validated the supplied 22-group filtered CSV.")
    return rows


def save_filtered(rows: list[dict[str, object]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            for metric in METRICS.values():
                output[metric] = f"{float(row[metric]):.2f}"
            output["estimated_time_saved_pct_from_means"] = (
                f"{float(row['estimated_time_saved_pct_from_means']):.4f}"
            )
            writer.writerow({column: output[column] for column in OUTPUT_COLUMNS})


def make_chart(rows: list[dict[str, object]], r: float, p_value: float, path: Path) -> None:
    x = np.array([float(record["automation_pct"]) for record in rows])
    y = np.array([float(record["estimated_time_saved_pct_from_means"]) for record in rows])

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#c5ccd4", "axes.labelcolor": "#253346",
        "xtick.color": "#5f6b78", "ytick.color": "#5f6b78",
    })
    fig, ax = plt.subplots(figsize=(13.6, 7.6), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    fig.subplots_adjust(left=0.08, right=0.97, bottom=0.17, top=0.78)

    ax.scatter(x, y, s=69, facecolor="#1479b8", edgecolors="white",
               linewidths=1.1, alpha=0.96, zorder=3)
    slope, intercept = np.polyfit(x, y, 1)
    trend_x = np.array([30, 80])
    ax.plot(trend_x, slope * trend_x + intercept, color="#384a5c",
            linestyle=(0, (5, 4)), linewidth=1.6, zorder=2)

    ax.set_xlim(30, 80)
    ax.set_ylim(55, 96)
    ax.set_xlabel("AI automation rate (% of Claude task interactions)", labelpad=13)
    ax.set_ylabel("Estimated task time saved (%)", labelpad=11)
    ax.xaxis.set_major_locator(MultipleLocator(10))
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.grid(True, color="#dce4ec", linewidth=0.85, alpha=0.73, zorder=0)

    # Selective annotations make the comparisons clear without labeling all 22 dots.
    annotate = {
        "Legal": (9, 10, "left", "Legal: 86.3%"),
        "Protective Service": (-10, 16, "right", "Protective service: 86.7%"),
        "Office and Administrative Support": (-10, 17, "right", "Office/admin: 90.3%"),
        "Community and Social Service": (11, 4, "left", "Community/social service: 62.0%"),
        "Healthcare Support": (-18, -17, "right", "Healthcare support: 70.8%"),
        "Healthcare Practitioners and Technical": (17, 14, "left", "Healthcare practitioners: 71.9%"),
    }
    for row in rows:
        name = str(row["occupation_group"])
        if name not in annotate:
            continue
        dx, dy, align, label = annotate[name]
        ax.annotate(label,
                    xy=(float(row["automation_pct"]),
                        float(row["estimated_time_saved_pct_from_means"])),
                    xytext=(dx, dy), textcoords="offset points",
                    ha=align, va="center", fontsize=8.75,
                    color="#24384c",
                    arrowprops=dict(arrowstyle="-", color="#8aa0b0", lw=0.75),
                    bbox=dict(boxstyle="round,pad=0.21", facecolor="white",
                              edgecolor="none", alpha=0.93),
                    zorder=5)

    stats_text = (
        f"Pearson r = {r:.2f}   |   p = {p_value:.2f}  (not significant)\n"
        f"R² = {r*r:.3f} ({r*r*100:.1f}% of variance)   |   n = {len(rows)}"
    )
    ax.text(0.985, 0.065, stats_text, transform=ax.transAxes,
            va="bottom", ha="right", fontsize=9.8, color="#21384b",
            bbox=dict(boxstyle="round,pad=0.65", facecolor="#f5f8fb",
                      edgecolor="#d8e3ed", linewidth=0.8))

    fig.text(0.08, 0.93, "More AI Automation Doesn't Necessarily Mean More Time Savings",
             ha="left", va="top", fontsize=19.5, fontweight="bold", color="#102b40")
    fig.text(0.08, 0.885,
             "May 2026  ·  Global Claude.ai usage  ·  22 major occupational groups",
             ha="left", va="top", fontsize=12, color="#566779")
    fig.text(0.08, 0.065,
             "Source: Anthropic Economic Index, June 2026 release (May 2026 observations).",
             ha="left", va="center", fontsize=9.4, color="#657487")
    fig.text(0.08, 0.041,
             "Time saved = ratio of estimated group-mean task durations; not observed job productivity or decision quality.",
             ha="left", va="center", fontsize=9.0, color="#657487")
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=None,
        help="Path to original Anthropic CSV. If omitted, use the included filtered_data.csv.",
    )
    args = parser.parse_args()
    if args.source is not None:
        raw_path = args.source.expanduser().resolve()
        if not raw_path.is_file():
            parser.error(f"Original CSV not found: {raw_path}")
        rows = read_from_raw(raw_path)
    elif (REPO / CSV_FILENAME).is_file():
        rows = read_from_filtered(REPO / CSV_FILENAME)
    elif (REPO / RAW_FILENAME).is_file():
        rows = read_from_raw(REPO / RAW_FILENAME)
    else:
        parser.error("No data available. Supply --source PATH to the original CSV.")

    # Sanity checks for eligible records.
    for record in rows:
        automation = float(record["automation_pct"])
        augmentation = float(record["augmentation_pct"])
        if not (0 <= automation <= 100 and 0 <= augmentation <= 100):
            raise ValueError("Automation and augmentation rates must be percentages.")
        if not math.isclose(automation + augmentation, 100.0, abs_tol=0.05):
            raise ValueError(f"Collaboration rates do not sum to ~100 for {record['occupation_group']}")
    x = np.asarray([float(rec["automation_pct"]) for rec in rows])
    y = np.asarray([float(rec["estimated_time_saved_pct_from_means"]) for rec in rows])
    result = pearsonr(x, y)  # Two-sided Pearson test, occupation groups equally weighted.
    r, p_value = float(result.statistic), float(result.pvalue)
    if not (np.isfinite(r) and np.isfinite(p_value)):
        raise ValueError("Correlation could not be calculated.")

    save_filtered(rows, REPO / CSV_FILENAME)
    make_chart(rows, r, p_value, REPO / CHART_FILENAME)
    print(f"Pearson r: {r:.4f}   p-value: {p_value:.4f}   R²: {r*r:.4f}")
    print(f"Mean estimated time saved (unweighted across occupations): {y.mean():.1f}%")
    print(f"Min / max estimated time saved: {y.min():.1f}% / {y.max():.1f}%")
    print(f"Created: {REPO / CSV_FILENAME}")
    print(f"Created: {REPO / CHART_FILENAME}")


if __name__ == "__main__":
    main()
