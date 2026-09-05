TRACK_ID=PS06

# Transaction Risk Investigation Assistant

An investigation assistant for a bank's fraud desk. Given a customer's transaction
history, it runs a set of deterministic risk rules against that customer's own
established pattern, then uses Gemini to turn the structured findings into a
plain-English investigation note for a human analyst. The system never states that
fraud has occurred — it flags, explains, and hands judgement to the investigator.

## How it works

1. **`rules.py`** — pure Python, no LLM calls. Builds a per-customer baseline from
   their own history (typical amount range, known payees, known channels), then
   checks for:
   - Unusually large transfers (relative to this customer's own mean + std-dev)
   - Bursts of payments to newly-seen payees within a short window
   - Odd-hours activity (00:00–05:59)
   - Deviation from the customer's established pattern (e.g. a channel they've
     never used before)
2. **Gemini** — receives only the structured rule findings (JSON), never the raw
   CSV, and writes the investigation note. It is explicitly instructed to lead
   with a verdict, never use the word "fraud", and never cite anything outside
   the findings it was given.
3. If the Gemini call fails or no API key is set, the app falls back to a
   plain rule-findings summary rather than failing the request.

## Running it

```
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here
python app.py
```

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

[link to be added]
