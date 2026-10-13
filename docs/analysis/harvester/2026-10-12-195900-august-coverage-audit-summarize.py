"""Build CSVs, proposed recovery windows and a plot from read-only exports.

Run from any directory with Python and matplotlib. This script makes no
database or provider calls and overwrites only its derived audit artifacts.
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


BASE = Path(__file__).with_name("2026-10-12-195900-august-coverage-audit")
data = json.loads(BASE.with_suffix(".json").read_text())
details = json.loads(BASE.with_name(BASE.name + "-gap-detail.json").read_text())
assert data["metadata"]["transaction_read_only"] == "on"
assert details["transaction_read_only"] == "on"


def save_csv(suffix, rows):
    with BASE.with_name(BASE.name + suffix).open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


daily = [r for r in data["daily"] if r["day"].startswith("2026-08")]
hours = data["hourly"]
for zone in ("UTC", "Asia/Tokyo"):
    zone_days = [r for r in daily if r["zone"] == zone]
    zone_hours = [r for r in hours if r["zone"] == zone]
    assert len(zone_days) == 31 and len(zone_hours) == 31 * 24
    for day in zone_days:
        day_hours = [r for r in zone_hours if r["hour"].startswith(day["day"])]
        assert sum(r["posts"] for r in day_hours) == day["posts"]
        assert sum(r["posts"] > 0 for r in day_hours) == day["populated_hours"]
        assert day["inserted_within_24h"] + day["inserted_after_24h"] == day["posts"]

save_csv("-daily.csv", daily)
save_csv("-hourly.csv", hours)
save_csv("-insert-gaps.csv", details["gap_counts"])

# One historical cycle of padding, rounded outward to quarter-hour slots.
# Merge the three August 5/6 interruptions into one bounded recovery window.
groups = [("major", [6]), ("major", [8]), ("major", [1]),
          ("major", [2]), ("major", [3, 4, 5]),
          ("smaller", [9]), ("smaller", [7])]
gaps = {r["id"]: r for r in details["gap_counts"]}
windows = []
for priority, ids in groups:
    selected = [gaps[i] for i in ids]
    first = min(datetime.fromisoformat(g["since"]) for g in selected)
    last = max(datetime.fromisoformat(g["until"]) for g in selected)
    lower = first.replace(minute=first.minute // 15 * 15, second=0, microsecond=0)
    lower -= timedelta(minutes=15)
    upper = last.replace(minute=last.minute // 15 * 15, second=0, microsecond=0)
    upper += timedelta(minutes=30)
    windows.append({
        "priority": priority,
        "evidence_gap_ids": ids,
        "since_utc": lower.isoformat(),
        "until_utc": upper.isoformat(),
        "since_jst": lower.astimezone(ZoneInfo("Asia/Tokyo")).isoformat(),
        "until_jst": upper.astimezone(ZoneInfo("Asia/Tokyo")).isoformat(),
        "padded_hours": (upper - lower).total_seconds() / 3600,
        "observed_insert_gap_hours": sum(g["gap_hours"] for g in selected),
        "stored_posts_inside_unpadded_gaps": sum(g["stored_posts_created_inside_gap"] for g in selected),
    })

manifest = {
    "schema_version": 1,
    "status": "proposed_windows_only",
    "database_snapshot_at": data["metadata"]["snapshot_at"],
    "gap_detail_snapshot_at": details["snapshot_at"],
    "scope": "August 2026 stored X posts",
    "windows": windows,
    "collection_population": "Define and pin policy/brand/list scope before execution; original August source_query_id is null.",
    "planned_credential_purpose": "on_demand",
    "execution_authorized": False,
    "live_cursors_may_advance": False,
    "paid_request_allowance": None,
    "usd_allowance": None,
}
BASE.with_name(BASE.name + "-recovery-windows.json").write_text(json.dumps(manifest, indent=2) + "\n")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

fig, axes = plt.subplots(1, 2, figsize=(15, 10), sharey=True, layout="constrained")
maximum = max(r["posts"] for r in hours)
for ax, zone in zip(axes, ("UTC", "Asia/Tokyo")):
    values = [[max(0.5, r["posts"]) for r in hours if r["zone"] == zone
               and r["hour"].startswith(f"2026-08-{day:02d}")]
              for day in range(1, 32)]
    plotted = ax.imshow(values, aspect="auto", cmap="magma",
                        norm=LogNorm(vmin=0.5, vmax=maximum))
    ax.set_title(zone)
    ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_yticks(range(31), [f"Aug {day:02d}" for day in range(1, 32)])
    ax.set_xlabel("Hour in the displayed timezone")
axes[0].set_ylabel("Post creation date")
colorbar = fig.colorbar(plotted, ax=axes, shrink=0.8)
colorbar.set_label("Stored posts per hour (logarithmic colour scale)")
colorbar.set_ticks([0.5, 1, 10, 100, 1000], labels=["0", "1", "10", "100", "1,000"])
fig.suptitle("August 2026: stored X posts by creation hour\n"
             "Dark areas mark sparse stored coverage; counts include later retrievals", fontsize=15)
fig.savefig(BASE.with_suffix(".png"), dpi=140)
plt.close(fig)

print("Validated 62 daily rows against 1,488 hourly rows.")
for row in windows:
    print(row["priority"], row["since_utc"], row["until_utc"],
          row["stored_posts_inside_unpadded_gaps"], "stored posts")
