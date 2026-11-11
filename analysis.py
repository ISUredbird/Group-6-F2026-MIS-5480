"""MIS 5480: AI Productivity Paradox — Anthropic Economic Index analysis.

Run: python analysis.py

The included filtered_data.csv is enough to reproduce the statistics and chart.
To repeat the filtering and reshaping from the original data, download the
Anthropic Claude.ai CSV and place it in this folder before running the script.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


# Files are saved in the same folder as this script.
folder = Path(__file__).parent
raw_file = folder / "aei_claude_ai_2026-06-26.csv"
clean_file = folder / "filtered_data.csv"
chart_file = folder / "scatterplot.png"

# These are the five Anthropic measures used in our analysis.
metrics = {
    "pct": "claude_usage_share_pct",
    "collaboration_bucket_automation_pct": "automation_pct",
    "collaboration_bucket_augmentation_pct": "augmentation_pct",
    "human_only_time_mean": "human_only_estimated_hours",
    "human_with_ai_time_mean": "with_ai_estimated_minutes",
}

# STEP 1: Read and filter the original data, if it has been downloaded.
# The original file is large, so we read it in smaller chunks.
if raw_file.exists():
    matching_rows = []

    for chunk in pd.read_csv(raw_file, chunksize=100000):
        selected = chunk.loc[
            (chunk["date_start"] == "2026-05-01")
            & (chunk["geo_id"] == "GLOBAL")
            & (chunk["geo_level"] == "global")
            & (chunk["category_name"] == "soc_occupation")
            & (chunk["hierarchy_level"] == 1)
            & (chunk["metric_id"].isin(metrics)),
            ["node_external_id", "node_name", "metric_id", "value"],
        ]
        matching_rows.append(selected)

    data = pd.concat(matching_rows, ignore_index=True)
    print("Raw rows after filtering:", len(data))

    # STEP 2: Turn the five metric rows per occupation into five columns.
    # pivot() also alerts us if the same occupation and metric are duplicated.
    data = data.pivot(
        index=["node_external_id", "node_name"],
        columns="metric_id",
        values="value",
    ).reset_index()

    data = data.rename(columns={
        "node_external_id": "soc_major_code",
        "node_name": "occupation_group",
    })
    data = data.rename(columns=metrics)
    data["month"] = "2026-05"
    data["geo_id"] = "GLOBAL"

else:
    # The small CSV is included on GitHub so the analysis runs without
    # downloading the full dataset.
    data = pd.read_csv(clean_file)
    print("Using included filtered_data.csv")

# STEP 3: Check missing data and calculate estimated task time savings.
needed = list(metrics.values())
if data[needed].isna().any().any():
    raise ValueError("Missing values in the analysis columns")
if len(data) != 22:
    raise ValueError("Expected 22 major occupation groups")
if (data["human_only_estimated_hours"] <= 0).any():
    raise ValueError("Human-only task time must be positive")

# Convert hours to minutes, then calculate percentage reduction in duration.
data["estimated_time_saved_pct_from_means"] = (
    (data["human_only_estimated_hours"] * 60 - data["with_ai_estimated_minutes"])
    / (data["human_only_estimated_hours"] * 60) * 100
)

# Keep the same ten columns in the downloadable cleaned dataset.
columns = ["month", "geo_id", "soc_major_code", "occupation_group",
           "claude_usage_share_pct", "automation_pct", "augmentation_pct",
           "human_only_estimated_hours", "with_ai_estimated_minutes",
           "estimated_time_saved_pct_from_means"]
data = data[columns].sort_values("soc_major_code")
data.to_csv(clean_file, index=False, float_format="%.4f")

# STEP 4: Measure the association across the 22 occupation groups.
x = data["automation_pct"]
y = data["estimated_time_saved_pct_from_means"]
r, p_value = pearsonr(x, y)

print("Occupational groups:", len(data))
print(f"Pearson correlation: {r:.4f}")
print(f"P-value: {p_value:.4f}")
print(f"R-squared: {r ** 2:.4f}")
print(f"Mean estimated time saved: {y.mean():.1f}%")

# STEP 5: Create a simple scatterplot with a descriptive trendline.
plt.figure(figsize=(12, 7))
plt.scatter(x, y, color="steelblue", s=48)

slope, intercept = np.polyfit(x, y, 1)
line_x = np.array([30, 80])
plt.plot(line_x, slope * line_x + intercept, "--", color="gray")

# Label a few occupations that help illustrate the finding.
labels = {
    "Legal": (6, 8),
    "Protective Service": (7, 8),
    "Office and Administrative Support": (-80, 10),
    "Community and Social Service": (7, -12),
}
for name, offset in labels.items():
    point = data.loc[data["occupation_group"] == name].iloc[0]
    plt.annotate(name, (point["automation_pct"],
                        point["estimated_time_saved_pct_from_means"]),
                 xytext=offset, textcoords="offset points", fontsize=9)

plt.title("More AI Automation Doesn't Necessarily Mean More Time Savings", fontsize=15)
plt.xlabel("AI automation rate (% of Claude task interactions)")
plt.ylabel("Estimated task time saved (%)")
plt.xlim(30, 80)
plt.ylim(55, 96)
plt.grid(alpha=0.25)
plt.text(0.98, 0.04, f"Pearson r = {r:.2f}   |   p = {p_value:.2f}   |   n = {len(data)}",
         transform=plt.gca().transAxes, ha="right",
         bbox=dict(facecolor="white", edgecolor="lightgray"))
plt.figtext(0.10, 0.01,
            "Source: Anthropic Economic Index, May 2026 global Claude.ai data. "
            "Time savings are estimates, not measured job productivity.", fontsize=8)
plt.tight_layout(rect=[0, 0.04, 1, 1])
plt.savefig(chart_file, dpi=180)
plt.close()
print("Saved:", clean_file.name, "and", chart_file.name)
