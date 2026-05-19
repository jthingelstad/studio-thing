"""Fetch live subscriber/financial stats from Buttondown + Stripe.

The body-fetch path (``fetch_all_emails`` / ``fetch_email_by_id`` /
``fetch()``) was retired alongside the data/buttondown/ snapshot tree.
Issues are now created and committed by workshop_bot's ship sequence;
the website builds from data/issues/{N}/ directly. What's still useful
on this side of the API is the stats refresh that powers stats.json
(landing page subscriber counts, Stripe-backed "amount raised").
"""

import os

import requests
import stripe
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)

load_dotenv()

API_BASE = "https://api.buttondown.com/v1"


def get_headers():
    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        raise RuntimeError("BUTTONDOWN_API_KEY environment variable is required")
    return {"Authorization": f"Token {api_key}"}


def fetch_subscriber_count(headers):
    """Fetch total subscriber count from Buttondown."""
    resp = requests.get(
        f"{API_BASE}/subscribers", headers=headers, params={"page_size": 1}
    )
    resp.raise_for_status()
    return resp.json().get("count", 0)


def fetch_premium_subscriber_count(headers):
    """Fetch premium (supporting) subscriber count from Buttondown."""
    resp = requests.get(
        f"{API_BASE}/subscribers",
        headers=headers,
        params={"type": "premium", "page_size": 1},
    )
    resp.raise_for_status()
    return resp.json().get("count", 0)


def fetch_stripe_balance():
    """Fetch the current Stripe balance (amount raised)."""
    api_key = os.environ.get("STRIPE_API_KEY")
    if not api_key:
        print("  Warning: STRIPE_API_KEY not set, skipping balance fetch")
        return 0

    stripe.api_key = api_key
    balance = stripe.Balance.retrieve()

    total_cents = 0
    for entry in balance["available"]:
        if entry["currency"] == "usd":
            total_cents += entry["amount"]
    for entry in balance["pending"]:
        if entry["currency"] == "usd":
            total_cents += entry["amount"]

    return total_cents / 100
