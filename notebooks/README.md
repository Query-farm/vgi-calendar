# Calendar Math examples

[Worker repository](https://github.com/Query-farm/vgi-calendar) · [Shared notebook tools and standard](https://github.com/Query-farm/vgi-example-notebooks)

| Notebook | Investigation | Run |
|---|---|---|
| [The same lead time, different delivery dates](01_same_lead_time_different_dates.ipynb) | Compare New York, England and Bavaria holiday calendars; roll closed dispatches forward; reconcile business-day arithmetic with explicit service-date lists. | [Open in Colab](https://colab.research.google.com/github/Query-farm/vgi-calendar/blob/main/notebooks/01_same_lead_time_different_dates.ipynb) |

The notebook contains executed SQL, result-driven explanations and three SVG
charts. It includes the linked worker title and subtitle, Query Farm and VGI
branding, plus its own Colab button. GitHub displays code expanded; shared setup
and a small plotting companion keep those cells short. VGI connection SQL remains
visible.

## Run it

Open in Colab and run all cells, or use `uv` from this directory:

```sh
uv sync --locked
uv run --locked vgi-notebooks --timeout 300
```

Select `.venv/bin/python` for interactive work. The notebook installs the shared
base tools, preserving compatible preinstalled plotting and kernel packages; the
local environment additionally includes the runner. Its companion is downloaded
from an immutable revision and SHA-256 verified, so a standalone notebook works
without a worker checkout or copied standard/runner scripts.

The visible ATTACH uses the released worker:

```text
uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-calendar@v0.5.0 vgi-calendar-worker
```

First setup needs Git and network access. The worker runs in its own environment;
no SDK override, API key or live-data service is required. A release tag fixes the
worker code, while dependency ranges may resolve newer holiday rules on future
installs. The notebook records the resulting dates and checks relationships rather
than requiring particular library-version-specific holiday labels.

## What the example means

Nine synthetic weekday requests fall between 21 and 31 December 2026. We apply
the same request population to New York (`US/NY`), England (`GB/ENG`) and Bavaria
(`DE/BY`). Supported regional codes are discovered first. The calendar extends
through 15 January 2027 to cover the largest allowed lead time.

Our policy moves a request on a closed date to the next business day. It then
counts the selected lead time strictly after dispatch, including the delivery
date. These are civil dates, not elapsed 24-hour periods. Weekday recurrence does
not remove holidays. Calling `add_business_days(date, 0)` would leave a closed
date unchanged, so the dispatch adjustment is explicit.

The first chart keeps business days, weekends and holidays distinct. The second
uses common axes to compare elapsed calendar days. The final timeline follows
31 December across the year boundary. Explicit service-date lists and SQL checks
reconcile `business_days`' inclusive endpoints with `business_days_between`'s
half-open interval. Holiday names and weekend flags remain available even when
the display gives holidays priority.

These modeled dates are not carrier commitments, workplace schedules or observed
shipping performance. Stock-exchange sessions belong to the separate
[vgi-trading-calendar](https://github.com/Query-farm/vgi-trading-calendar) worker.

## Change one assumption

`LEAD_BUSINESS_DAYS` defaults to `2` and accepts integers `1–7`. The closing
experiment changes it to `5`. Save that run separately:

```sh
uv run --locked vgi-notebooks --timeout 300 \
  --parameters '{"LEAD_BUSINESS_DAYS":5}' --output-dir artifacts/five-business-days
```

Requested dates, holiday flags and adjusted dispatches should stay fixed. Every
service-date list should grow from two dates to five, and deliveries should move
later. The increase in elapsed calendar days can differ by region. Compare the
summary, elapsed-day panels, final-request timeline and enumerated service dates;
restore `2` to reproduce the default.

The shared runner rejects unknown overrides, requires a separate output directory
for experiments and saves notebooks only after success. Checked-in SVG assets
make GitHub charts sharp; review PNGs and experiment copies are ignored.
[Coverage evidence](coverage.json) distinguishes actual released execution from
current-source review. The current source tree and dependency files are identical
to v0.5.0; no separate current worker build was needed for this notebook update.
