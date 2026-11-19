"""Figure: monthly agent-commit share per community, policy dates marked -> figures/monthly_share.{pdf,png}.

Reads data/results/monthly.csv (from 10_results.py) and data/policy_dates.csv. One panel per community,
same x and y scales so the panels compare directly; dashed line = policy proposal, solid = effective.
Biopython is left out (one agent commit in the whole period); the caption says so.
Sized for one IEEE column (3.5 in wide).
"""
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "figures"
PANELS = [("bioconductor", "Bioconductor", "Bioconductor", "#2a78d6"),
          ("nf-core", "nf-core", "nf-core", "#eb6834")]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def main():
    OUT.mkdir(exist_ok=True)
    m = pd.read_csv(ROOT / "data" / "results" / "monthly.csv")
    m["date"] = pd.to_datetime(m.month + "-15")
    policy = pd.read_csv(ROOT / "data" / "policy_dates.csv").set_index("community")
    # Comparison group: GitHub repos with a bioinformatics topic, no shared policy.
    # Written by 16_mine_topic.py; drawn in grey in both panels when present.
    tpath = ROOT / "data" / "results" / "topic_monthly.csv"
    topic = None
    if tpath.exists():
        topic = pd.read_csv(tpath)
        topic["date"] = pd.to_datetime(topic.month + "-15")

    # Times-like font to match IEEEtran; fonttype 42 embeds TrueType, not Type 3 (IEEE PDF eXpress rejects Type 3)
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Nimbus Roman", "Liberation Serif"],
                         "pdf.fonttype": 42, "font.size": 7, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, axes = plt.subplots(len(PANELS), 1, figsize=(3.5, 2.9), sharex=True, sharey=True)
    for ax, (comm, policy_name, title, color) in zip(axes, PANELS):
        g = m[m.community == comm]
        ax.plot(g.date, g.share_pct, color=color, lw=1.4, marker="o", ms=2.2, zorder=3, label=title)
        if topic is not None:
            ax.plot(topic.date, topic.share_pct, color="#9a9893", lw=1.0, zorder=2.5,
                    label="Comparison group (GitHub)")
            ax.legend(loc="upper left", bbox_to_anchor=(0, 0.80), fontsize=5.5, frameon=False,
                      handlelength=1.6, borderaxespad=0.2)
        ymax = 50
        for kind, style, label in [("proposal_date", (0, (3, 2)), "proposed"), ("effective_date", "-", "effective")]:
            d = pd.Timestamp(policy.loc[policy_name, kind])
            ax.axvline(d, color=MUTED, lw=0.8, ls=style, zorder=2)
            ax.text(d, ymax * 0.97, f" {label}\n {d:%d %b %Y}", color=MUTED, fontsize=5.5, va="top",
                    ha="right" if kind == "proposal_date" and comm == "bioconductor" else "left")
        ax.set_title(title, loc="left", fontsize=7.5, color=INK, pad=2)
        ax.set_ylim(0, ymax)
        ax.set_yticks([0, 10, 20, 30, 40])
        ax.set_ylabel("agent share (%)")
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        for side in ["top", "right"]:
            ax.spines[side].set_visible(False)
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    axes[-1].set_xlim(pd.Timestamp("2023-12-15"), m.date.max() + pd.Timedelta(days=20))
    fig.tight_layout(pad=0.3, h_pad=0.6)
    for ext in ["pdf", "png"]:
        fig.savefig(OUT / f"monthly_share.{ext}", dpi=300)
    print(f"wrote figures/monthly_share.pdf and .png ({m.month.min()} to {m.month.max()})")


if __name__ == "__main__":
    main()
