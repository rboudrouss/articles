#!/usr/bin/env python3
"""Generate the benchmark charts for the OCaml Workshop 2026 slides.

Reads bench/results/latest.json from the mopsa-emcc repo (medians over ~100
reps per file/target) and renders PDF+PNG figures sized for beamer 16:9.
"""

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DATA = Path.home() / "Documents/mopsa-emcc/bench/results/latest.json"

# dataviz reference palette, light mode (validated categorical order)
BLUE = "#2a78d6"   # slot 1 -> wasm (ours)
ORANGE = "#eb6834" # slot 2 -> jsoo
AQUA = "#1baf7a"   # slot 3 -> native
GRAY = "#8a8a85"
TEXT = "#1a1a19"
MUTED = "#5f5e58"
GRID = "#d9d8d2"
BG = "#FAFAFA"  # metropolis theme background

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Fira Sans", "DejaVu Sans"],
    "font.size": 11,
    "text.color": TEXT,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
})

rows = json.load(open(DATA))["rows"]


def rows_for(target, lang=None):
    return [r for r in rows if r["target"] == target and r["status"] == "ok"
            and (lang is None or r["lang"] == lang)]


def med(vals):
    return statistics.median(vals)


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{name}.{ext}", bbox_inches="tight",
                    dpi=200 if ext == "png" else None)
    plt.close(fig)
    print(f"wrote {name}.pdf/.png")


# ---------------------------------------------------------------- chart 1
# Slowdown vs native, warm runs, per file (C + Python corpus).
# Job: magnitude comparison -> horizontal bars, one hue.
def chart_slowdown():
    native = {r["id"]: r["runMs"] for r in rows_for("native")}
    wasm = {r["id"]: r.get("runWarmMs") or r["runMs"] for r in rows_for("wasm-node")}
    items = []
    for lang, label in (("c", "C"), ("python", "Python")):
        for r in rows_for("wasm-node", lang):
            fid = r["id"]
            items.append((lang, fid.split("/")[-1], wasm[fid] / native[fid]))
    items.sort(key=lambda t: (t[0], t[2]))

    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ys = range(len(items))
    colors = [BLUE for _ in items]
    ax.barh(list(ys), [x for _, _, x in items], color=colors, height=0.62, zorder=3)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([name for _, name, _ in items], fontsize=9.5, family="monospace")
    for y, (_, _, x) in zip(ys, items):
        ax.text(x + 0.15, y, f"{x:.1f}x", va="center", fontsize=9.5, color=MUTED)
    # language group separators
    n_c = sum(1 for l, _, _ in items if l == "c")
    ax.axhline(n_c - 0.5, color=GRID, lw=1)
    ax.set_xlabel("slowdown vs native (warm run, median of ~100)", fontsize=10)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.margins(x=0.08)
    # language group labels + measurement caveat, on-chart
    ax.text(1.01, (n_c - 1) / 2, "C", transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=10, color=MUTED, clip_on=False)
    ax.text(1.01, n_c + (len(items) - n_c - 1) / 2, "Python",
            transform=ax.get_yaxis_transform(), va="center", ha="left",
            fontsize=10, color=MUTED, clip_on=False)
    ax.set_title("wasm's own clock is a stub (reports 0.000s): wall-clock times, Node 22",
                 fontsize=9, color=MUTED, loc="left", pad=8)
    save(fig, "chart-slowdown")


# ---------------------------------------------------------------- chart 2
# Cumulative time for N successive analyses: wasm vs jsoo, node & browser.
# Job: the two series are the subject -> categorical, 2 hues, direct labels.
def chart_cumulative():
    def series(target):
        rs = rows_for(target, "python")
        inst = med([r["loadMs"] for r in rs])
        cold = med([r.get("runColdMs") or r["runMs"] for r in rs])
        warm = med([r.get("runWarmMs") or r["runMs"] for r in rs])
        return inst, cold, warm

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.1), sharey=True)
    for ax, (envname, wt, jt) in zip(
        axes,
        [("Node", "wasm-node", "jsoo-node"), ("Browser", "wasm-browser", "jsoo-browser")],
    ):
        n = list(range(0, 11))
        for target, color, label in ((wt, BLUE, "wasm"), (jt, ORANGE, "JavaScript")):
            inst, cold, warm = series(target)
            # jsoo cannot re-enter a warm state: every analysis is cold
            if target.startswith("jsoo"):
                cum = [inst / 1000 + i * cold / 1000 for i in n]
            else:
                cum = [inst / 1000 + (cold / 1000 + max(0, i - 1) * warm / 1000 if i else 0) for i in n]
            ax.plot(n, cum, color=color, lw=2, zorder=3)
            ax.annotate(label, (n[-1], cum[-1]), xytext=(4, 0),
                        textcoords="offset points", color=color, fontsize=10.5,
                        va="center", fontweight="bold")
        ax.set_title(envname, fontsize=11, color=TEXT)
        ax.set_xlabel("number of analyses", fontsize=10)
        ax.set_xticks([0, 2, 4, 6, 8, 10])
        ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.margins(x=0.14)
    axes[0].set_ylabel("cumulative time (s)", fontsize=10)
    axes[0].annotate("a fresh OCaml state needs a fresh JS realm:\n"
                     "every JavaScript analysis is a first run,\n"
                     "so the slope never flattens",
                     xy=(6, 0.359 + 6 * 0.371), xytext=(0.4, 5.2),
                     fontsize=8.5, color=MUTED,
                     arrowprops=dict(arrowstyle="-", color=GRAY, lw=0.8))
    axes[1].annotate("wasm re-instantiates a module\nV8 has already optimized",
                     xy=(6, 0.641 + 0.356 + 5 * 0.304), xytext=(2.6, 6.4),
                     fontsize=8.5, color=MUTED,
                     arrowprops=dict(arrowstyle="-", color=GRAY, lw=0.8))
    fig.suptitle("startup + N successive analyses (Python corpus medians)",
                 fontsize=9.5, color=MUTED, y=1.04)
    save(fig, "chart-cumulative")


# ---------------------------------------------------------------- chart 3
# Directed rounding vs round-to-nearest: why fesetround matters for soundness.
# Status colors: sound = green, unsound = red (reserved status palette).
GOOD = "#008300"
BAD = "#e34948"


def chart_rounding():
    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.15, 1.55)
    ax.axis("off")
    # the number line
    ax.annotate("", xy=(9.8, 0), xytext=(0.2, 0),
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.4))
    true_x = 5.4
    ax.plot([true_x], [0], marker="|", ms=26, color=TEXT, mew=2.2)
    ax.text(true_x, -0.62, "true upper bound", ha="center", fontsize=10, color=TEXT)
    # directed rounding: lands at-or-right of the true bound -> sound
    up_x = 6.6
    ax.plot([up_x], [0], marker="o", ms=9, color=GOOD, zorder=3)
    ax.annotate("", xy=(up_x - 0.12, 0.42), xytext=(true_x + 0.12, 0.42),
                arrowprops=dict(arrowstyle="->", color=GOOD, lw=1.6))
    ax.text(6.0, 0.95, "fesetround(FE_UPWARD): rounds outward, sound  ✓",
            ha="left", fontsize=10.5, color=GOOD)
    # round-to-nearest: may land left of the true bound -> unsound
    near_x = 4.3
    ax.plot([near_x], [0], marker="o", ms=9, color=BAD, zorder=3)
    ax.annotate("", xy=(near_x + 0.12, -0.42), xytext=(true_x - 0.12, -0.42),
                arrowprops=dict(arrowstyle="->", color=BAD, lw=1.6))
    ax.text(0.2, -1.05, "round-to-nearest (all wasm has): may round inward, "
            "values escape the interval  ✗", ha="left", fontsize=10.5, color=BAD)
    save(fig, "chart-rounding")


if __name__ == "__main__":
    chart_slowdown()
    chart_cumulative()
    chart_rounding()
