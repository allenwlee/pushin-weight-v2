"""Render static, bounded comparison charts for the September 17 trial update.

The numbers are intentionally source-cohort-specific delivery/error counts, not
population accuracy estimates.  Sources are cited in the report section that
embeds these assets.
"""

from pathlib import Path

import matplotlib.pyplot as plt


OUTPUT = Path(__file__).with_name("2026-09-17-221500-model-task-current-results")


def bar_labels(ax, values, suffix):
    for index, value in enumerate(values):
        ax.text(value + 0.25, index, f"{value}{suffix}", va="center", fontsize=9)


def main():
    figure, axes = plt.subplots(3, 1, figsize=(10, 10.5))
    figure.subplots_adjust(top=0.91, bottom=0.09, hspace=0.72)
    figure.suptitle(
        "September 17 model-task diagnostics — cohort-specific counts", fontsize=14,
        fontweight="bold"
    )

    labels = ["Qwen classifier v6 — strict", "Qwen classifier v6 — replay", "Direct V4.1 classifier — strict"]
    values = [16, 22, 24]
    axes[0].barh(labels, values, color=["#d95f02", "#e6ab02", "#1b9e77"])
    axes[0].set(xlim=(0, 25), xlabel="complete paired source records (replay does not add labels)", title="Classifier delivery: exact 24-source expanded-taxonomy cohort")
    bar_labels(axes[0], values, "/24")

    labels = ["Direct V4.1 baseline", "Qwen translation v4"]
    values = [7, 11]
    axes[1].barh(labels, values, color=["#7570b3", "#d95f02"])
    axes[1].set(xlim=(0, 24), xlabel="confirmed erroneous source posts (both arms also have 1 unresolved source)", title="Translation semantic review: same 24-source cohort")
    bar_labels(axes[1], values, "/24")

    labels = ["Direct V4.1 baseline", "Gemini commentary v3"]
    semantic = [5, 5]
    coverage = [2, 0]
    axes[2].barh(labels, semantic, color="#7570b3", label="semantic error")
    axes[2].barh(labels, coverage, left=semantic, color="#e6ab02", label="pre-call coverage failure")
    axes[2].set(xlim=(0, 24), xlabel="confirmed affected source posts", title="Commentary: semantic and delivery defects, same 24-source cohort")
    axes[2].legend(loc="lower right", fontsize=8)
    axes[2].text(5.2, 0, "5 semantic + 2 coverage = 7", va="center", fontsize=9)
    axes[2].text(5.2, 1, "5 semantic", va="center", fontsize=9)

    for axis in axes:
        axis.xaxis.grid(True, alpha=0.25)
        axis.set_axisbelow(True)
    figure.savefig(OUTPUT.with_suffix(".svg"), format="svg", bbox_inches="tight")
    figure.savefig(OUTPUT.with_suffix(".png"), dpi=180, bbox_inches="tight")


if __name__ == "__main__":
    main()
