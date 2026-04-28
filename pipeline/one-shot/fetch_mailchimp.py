"""One-shot fetcher for MailChimp-era Weekly Thing campaigns.

Downloads every sent campaign's metadata + HTML + plain-text content
from the Mailchimp Marketing API into cache/mailchimp_campaigns.json,
and builds a {issue_number: campaign_id} mapping in
cache/mailchimp_issue_map.json.

Used downstream by pipeline/one-shot/restore_mailchimp_images.py and
pipeline/one-shot/populate_missing_images.py to recover content that was lost
in the plain-text-only Buttondown import.

Auth: Mailchimp Marketing API basic auth. Use any username; the key
is the password. The key suffix (-us2, -us19, ...) is the datacenter
that becomes the hostname prefix.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "cache"
CAMPAIGNS_CACHE = CACHE_DIR / "mailchimp_campaigns.json"
ISSUE_MAP_CACHE = CACHE_DIR / "mailchimp_issue_map.json"
EMAILS_JSON = ROOT / "site" / "_data" / "emails.json"


def get_base_and_auth():
    key = os.environ.get("MAILCHIMP_API_KEY")
    if not key or "-" not in key:
        raise RuntimeError(
            "MAILCHIMP_API_KEY missing or malformed (expected ...-us2)")
    dc = key.rsplit("-", 1)[-1]
    return f"https://{dc}.api.mailchimp.com/3.0", ("anystring", key)


def fetch_all_campaigns(base, auth):
    """Paginated GET /campaigns?status=sent."""
    campaigns = []
    offset = 0
    page_size = 100
    while True:
        r = requests.get(
            f"{base}/campaigns",
            auth=auth,
            params={
                "count": page_size,
                "offset": offset,
                "status": "sent",
                "sort_field": "send_time",
                "sort_dir": "ASC",
            },
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        campaigns.extend(d["campaigns"])
        total = d["total_items"]
        print(f"  fetched {len(campaigns)}/{total} campaigns")
        if len(campaigns) >= total:
            break
        offset += page_size
    return campaigns


def fetch_content(base, auth, campaign_id):
    r = requests.get(
        f"{base}/campaigns/{campaign_id}/content", auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def build_issue_map(campaigns, emails_by_date):
    """Map campaign_id → issue_number.

    First pass: subject line `#N` gives the number directly (90/109 cases).
    Second pass: for subject lines without `#N`, match campaign.send_time
    date against Buttondown's publish_date (same day) to recover the number.
    """
    mapping = {}
    unmatched = []
    for c in campaigns:
        subj = c["settings"]["subject_line"]
        m = re.search(r"#(\d+)\b", subj)
        if m:
            mapping[int(m.group(1))] = c["id"]
            continue
        unmatched.append(c)
    # Date-based pass for the rest.
    for c in unmatched:
        send_date = c["send_time"][:10]  # YYYY-MM-DD
        if send_date in emails_by_date:
            mapping[emails_by_date[send_date]] = c["id"]
        else:
            print(f"  WARN: no Buttondown issue matches campaign "
                  f"{c['id']} ({send_date} - {c['settings']['subject_line']})")
    return mapping


def main():
    base, auth = get_base_and_auth()
    CACHE_DIR.mkdir(exist_ok=True)

    # 1. List campaigns
    print("Fetching campaign list...")
    campaigns = fetch_all_campaigns(base, auth)
    print(f"Found {len(campaigns)} sent campaigns.")

    # 2. Content for each, skipping any already cached from a prior partial run
    existing = {}
    if CAMPAIGNS_CACHE.exists():
        try:
            existing = json.loads(CAMPAIGNS_CACHE.read_text())
        except Exception:
            existing = {}

    out = dict(existing)
    for i, c in enumerate(campaigns, 1):
        cid = c["id"]
        if cid in out and out[cid].get("html"):
            continue
        print(f"  [{i}/{len(campaigns)}] {cid}  {c['settings']['subject_line'][:70]}")
        try:
            content = fetch_content(base, auth, cid)
        except requests.HTTPError as e:
            print(f"    ERROR: {e}")
            continue
        out[cid] = {
            "id": cid,
            "web_id": c.get("web_id"),
            "subject": c["settings"]["subject_line"],
            "send_time": c["send_time"],
            "archive_url": c.get("archive_url"),
            "long_archive_url": c.get("long_archive_url"),
            "html": content.get("html", ""),
            "plain_text": content.get("plain_text", ""),
        }
        # be polite; Mailchimp rate limits per-connection
        time.sleep(0.1)

    CAMPAIGNS_CACHE.write_text(json.dumps(out, indent=2))
    print(f"\nCached {len(out)} campaigns to {CAMPAIGNS_CACHE}")

    # 3. Build issue_number → campaign_id map
    emails = json.loads(EMAILS_JSON.read_text())
    emails_by_date = {}
    for e in emails:
        n = e.get("number")
        pd = (e.get("publish_date") or "")[:10]
        if isinstance(n, int) and pd:
            emails_by_date[pd] = n
    mapping = build_issue_map(campaigns, emails_by_date)
    ISSUE_MAP_CACHE.write_text(json.dumps(
        {str(k): v for k, v in sorted(mapping.items())}, indent=2))
    print(f"Mapped {len(mapping)} campaigns to Buttondown issues → {ISSUE_MAP_CACHE}")
    print(f"  issue range: #{min(mapping)} – #{max(mapping)}")


if __name__ == "__main__":
    main()
