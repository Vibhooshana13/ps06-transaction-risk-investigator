"""
rules.py — deterministic risk rules for the Transaction Risk Investigation Assistant.

No LLM calls happen anywhere in this file. Every function here takes a customer's
transaction history and returns plain data structures (dicts/lists) describing what
was found and why. The narrative layer (in app.py) is only allowed to describe these
findings — it never invents a rule result on its own.
"""

import csv
import statistics
from datetime import datetime
from collections import defaultdict

DATE_FMT = "%Y-%m-%d %H:%M"

# ---- thresholds (tune these; keep them named so the reasoning is legible) ----
LARGE_TRANSFER_STD_MULTIPLIER = 2.5     # amount beyond this many std-devs above mean is "large"
ODD_HOUR_START = 0
ODD_HOUR_END = 5                        # 00:00–05:59 counts as odd hours
NEW_PAYEE_BASELINE_FRACTION = 0.7       # first 70% of history (by time) defines "known" payees
NEW_PAYEE_BURST_WINDOW_DAYS = 7
NEW_PAYEE_BURST_MIN_COUNT = 2           # >=2 new payees within the window counts as a burst
PATTERN_CHANNEL_DEVIATION = True        # flag a channel customer has never used before


def load_transactions(csv_path):
    """Returns dict: customer_id -> list of transaction dicts, sorted by date."""
    by_customer = defaultdict(list)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            row["amount"] = float(row["amount"])
            row["_dt"] = datetime.strptime(row["date"], DATE_FMT)
            by_customer[row["customer_id"]].append(row)
    for cid in by_customer:
        by_customer[cid].sort(key=lambda r: r["_dt"])
    return dict(by_customer)


def list_customers(by_customer):
    return sorted(by_customer.keys())


def _build_baseline(transactions):
    """Establish 'normal' for this customer from their own history."""
    debits = [t for t in transactions if t["type"] == "debit"]
    amounts = [t["amount"] for t in debits] or [0]
    mean_amt = statistics.mean(amounts)
    std_amt = statistics.pstdev(amounts) if len(amounts) > 1 else 0

    cutoff_idx = max(1, int(len(transactions) * NEW_PAYEE_BASELINE_FRACTION))
    baseline_txns = transactions[:cutoff_idx]
    known_payees = {t["payee"] for t in baseline_txns}
    known_channels = {t["channel"] for t in baseline_txns}

    return {
        "mean_amount": round(mean_amt, 2),
        "std_amount": round(std_amt, 2),
        "large_amount_threshold": round(mean_amt + LARGE_TRANSFER_STD_MULTIPLIER * std_amt, 2),
        "known_payees": known_payees,
        "known_channels": known_channels,
    }


def rule_large_transfer(transactions, baseline):
    threshold = baseline["large_amount_threshold"]
    flagged = [t for t in transactions if t["type"] == "debit" and t["amount"] > threshold and threshold > 0]
    return {
        "rule": "large_transfer",
        "label": "Unusually large transfer",
        "triggered": len(flagged) > 0,
        "transactions": flagged,
        "facts": {
            "customer_mean_amount": baseline["mean_amount"],
            "threshold_used": threshold,
        },
    }


def rule_odd_hours(transactions, baseline):
    flagged = [t for t in transactions if ODD_HOUR_START <= t["_dt"].hour <= ODD_HOUR_END]
    return {
        "rule": "odd_hours",
        "label": "Odd-hours activity",
        "triggered": len(flagged) > 0,
        "transactions": flagged,
        "facts": {"window": f"{ODD_HOUR_START:02d}:00-{ODD_HOUR_END:02d}:59"},
    }


def rule_new_payee_burst(transactions, baseline):
    known = baseline["known_payees"]
    new_payee_txns = [t for t in transactions if t["payee"] not in known]
    new_payee_txns.sort(key=lambda t: t["_dt"])

    flagged = []
    seen_payees_in_window = {}
    for t in new_payee_txns:
        window_start = t["_dt"]
        window = [
            x for x in new_payee_txns
            if 0 <= (x["_dt"] - window_start).days < NEW_PAYEE_BURST_WINDOW_DAYS
        ]
        distinct_new_payees = {x["payee"] for x in window}
        if len(distinct_new_payees) >= NEW_PAYEE_BURST_MIN_COUNT:
            flagged.extend(window)

    # de-duplicate while preserving order
    seen_ids = set()
    unique_flagged = []
    for t in flagged:
        key = (t["_dt"], t["payee"], t["amount"])
        if key not in seen_ids:
            seen_ids.add(key)
            unique_flagged.append(t)

    return {
        "rule": "new_payee_burst",
        "label": "Burst of payments to new payees",
        "triggered": len(unique_flagged) > 0,
        "transactions": unique_flagged,
        "facts": {
            "window_days": NEW_PAYEE_BURST_WINDOW_DAYS,
            "min_distinct_new_payees": NEW_PAYEE_BURST_MIN_COUNT,
        },
    }


def rule_pattern_deviation(transactions, baseline):
    """Flags transactions using a channel this customer has never used before."""
    known_channels = baseline["known_channels"]
    flagged = [t for t in transactions if t["channel"] not in known_channels]
    return {
        "rule": "pattern_deviation",
        "label": "Deviation from established pattern (new channel used)",
        "triggered": len(flagged) > 0,
        "transactions": flagged,
        "facts": {"known_channels": sorted(known_channels)},
    }


ALL_RULES = [rule_large_transfer, rule_odd_hours, rule_new_payee_burst, rule_pattern_deviation]


def investigate(transactions):
    """
    Runs every rule against one customer's transaction history.
    Returns a structured result — no prose, no LLM involvement.
    """
    if not transactions:
        return {"needs_attention": False, "findings": [], "baseline": {}}

    baseline = _build_baseline(transactions)
    findings = [rule(transactions, baseline) for rule in ALL_RULES]
    needs_attention = any(f["triggered"] for f in findings)

    # serialize transactions for JSON/LLM consumption (drop internal _dt)
    for f in findings:
        f["transactions"] = [
            {k: v for k, v in t.items() if k != "_dt"} for t in f["transactions"]
        ]

    baseline_public = {k: v for k, v in baseline.items() if k not in ("known_payees", "known_channels")}
    baseline_public["known_payees"] = sorted(baseline["known_payees"])
    baseline_public["known_channels"] = sorted(baseline["known_channels"])

    return {
        "needs_attention": needs_attention,
        "findings": findings,
        "baseline": baseline_public,
        "transaction_count": len(transactions),
    }
