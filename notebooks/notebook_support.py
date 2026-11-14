"""Small presentation helpers for the calendar notebook."""

from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
from IPython.display import Markdown, display

COLORS = {"New York": "#267358", "England": "#456fba", "Bavaria": "#ac6b36"}


def theme() -> None:
    """Apply the shared notebook visual style."""
    sns.set_theme(style="whitegrid", context="notebook", font="DejaVu Sans")
    plt.rcParams.update(
        {
            "figure.dpi": 130,
            "text.parse_math": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": "#e2e8e4",
        }
    )


def prose(text: str) -> None:
    """Show a result-derived interpretation."""
    display(Markdown(text))


def finish(fig: plt.Figure, title: str, subtitle: str, filename: str) -> None:
    """Label, embed and save a chart for visual review."""
    fig.suptitle(title, x=0.08, y=0.98, ha="left", fontsize=18, weight="bold", color="#253d31")
    fig.text(0.08, 0.90, subtitle, ha="left", fontsize=11, color="#52675a")
    fig.text(
        0.08,
        0.025,
        "Source: synthetic dispatch requests · VGI calendar v0.5.0 / holidays 0.108",
        ha="left",
        fontsize=9,
        color="#52675a",
    )
    fig.tight_layout(rect=(0.02, 0.08, 1, 0.83))
    directory = Path("validation/charts")
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / filename, dpi=150)
    plt.show()
