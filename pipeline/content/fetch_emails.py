"""Fetch published emails and stats from the Buttondown API."""

import json
import os
import sys
from pathlib import Path

import requests
import stripe
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)

load_dotenv()

API_BASE = "https://api.buttondown.com/v1"


def get_headers():
    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        raise RuntimeError("BUTTONDOWN_API_KEY environment variable is required")
    return {"Authorization": f"Token {api_key}"}


def fetch_all_emails(headers):
    """Fetch all sent, public emails from Buttondown, handling pagination."""
    emails = []
    url = f"{API_BASE}/emails"
    params = {"status": "sent", "email_type": "public", "page_size": 100}

    while url:
        print(f"  Fetching {url} ...")
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        emails.extend(data.get("results", []))
        url = data.get("next")
        params = {}  # next URL already contains params

    return emails


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

    return total_cents / 100  # Convert cents to dollars


def fetch(no_cache=False):
    """Main fetch function. Returns list of email objects.

    Also fetches subscriber stats and writes apps/site/_data/stats.json.
    The no_cache argument is accepted for compatibility with older callers.
    """
    print("Fetching emails from Buttondown API...")
    headers = get_headers()
    emails = fetch_all_emails(headers)
    print(f"Fetched {len(emails)} emails")

    # Fetch live stats — preserve existing stats.json if API calls fail
    stats_output = Path(__file__).resolve().parents[2] / "apps" / "site" / "_data" / "stats.json"
    existing_stats = {}
    if stats_output.exists():
        with open(stats_output) as f:
            existing_stats = json.load(f)

    print("Fetching subscriber stats...")
    try:
        headers = get_headers()
        subscriber_count = fetch_subscriber_count(headers)
        premium_count = fetch_premium_subscriber_count(headers)
    except Exception as e:
        print(f"  Warning: Could not fetch subscriber stats: {e}")
        subscriber_count = existing_stats.get("subscriber_count", 0)
        premium_count = existing_stats.get("premium_subscriber_count", 0)

    print("Fetching Stripe balance...")
    try:
        amount_raised = fetch_stripe_balance()
    except Exception as e:
        print(f"  Warning: Could not fetch Stripe balance: {e}")
        amount_raised = existing_stats.get("amount_raised", 0)

    stats = {
        "subscriber_count": subscriber_count,
        "premium_subscriber_count": premium_count,
        "amount_raised": round(amount_raised, 2),
    }

    # Write stats
    with open(stats_output, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats: {subscriber_count} subscribers, {premium_count} premium, ${amount_raised:.2f} raised")

    return emails
