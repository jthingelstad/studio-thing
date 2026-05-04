"""Phase B: populate / overwrite the front-matter `image:` field on
MailChimp-era issues using the cached Mailchimp campaign HTML.

Runs on every issue whose current `image:` is either:
  1. empty (`image: ''`), OR
  2. a host in the wrong-host allowlist — third-party OG images that
     got auto-derived by Buttondown from an incidental inline asset
     (letsencrypt logo, eff logo, etc.) rather than the real weekly
     hero photo.

Hero selection from the Mailchimp HTML:
  - skip UI chrome (`cdn-images.mailchimp.com/icons`, social-block assets)
  - skip the recurring Weekly Thing branding logo
  - prefer first `gallery.mailchimp.com/.../images/...` (that's where
    Jamie uploaded the weekly hero)
  - fall back to first `micro.thingelstad.com/uploads/...`
  - if neither exists, skip and log

Two phases of use:
  `--list-wrong-hosts` — read-only audit, prints every distinct host
  currently in an `image:` field with counts and sample issues, so
  Jamie can vet WRONG_HOSTS before any writes.

  (no flag)          — do the writes.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import yaml

sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "apps" / "site" / "archive"
CAMPAIGNS_CACHE = ROOT / "cache" / "mailchimp_campaigns.json"
ISSUE_MAP_CACHE = ROOT / "cache" / "mailchimp_issue_map.json"

# Third-party hosts that are never right for an issue's hero image.
# Vetted via --list-wrong-hosts before the first real run.
WRONG_HOSTS = {
    "letsencrypt.org",
    "www.eff.org",
    "wikimediafoundation.org",
    "upload.wikimedia.org",
    "is1-ssl.mzstatic.com",
    "is1.mzstatic.com",
    "static1.squarespace.com",
    "blotcdn.com",
    "buttondown-attachments.s3.us-west-2.amazonaws.com",
}

HTML_IMG_RE = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)

# URL fragments that indicate UI chrome / template assets — never hero.
SKIP_URL_FRAGMENTS = (
    "cdn-images.mailchimp.com/icons",
    "weekly.thingelstad.com/images/logo/",
    "/outline-gray-",  # social block icons
    "/color-",         # more social icons
    "tinyletterapp.com/",  # old Tinyletter CDN assets
)


def load_fm_and_image_line(fp):
    """Return (front_matter_dict, image_value_string_or_None, raw_content)."""
    content = fp.read_text()
    m = re.match(r"^---\n(.+?)\n---\n", content, re.DOTALL)
    if not m:
        return None, None, content
    fm = yaml.safe_load(m.group(1))
    image = fm.get("image")
    return fm, image, content


def pick_hero(html):
    """Return the first URL in `html` that qualifies as a hero image."""
    gallery_candidates = []
    micro_candidates = []
    for url in HTML_IMG_RE.findall(html):
        if any(frag in url for frag in SKIP_URL_FRAGMENTS):
            continue
        if "gallery.mailchimp.com/" in url and "/images/" in url:
            gallery_candidates.append(url)
        elif "micro.thingelstad.com/uploads/" in url:
            micro_candidates.append(url)
    if gallery_candidates:
        return gallery_candidates[0]
    if micro_candidates:
        return micro_candidates[0]
    return None


def url_host(url):
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def list_wrong_hosts(issue_map):
    counts = Counter()
    examples = {}
    for fp in sorted(ARCHIVE_DIR.glob("*.md"),
                     key=lambda p: int(p.stem) if p.stem.isdigit() else 9999):
        if not fp.stem.isdigit():
            continue
        n = int(fp.stem)
        if str(n) not in issue_map:
            continue  # not a MailChimp-era issue
        _, image, _ = load_fm_and_image_line(fp)
        if not image:
            continue
        host = url_host(image)
        counts[host] += 1
        examples.setdefault(host, []).append(n)

    print("Hosts currently in `image:` across MailChimp-era issues:\n")
    for host, n in counts.most_common():
        flag = "  WRONG" if host in WRONG_HOSTS else ""
        samples = ", ".join(f"#{x}" for x in examples[host][:5])
        print(f"  [{n:3}] {host}{flag}")
        print(f"        {samples}{'…' if len(examples[host]) > 5 else ''}")


def update_image_line(content, new_url):
    """Replace the front-matter `image:` line (empty or populated)
    with `image: <new_url>`."""
    new, n = re.subn(
        r"^image:.*$",
        f"image: {new_url}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("expected exactly 1 image line to replace")
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-wrong-hosts", action="store_true",
                    help="Audit only: print hosts currently in image: field")
    args = ap.parse_args()

    campaigns = json.loads(CAMPAIGNS_CACHE.read_text())
    issue_map = json.loads(ISSUE_MAP_CACHE.read_text())

    if args.list_wrong_hosts:
        list_wrong_hosts(issue_map)
        return

    if args.issues:
        files = [ARCHIVE_DIR / f"{n}.md" for n in args.issues]
    else:
        files = sorted(ARCHIVE_DIR.glob("*.md"))

    counts = Counter()
    skipped_no_hero = []
    for fp in files:
        if not fp.exists():
            continue
        if not fp.stem.isdigit():
            continue
        n = int(fp.stem)
        if str(n) not in issue_map:
            continue
        _, image, content = load_fm_and_image_line(fp)
        image_str = image or ""
        # Decide if this issue needs processing
        if image_str:
            host = url_host(image_str)
            if host not in WRONG_HOSTS:
                continue  # current image is acceptable

        cid = issue_map[str(n)]
        html = campaigns.get(cid, {}).get("html", "")
        if not html:
            counts["no_cache"] += 1
            continue

        hero = pick_hero(html)
        if not hero:
            skipped_no_hero.append(n)
            counts["no_hero"] += 1
            continue

        new_content = update_image_line(content, hero)
        if new_content == content:
            continue
        counts["updated"] += 1
        action = "would set" if args.dry_run else "set"
        was = f" (was {image_str})" if image_str else ""
        print(f"#{n}: {action} image={hero}{was}")
        if not args.dry_run:
            fp.write_text(new_content)

    print(f"\nUpdated: {counts['updated']}  "
          f"No hero candidate: {counts['no_hero']}  "
          f"No cache: {counts['no_cache']}")
    if skipped_no_hero:
        print(f"Skipped (no hero): {skipped_no_hero}")


if __name__ == "__main__":
    main()
