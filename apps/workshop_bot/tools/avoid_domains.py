"""Domains Linky shouldn't surface from Pinboard's site-wide popular feed.

This mirrors ``pipeline/content/domain_exclusions.py`` — the set the archive
build uses to keep utility / CDN / social / own-domain links out of the
per-issue domain lists. It's copied (not imported) because ``pipeline/`` isn't
an importable package from here, and because the two serve slightly different
ends: this one only gates Linky's popular-feed pass (nothing it touches
ships), so an exact match with the archive list isn't required — keep them
loosely in sync by hand.

A "popular on Pinboard" item on one of these hosts (a Wikipedia article, a
YouTube video, a t.co redirect, one of Jamie's own posts) is noise for the
"could this be a Notable?" judgement, so ``_handle_popular_unseen`` filters
them before they ever reach Linky.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Mirrors pipeline/content/domain_exclusions.py:EXCLUDED_DOMAINS — see module
# docstring on why it's a copy.
EXCLUDED_DOMAINS = {
    # Newsletter's own domains
    "weekly.thingelstad.com",
    "thingelstad.com",
    "www.thingelstad.com",
    "micro.thingelstad.com",
    # Buttondown
    "buttondown.com",
    "buttondown.email",
    # Image CDNs and hosting
    "imgur.com",
    "i.imgur.com",
    "cloudinary.com",
    "res.cloudinary.com",
    "images.unsplash.com",
    "unsplash.com",
    # URL shorteners
    "t.co",
    "bit.ly",
    "tinyurl.com",
    "ow.ly",
    "buff.ly",
    "goo.gl",
    # Generic utility / CDN
    "fonts.google.com",
    "fonts.googleapis.com",
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
    "gravatar.com",
    # Email / unsubscribe
    "email.mg.buttondown.email",
    "manage.kmail-lists.com",
    # Common embed/media hosts
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "open.spotify.com",
    "player.vimeo.com",
    # Reference / encyclopedic
    "en.wikipedia.org",
    "wikipedia.org",
    "en.m.wikipedia.org",
    # Social media
    "twitter.com",
    "x.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "linkedin.com",
    "www.linkedin.com",
}


def _domain_of(url: str) -> str:
    try:
        host = urlsplit((url or "").strip()).hostname or ""
    except (ValueError, AttributeError):
        return ""
    return host.lower()


def is_excluded_domain(domain: str) -> bool:
    domain = (domain or "").lower().strip()
    if not domain:
        return False
    if domain in EXCLUDED_DOMAINS:
        return True
    return any(domain.endswith("." + excluded) for excluded in EXCLUDED_DOMAINS)


def is_excluded_url(url: str) -> bool:
    """True if ``url``'s host is on (or a subdomain of) the exclusion list."""
    return is_excluded_domain(_domain_of(url))
