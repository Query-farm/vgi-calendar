"""Calendar example plots; request policy and calendar arithmetic stay in SQL."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from vgi_notebooks import finish

COLORS = {"New York": "#267358", "England": "#456fba", "Bavaria": "#ac6b36"}
SOURCE = "Synthetic dispatch requests · VGI Calendar v0.5.0 · installed holidays library rules"


def validate_lead_time(value):
    """Bound the modeled request window before starting the worker."""
    if type(value) is not int or not 1 <= value <= 7:
        raise ValueError("LEAD_BUSINESS_DAYS must be an integer from 1 to 7.")


def plot_calendar(calendar_frame):
    """Show business days, weekends and public holidays without equating them."""
    grid = calendar_frame.pivot(index="region", columns="date", values="day_kind").reindex(list(COLORS))
    fig, ax = plt.subplots(figsize=(13, 5.2))
    sns.heatmap(
        grid,
        ax=ax,
        cmap=ListedColormap(["#e4f0e8", "#e4e7eb", "#c68d54"]),
        vmin=0,
        vmax=2,
        linewidths=1.5,
        linecolor="white",
        cbar=False,
        annot=False,
    )
    for y in range(len(grid)):
        for x in range(len(grid.columns)):
            ax.text(
                x + 0.5,
                y + 0.5,
                ["B", "W", "H"][int(grid.iloc[y, x])],
                ha="center",
                va="center",
                fontsize=9,
                color="#253d31",
            )
    ax.set_xticklabels([pd.Timestamp(d).strftime("%d\n%b") for d in grid.columns], rotation=0, fontsize=8)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    ax.set(xlabel="", ylabel="Regional calendar")
    ax.legend(
        handles=[
            Patch(facecolor=c, label=label)
            for c, label in [("#e4f0e8", "B · business day"), ("#e4e7eb", "W · weekend"), ("#c68d54", "H · holiday")]
        ],
        loc="upper left",
        bbox_to_anchor=(0, -0.17),
        ncol=3,
        frameon=False,
    )
    finish(
        fig,
        "A weekday is not always a business day",
        "21 Dec 2026–15 Jan 2027 · holidays take precedence over weekends in this display",
        SOURCE,
        name="01_regional_calendars",
    )


def plot_elapsed(delivery_frame, lead_business_days):
    """Compare modeled elapsed days on identical axes."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.2), sharex=True, sharey=True)
    for ax, (region, color) in zip(axes, COLORS.items(), strict=True):
        rows = delivery_frame[delivery_frame.region == region]
        ax.plot(pd.to_datetime(rows.requested_date), rows.elapsed_calendar_days, marker="o", color=color, linewidth=2)
        ax.axhline(lead_business_days, linestyle="--", color="#748178", label="Naive calendar-day addition")
        ax.set_title(region, loc="left", weight="bold")
        ax.set_xlabel("Requested dispatch date")
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.set_ylim(0, max(delivery_frame.elapsed_calendar_days) + 1)
    axes[0].set_ylabel("Calendar days from request to delivery")
    axes[0].legend(loc="upper left", fontsize=8, frameon=False)
    finish(
        fig,
        "Equal service promises can span unequal calendar time",
        f"{lead_business_days} business days after dispatch · common axes across all three regions",
        SOURCE,
        name="02_elapsed_days",
    )


def plot_timeline(delivery_frame, lead_business_days):
    """Keep requested, dispatched, naive and business-day delivery dates distinct."""
    last = (
        delivery_frame[delivery_frame.requested_date == delivery_frame.requested_date.max()]
        .set_index("region")
        .loc[list(COLORS)]
    )
    fig, ax = plt.subplots(figsize=(13, 6.0))
    for y, (region, row) in enumerate(last.iterrows()):
        start, end = pd.Timestamp(row.requested_date), pd.Timestamp(row.delivery_date)
        ax.plot([start, end], [y, y], color=COLORS[region], linewidth=6, solid_capstyle="round")
        ax.scatter([start], [y], marker="|", s=240, color="#253d31", zorder=4)
        ax.scatter(
            [pd.Timestamp(row.dispatch_date)], [y], marker="o", s=60, color="white", edgecolor="#253d31", zorder=5
        )
        ax.scatter([end], [y], marker="D", s=65, color=COLORS[region], zorder=5)
        ax.scatter([pd.Timestamp(row.naive_date)], [y], marker="x", s=65, color="#303b35", zorder=6)
        ax.annotate(end.strftime("%d %b"), (end, y), xytext=(8, 8), textcoords="offset points", fontsize=10)
    ax.set_yticks(range(3), list(COLORS))
    ax.invert_yaxis()
    ax.set_ylim(2.6, -0.6)
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_xlim(
        pd.Timestamp(last.requested_date.min()) - pd.Timedelta(days=1),
        pd.Timestamp(last.delivery_date.max()) + pd.Timedelta(days=2),
    )
    ax.set_xlabel("Local civil date · December 2026 → January 2027")
    ax.plot([], [], marker="|", color="#253d31", linestyle="", label="Requested")
    ax.plot([], [], marker="o", markerfacecolor="white", color="#253d31", linestyle="", label="Dispatch")
    ax.plot([], [], marker="D", color="#267358", linestyle="", label="Business-day delivery")
    ax.plot([], [], marker="x", color="#303b35", linestyle="", label="Naive delivery")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.20), ncol=4, frameon=False)
    finish(
        fig,
        "A year boundary makes the calendar assumptions visible",
        f"Requested 31 Dec 2026 · {lead_business_days}-business-day service · lines show modeled date spans",
        SOURCE,
        name="03_year_boundary",
    )
    return last
