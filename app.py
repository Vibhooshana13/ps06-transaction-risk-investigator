"""
app.py — Transaction Risk Investigation Assistant (PS06)

Serves the frontend and a small API. All fraud-signal detection happens in
rules.py using deterministic logic. Gemini is used ONLY to turn the rule
engine's structured findings into a plain-English investigation note for a
human analyst — it never decides on its own whether something is suspicious,
and it never states that fraud has occurred.
"""

import os
import json
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

import rules

load_dotenv()

app = Flask(__name__)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "transactions.csv")
TRANSACTIONS = rules.load_transactions(DATA_PATH)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
_gemini_model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print(f"[startup] Gemini unavailable, will fall back to raw findings: {e}")


def build_narrative_prompt(customer_id, result):
    """
    Builds a prompt that hands Gemini ONLY the structured rule findings —
    never the raw CSV — so it cannot cite a transaction that wasn't actually
    flagged by a rule.
    """
    findings_for_prompt = [f for f in result["findings"] if f["triggered"]]

    instructions = """You are writing an investigation note for a bank fraud-desk analyst.
Rules, already applied by a separate deterministic system, are given to you as JSON below.
Do not invent, add, or infer any transaction, rule, or amount that is not present in the JSON.

Write the note with this structure:
1. One-line verdict: either "No activity requires investigator attention" or
   "Activity flagged for review" — never say "fraud" or "fraudulent" anywhere in your note.
2. If flagged: for each triggered rule, explain in plain English which transactions were
   involved, how they connect to each other, and how they differ from the customer's normal
   pattern (using the baseline facts given). End with a short "what to check first" pointer
   for the investigator.
3. If nothing is flagged: say so plainly in 1-2 sentences. Do not manufacture concern.

Keep the tone factual and neutral. You are handing judgement to a human, not making an
accusation."""

    payload = {
        "customer_id": customer_id,
        "needs_attention": result["needs_attention"],
        "baseline": result["baseline"],
        "triggered_findings": findings_for_prompt,
    }

    return f"{instructions}\n\nSTRUCTURED FINDINGS (JSON):\n{json.dumps(payload, indent=2, default=str)}"


def generate_narrative(customer_id, result):
    if _gemini_model is None:
        return None, "Gemini not configured (GEMINI_API_KEY missing or client failed to init)."
    try:
        prompt = build_narrative_prompt(customer_id, result)
        response = _gemini_model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        return None, f"Narrative generation failed: {e}"


def fallback_narrative(result):
    """Used when Gemini is unavailable or errors — never leave the analyst with nothing."""
    if not result["needs_attention"]:
        return "No activity requires investigator attention. (Narrative generation was unavailable — this is a rule-engine-only summary.)"
    lines = ["Activity flagged for review. (Narrative generation was unavailable — showing raw rule findings.)"]
    for f in result["findings"]:
        if f["triggered"]:
            lines.append(f"- {f['label']}: {len(f['transactions'])} transaction(s) flagged.")
    return "\n".join(lines)


@app.route("/")
def index():
    return render_template("index.html", customers=rules.list_customers(TRANSACTIONS))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/api/customers")
def api_customers():
    return jsonify(rules.list_customers(TRANSACTIONS))


@app.route("/api/investigate", methods=["POST"])
def api_investigate():
    body = request.get_json(silent=True) or {}
    customer_id = body.get("customer_id")

    if not customer_id or customer_id not in TRANSACTIONS:
        return jsonify({"error": "Unknown or missing customer_id"}), 400

    result = rules.investigate(TRANSACTIONS[customer_id])
    narrative, error = generate_narrative(customer_id, result)
    if narrative is None:
        narrative = fallback_narrative(result)

    return jsonify({
        "customer_id": customer_id,
        "needs_attention": result["needs_attention"],
        "narrative": narrative,
        "narrative_error": error,
        "findings": result["findings"],
        "baseline": result["baseline"],
        "transaction_count": result["transaction_count"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
