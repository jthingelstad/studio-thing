"""Migrate MailChimp-hosted images to files.thingelstad.com (S3).

For every `gallery.mailchimp.com` URL referenced in the archive:
  1. Download the image.
  2. Upload it to `s3://files.thingelstad.com/weekly-thing/<N>/cover.jpg`.
  3. Rewrite every occurrence in the archive (front-matter `image:` and
     inline body references) to the new S3 URL.

Each MailChimp-era issue has exactly one unique gallery URL — used
for both the hero and the Weekly Photo. We keep one file per issue as
`cover.jpg` matching the modern convention.

Destination pattern:
    https://files.thingelstad.com/weekly-thing/<N>/cover.jpg

Requires AWS credentials in the default chain (`aws configure` or
session login). Bucket name hardcoded to `files.thingelstad.com`;
override with `--bucket`.
"""

import argparse
import re
import sys
from pathlib import Path

import boto3
import requests
from botocore.exceptions import ClientError

sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "apps" / "site" / "archive"

GALLERY_URL_RE = re.compile(r"https?://gallery\.mailchimp\.com/[^\s\")\]]+")


def collect_issues_with_gallery_images():
    """Return [(issue_number, archive_path, unique_gallery_url)]."""
    out = []
    for fp in sorted(
        ARCHIVE_DIR.glob("*.md"), key=lambda p: int(p.stem) if p.stem.isdigit() else 9999
    ):
        if not fp.stem.isdigit():
            continue
        content = fp.read_text()
        urls = GALLERY_URL_RE.findall(content)
        unique = sorted(set(urls))
        if not unique:
            continue
        if len(unique) > 1:
            print(
                f"#{fp.stem}: WARNING — {len(unique)} unique gallery URLs; "
                f"only the first will be migrated. Others:"
            )
            for u in unique[1:]:
                print(f"    {u}")
        out.append((int(fp.stem), fp, unique[0]))
    return out


def s3_key(issue):
    return f"weekly-thing/{issue}/cover.jpg"


def s3_public_url(bucket, key):
    # Virtual-hosted style, direct https. Works when the bucket is
    # `files.thingelstad.com` and that name is a DNS CNAME to the bucket
    # (the existing modern convention).
    return f"https://{bucket}/{key}"


def ensure_uploaded(s3, bucket, key, source_url, dry_run):
    """Upload source_url to s3 if the key doesn't already exist."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return "already-in-s3"
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            raise
        # key doesn't exist yet — upload
    if dry_run:
        return "would-upload"
    r = requests.get(source_url, timeout=30)
    r.raise_for_status()
    body = r.content
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000, immutable",
    )
    return f"uploaded-{len(body)}B"


def rewrite_file(fp, old_url, new_url):
    """Replace every occurrence of old_url in fp with new_url.
    Returns count of replacements."""
    content = fp.read_text()
    if old_url not in content:
        return 0
    new_content = content.replace(old_url, new_url)
    n = content.count(old_url)
    fp.write_text(new_content)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issues", nargs="*", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bucket", default="files.thingelstad.com")
    args = ap.parse_args()

    entries = collect_issues_with_gallery_images()
    if args.issues:
        entries = [e for e in entries if e[0] in args.issues]
    if not entries:
        print("Nothing to migrate.")
        return

    s3 = boto3.client("s3") if not args.dry_run else None
    # Probe (only when live)
    if s3:
        s3.head_bucket(Bucket=args.bucket)

    print(f"Processing {len(entries)} issue(s) into s3://{args.bucket}/weekly-thing/\n")

    uploaded = 0
    already = 0
    rewritten_files = 0
    total_rewrites = 0

    for issue, fp, url in entries:
        key = s3_key(issue)
        new_url = s3_public_url(args.bucket, key)
        try:
            if s3:
                status = ensure_uploaded(s3, args.bucket, key, url, dry_run=False)
            else:
                status = "would-upload"
        except Exception as e:
            print(f"#{issue}: ERROR uploading: {e}")
            continue

        if status == "already-in-s3":
            already += 1
        elif status.startswith("uploaded"):
            uploaded += 1

        # Rewrite every file that contains this URL (usually just fp, but be
        # safe and check other files too in case an image was referenced
        # cross-issue)
        for other_fp in ARCHIVE_DIR.glob("*.md"):
            if not other_fp.stem.isdigit():
                continue
            if args.dry_run:
                n = other_fp.read_text().count(url)
                if n:
                    total_rewrites += n
                    if other_fp == fp:
                        rewritten_files += 1
            else:
                n = rewrite_file(other_fp, url, new_url)
                if n:
                    total_rewrites += n
                    if other_fp == fp:
                        rewritten_files += 1

        verb = "would" if args.dry_run else ""
        print(f"#{issue}: {status} | {verb} rewrite → {new_url}")

    print("\nSummary:")
    print(f"  uploaded:    {uploaded}")
    print(f"  already:     {already}")
    print(f"  URL rewrites:{total_rewrites} occurrences across {rewritten_files} file(s)")


if __name__ == "__main__":
    main()
