(or `export GEMINI_API_KEY=your_key_here` on Mac/Linux, `set GEMINI_API_KEY=your_key_here` on Windows cmd)

Then open http://localhost:8000, pick a customer from the dropdown, and click
**Investigate**.

## Data

`data/transactions.csv` is synthetic data generated for this project, covering
two customers over ~3-4 months:
- **CUST001** — routine activity only (salary, rent, groceries, subscriptions).
  Expected result: no findings triggered.
- **CUST002** — routine activity for the first ~2.5 months, then a planted
  episode of large wire transfers to newly-seen payees at odd hours over a
  few days. Expected result: multiple rules triggered on the same connected
  episode.

## Demo video

https://drive.google.com/file/d/1lUOrM8JOBZx4iSWZI9ruHXsxe41a1Cji/view?usp=drive_link
