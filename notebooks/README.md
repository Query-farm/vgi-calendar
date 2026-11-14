# Calendar notebooks

[01 · The same lead time, different delivery dates](01_same_lead_time_different_dates.ipynb)
uses weekday recurrence, regional holidays and business-day arithmetic to explain
synthetic dispatch and delivery schedules in New York, England and Bavaria.
The executed example includes three embedded charts and visible Haybarn/VGI SQL.

## Setup and execution

You need `uv` and Git on PATH. This directory is independently runnable: download
or copy **notebooks/**, including its assets, helper, environment files and runner.
From that directory:

```sh
uv sync --locked
uv run --locked python execute.py
```

Select `.venv/bin/python` in a Jupyter-compatible editor and **Restart Kernel → Run All**.
No global kernel registration or worker checkout is required. Python 3.13–3.14
is supported by the notebook environment, which pins published Haybarn 2.0.0rc11.
The visible SQL launches release **v0.5.0** through this literal command:

```sql
ATTACH 'cal' (TYPE vgi, LOCATION 'uvx --python 3.13 --with holidays==0.108 --with vgi-python==0.51.0 --from git+https://github.com/Query-farm/vgi-calendar@v0.5.0 vgi-calendar-worker');
```

The GitHub release provides a wheel/source archive, not a native per-platform
`github-auto` asset; `uvx` installs the pinned Git release and runs its entry point.
It pins `holidays==0.108` and `vgi-python==0.51.0` to preserve the demonstrated
calendar rules and SDK. The first run downloads Python/dependencies and the SQL
extension; calculations are then local. To upgrade, change the release and
compatible dependency pins in the visible ATTACH, execute the default and
experiment, and review any calendar-rule changes.

Parameters and connection SQL stay visible; setup, plots and cleanup are folded.
Editors may retain their own folding state. The example has no live/replay switch.

Change `LEAD_BUSINESS_DAYS` from 2 to 5 and restart/run all, or preserve the default:

```sh
uv run --locked python execute.py --parameters '{"LEAD_BUSINESS_DAYS": 5}' \
  --output-dir validation/lead-5
```

The runner uses a fresh kernel with this notebook directory as its working
directory. It rejects overrides that would overwrite the default and atomically
saves only successful runs. Experiment copies include their guide, environment,
helper, runner and branding. Logs, charts and experiments under `validation/` are
Git-ignored; the primary notebook retains its embedded outputs.

## Assumptions and provenance

Requests are synthetic. Holiday rules come from the pinned `holidays==0.108`
library through `cal.main`; they are calendar-model outputs, not carrier service
commitments or organization-specific operating schedules. The example uses
US/NY, GB/ENG and DE/BY. English holiday names and observed shifts follow the
worker's existing implementation. No live holiday service is queried.

Nine weekday requests span 21–31 December 2026 inclusive. Closed requested dates
roll to the next business day; the service count starts strictly after dispatch
and includes delivery. Saturday/Sunday are always weekends. The same region
governs dispatch and delivery, with no time-of-day cutoff or cross-border transit.
Naive recurrence timestamps become civil dates; no elapsed-hour or UTC simultaneity
claim is made. The calendar chart covers 21 December–15 January inclusive.

Country/subdivision arguments on scalar functions are constants, so the SQL uses
explicit branches. The notebook also demonstrates the difference between
half-open `business_days_between` and inclusive `business_days` endpoint rules.
Checks validate service counts, available endpoints, uniqueness and chart coverage
across supported lead-time parameters (integers 1–7).

Domain calculations stay in SQL through the real worker. Python provides formatting,
parameter validation and chart rendering using Seaborn/Matplotlib. Ordinary in-memory
tables are used because JupySQL opens separate cursors. Cleanup closes the connection.

Official Strata Sun + Query.Farm and VGI assets are copied unchanged from the approved
perps examples, originally from the Query.Farm media kit. The linked Strata Sun appears
at the top and final bottom of the notebook.
