# LLM Archive Audit

Model: `claude-opus-4-7`
Issues scanned: **344**
Verified findings: **1391**
Rejected (snippet not found in source): 9
Tokens: 3,207,678 in + 221,463 out (cache r/w 0/0)
Estimated cost: ~$21.57

## Verified findings by severity

- `high`: 165
- `medium`: 420
- `low`: 806

## Verified findings by category

- `typo`: 570
- `malformed-link`: 498
- `narrative-break`: 100
- `migration-artifact`: 67
- `header-error`: 59
- `other`: 45
- `image-problem`: 37
- `dangling-reference`: 15

## Per-issue findings

### #1 — Weekly Thing for May 13, 2017

- Era: Tinyletter
- Overall: The issue is in good shape and era-normal for a Tinyletter issue; only a minor punctuation oddity in a quoted excerpt was noted.
  - **[LOW] typo** — The apostrophe after 'have' appears where a comma or period was intended, but this is quoted from the source article so may be intentional.
    - `Maybe they have’ maybe they haven’t.`
    - Fix: Verify against source; if a transcription error, change to 'Maybe they have, maybe they haven't.'

### #2 — Weekly Thing for May 20, 2017

- Era: Tinyletter
- Overall: Issue reads cleanly for its Tinyletter era; the only notable problem is the dead Tinyletter-hosted promotion image already flagged by the static audit.
  - **[MEDIUM] image-problem** — The static audit confirmed the Tinyletter-hosted EFF logo image is unreachable (DNS failure), so readers see a broken image in the Promotion section.
    - `[![EFF Logo](http://gallery.tinyletterapp.com/178527e39f3fdfbc6cb90d7ad4c92f8cc7481ff2/images/25192a65-96d3-4b97-ab6b-d324e8bf8d42.png)](https://www.eff.org)`
    - Fix: Rehost the EFF logo on a durable location (or remove the image) and update the src URL.

### #3 — Weekly Thing for May 27, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; one broken link URL and one closing-line typo are the only notable issues.
  - **[HIGH] malformed-link** — The URL is malformed with four slashes after `http:` and points only to the domain root, not the actual article.
    - `### [Target and Elasticsearch: Maintaining an ELK stack over Peak Season](http:////target.github.io)`
    - Fix: Restore the correct article URL on target.github.io.
  - **[MEDIUM] typo** — Clear typo — should be "Thank you for subscribing."
    - `Thank your or subscribing.`
    - Fix: Change "Thank your or subscribing" to "Thank you for subscribing".

### #4 — Weekly Thing for June 3, 2017

- Era: Tinyletter
- Overall: Issue is in good shape structurally; only a handful of minor typos, most notably the garbled closing line "Thank your or subscribing."
  - **[LOW] typo** — "Wordwide" is a clear misspelling of "Worldwide".
    - `Next week we have Apple's Wordwide Developer Conference.`
    - Fix: Change "Wordwide" to "Worldwide".
  - **[LOW] typo** — "get's" should be "gets" (no apostrophe for a verb).
    - `I’m eager to see what get's announced.`
    - Fix: Change "get's" to "gets".
  - **[LOW] typo** — "it’s" should be "its" (possessive).
    - `Hit it’s funding goal on the first day.`
    - Fix: Change "it’s" to "its".
  - **[LOW] typo** — "your" should be "you're".
    - `If you look the right direction you feel like your in the woods.`
    - Fix: Change "your" to "you're".
  - **[MEDIUM] typo** — Clearly garbled closing phrase; should read "Thank you for subscribing."
    - `Thank your or subscribing.`
    - Fix: Replace with "Thank you for subscribing."

### #5 — Weekly Thing for June 10, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall with era-normal Tinyletter formatting; only a minor closing-line typo was found.
  - **[LOW] typo** — Clear typo: 'Thank your or subscribing' should be 'Thank you for subscribing'.
    - `Thank your or subscribing.`
    - Fix: Change to 'Thank you for subscribing.'

### #8 — Weekly Thing for July 1, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; two clear name typos ("Le's Encrypt" and "Larry Lessing") are the only notable issues.
  - **[MEDIUM] typo** — This is a clear typo — should be "Let's Encrypt" (the subject of the linked article).
    - `I'm a big fan of Le's Encrypt`
    - Fix: Change "Le's Encrypt" to "Let's Encrypt".
  - **[LOW] typo** — The author's name is Larry Lessig, not Lessing (the link URL confirms this).
    - `by [Larry Lessing](http://www.lessig.org/about/)`
    - Fix: Change "Larry Lessing" to "Larry Lessig".

### #9 — Weekly Thing for July 8, 2017

- Era: Tinyletter
- Overall: The issue is in good shape overall with era-normal formatting; only a minor handle typo worth noting.
  - **[LOW] typo** — The display handle '@cunngleah' doesn't match the linked username 'cunningleah' — likely a typo in the visible handle.
    - `*Via [@cunngleah](https://twitter.com/cunningleah)*`
    - Fix: Correct the displayed handle to '@cunningleah' to match the link target.

### #10 — Weekly Thing for July 15, 2017

- Era: Tinyletter
- Overall: Issue is generally in good shape for the Tinyletter era; main concern is the broken Internet Archive promo image, plus a couple of minor typos.
  - **[MEDIUM] image-problem** — Static audit confirmed this image URL returns HTTP 415, so the Internet Archive promo image is broken for readers.
    - `[![image](https://assets.buttondown.email/internet-archive.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=DC32nL3%2F5W9EgTWxWcCPp55TF94%3D&Expires=1707555020)](https://archive.org)`
    - Fix: Replace with a working image URL or remove the broken image reference.
  - **[LOW] typo** — 'there' should be 'their' — clear homophone typo.
    - `It's great to see what OmniGroup is doing with there applications on iOS.`
    - Fix: Change 'there' to 'their'.
  - **[LOW] typo** — Sentence is missing a word (likely 'for') between 'task' and 'most'.
    - `Managing your calendar is an important task most of us.`
    - Fix: Change to 'an important task for most of us.'

### #11 — Weekly Thing for July 22, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; the only notable problem is the broken Let's Encrypt promo image flagged by the static audit, plus a minor run-together link title.
  - **[LOW] typo** — The link title has a missing space/separator between 'Blog' and 'Android', appearing as a run-together word from the source page title.
    - `TrendLabs Security Intelligence BlogAndroid Backdoor GhostCtrl`
    - Fix: Clean up the link title to 'Android Backdoor GhostCtrl can Silently Record Your Audio, Video, and More - TrendLabs Security Intelligence Blog'.
  - **[MEDIUM] image-problem** — Static audit confirmed this image returns HTTP 415 — the signed S3 URL has expired/is invalid, so the Let's Encrypt promo image won't render.
    - `[![image](https://assets.buttondown.email/Lets-Encrypt.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=38GtC7f5JibrUizvcGLgYvObAlg%3D&Expires=1707555309)](https://letsencrypt.org)`
    - Fix: Re-host the Let's Encrypt logo at a stable URL and update the image reference.

### #12 — Weekly Thing for July 29, 2017

- Era: Tinyletter
- Overall: Readable issue, but the Highlighted iOS App section has two malformed markdown links with nested `[Bear](...)` targets that will render visibly broken, plus an expired promo image and a couple of minor typos.
  - **[HIGH] malformed-link** — The image link target is malformed — it contains a nested markdown link `[Bear](...)` as the URL instead of just the URL, which will render as broken markdown.
    - `[![image](https://assets.buttondown.email/512x512bb.jpg?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=C%2F9UcIhtHhSXGhH8kMrJz7%2BuHhk%3D&Expires=1707555609)]([Bear](https://itunes.apple.com/us/app/bear/id1016366447?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com))`
    - Fix: Replace the link target with just the iTunes URL: `](https://itunes.apple.com/us/app/bear/id1016366447?...)`.
  - **[HIGH] malformed-link** — The heading link has a nested `[Bear](...)` as its URL target, which is malformed markdown and will not render correctly.
    - `### [Bear]([Bear](https://itunes.apple.com/us/app/bear/id1016366447?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com))`
    - Fix: Change to `### [Bear](https://itunes.apple.com/us/app/bear/id1016366447?...)`.
  - **[MEDIUM] image-problem** — Static audit flagged this image as returning HTTP 415 — the signed URL has expired.
    - `[![image](https://assets.buttondown.email/wikitribune.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=5wh9BQPQOOjWMV03EtZW3I9gmaw%3D&Expires=1707555607)](https://www.wikitribune.com)`
    - Fix: Re-host the WikiTribune promo image or update to a non-expiring asset URL.
  - **[LOW] typo** — "To give at a try" should read "To give it a try".
    - `To give at a try, I setup a`
    - Fix: Change "give at a try" to "give it a try".
  - **[LOW] typo** — "case" should be "cause".
    - `you could have a payment failure and an unmonitored email address case a big problem.`
    - Fix: Change "case a big problem" to "cause a big problem".

### #13 — Weekly Thing for August 5, 2017

- Era: Tinyletter
- Overall: The issue has a significant formatting break in the Links section where a stray asterisk collapses ~10 link entries into one run-on paragraph, which should be fixed; a broken promo image also persists.
  - **[HIGH] narrative-break** — A stray asterisk before `###` prevents the heading from rendering and collapses many subsequent link entries into a single run-on paragraph.
    - `But he beat me—and I was early. *### [Quantify everything with Exist.io custom tracking - BrettTerpstra.com](http://brettterpstra.com/2017/08/02/quantify-everything-with-exist-dot-io-custom-tracking/)`
    - Fix: Remove the stray `*` and ensure each `###` heading starts on its own line so the following link items render correctly.
  - **[HIGH] narrative-break** — A stray `*` appears mid-sentence, a leftover from the broken formatting run that merged multiple link entries.
    - `"Distributed systems are never 'up'; they exist in a constant state of partially degraded service."* There is a lot of truth there.`
    - Fix: Remove the stray asterisk and restore the proper heading/paragraph structure for the affected link entries.
  - **[MEDIUM] image-problem** — Static audit confirms the EFF promotional image returns HTTP 415, so the image is broken in the archive.
    - `[![image](https://assets.buttondown.email/eff.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=lL2eoakEQfEm5MsbmxupmyCNpJw%3D&Expires=1707555883)](https://www.eff.org)`
    - Fix: Re-host the EFF logo on a stable URL or replace with a valid asset.

### #14 — Weekly Thing for August 12, 2017

- Era: Tinyletter
- Overall: Issue reads cleanly overall; a couple of minor typos and one confirmed broken image asset from the migration.
  - **[LOW] typo** — 'this thoughts' should be 'his thoughts'.
    - `the only place to get this thoughts during that time.`
    - Fix: Change 'this thoughts' to 'his thoughts'.
  - **[LOW] typo** — 'goo things' should be 'good things'.
    - `how to create the goo things about the social web`
    - Fix: Change 'goo things' to 'good things'.
  - **[LOW] typo** — Missing possessive — should be 'Josh Bernoff's site'.
    - `I like [Josh Bernoff](https://withoutbullshit.com/about-me) site`
    - Fix: Change to 'Josh Bernoff's site'.
  - **[MEDIUM] image-problem** — Static audit flagged this image as broken (HTTP 415); signed URL has expired.
    - `https://assets.buttondown.email/Wikimedia_Foundation_logo.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=9jZCP1IxiEk1k4NaedoLNOrGYYM%3D&Expires=1707556128`
    - Fix: Re-host the Wikimedia logo image or replace the broken asset URL.

### #15 — Weekly Thing for August 19, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; only a minor wording typo in the Cloudflare/Daily Stormer blurb. The static audit's broken EFF promo image is a real concern but is era-normal Buttondown asset expiration.
  - **[LOW] typo** — 'As you remind this' appears to be a typo for 'As you read this' or similar — 'remind this' is not grammatical.
    - `As you remind this remember that WikiLeaks was also denied service`
    - Fix: Change 'As you remind this remember' to 'As you read this, remember'.

### #16 — Weekly Thing for August 26, 2017

- Era: Tinyletter
- Overall: Issue reads cleanly and is era-normal for Tinyletter; only concern is the one broken promo image flagged by the static audit.
  - **[LOW] image-problem** — Static audit confirmed this image returns HTTP 415 — the Creative Commons promo image is broken in the archive.
    - `![image](https://assets.buttondown.email/creative-commons.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=J%2BQ5JdRiEGPjh69GPTmD3CUU7ZU%3D&Expires=1707556718)`
    - Fix: Replace with a working image URL or remove the broken image reference.

### #17 — Weekly Thing for September 2, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; main concern is the broken Minnestar promo image flagged by the static audit, plus one minor typo.
  - **[MEDIUM] image-problem** — Static audit confirms this Minnestar promotional image returns HTTP 415 and won't render.
    - `[![image](https://assets.buttondown.email/Minnestar.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=eUOodusAi8sZmdiM79h8sSUgRNY%3D&Expires=1707556986)](https://minnestar.org)`
    - Fix: Re-upload the Minnestar logo to a working asset URL or remove the broken image wrapper.
  - **[LOW] typo** — "git" is an obvious typo for "give".
    - `I installed and signed up for Sarahah and I did git it access to my contacts.`
    - Fix: Change "git" to "give".

### #18 — Weekly Thing for September 9, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; only a minor typo and a known broken Creative Commons promo image (already flagged by static audit).
  - **[LOW] typo** — 'The' should be 'This' — clear typo at the start of a sentence.
    - `The is the same content that shows up every week`
    - Fix: Change 'The is' to 'This is'.

### #19 — Weekly Thing for September 16, 2017

- Era: Tinyletter
- Overall: Issue reads cleanly in Tinyletter-era style; only concern is the broken EFF promo image flagged by the static audit.
  - **[LOW] image-problem** — Static audit flagged this image as returning HTTP 415; the EFF promotion logo likely does not render for archive readers.
    - `[![image](https://assets.buttondown.email/eff.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=Svi%2FXVP%2FXfd5T0OGxWLVYaLNe6s%3D&Expires=1707557505)](https://www.eff.org)`
    - Fix: Replace with a working EFF logo asset or remove the broken image link.

### #20 — Weekly Thing for September 23, 2017

- Era: Tinyletter
- Overall: Issue #20 is in good shape overall; the only notable issue is the expired EFF promotional image URL and one minor sentence-level truncation.
  - **[MEDIUM] image-problem** — Static audit confirmed this EFF promotion image returns HTTP 415; the signed URL has expired, leaving a broken image in the Promotion section.
    - `[![image](https://assets.buttondown.email/eff.png?AWSAccessKeyId=AKIAJEXF6S6TCOKT7N3Q&Signature=y9qu57DmH%2Frxr5zas%2BqFSc129yo%3D&Expires=1707557735)](https://www.eff.org)`
    - Fix: Replace the expired signed asset URL with a permanent copy of the EFF logo hosted on the archive.
  - **[LOW] narrative-break** — The sentence reads as if it was truncated — 'takes ... visual display guidelines' lacks a verb completion (e.g., 'takes a look at' or 'applies').
    - `John Krygier, a cartographer and professor, takes [Tufte's](http://edwardtufte.com) visual display guidelines.`
    - Fix: Add the missing verb phrase, e.g., 'takes a look at Tufte's visual display guidelines.'

### #21 — Weekly Thing for September 30, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; only minor typos noted and the static-audit image issue is a known asset-expiry artifact.
  - **[LOW] typo** — 'too' should be 'to' — a clear typo.
    - `Tammy has been [teaching me to play cribbage](http://www.thingelstad.com/2017/09/23/at-cabin-kids.html) and I wanted too find a way`
    - Fix: Change 'wanted too find' to 'wanted to find'.
  - **[LOW] typo** — 'temperator' should be 'temperature' — appears to be a typo (though it may also appear in the linked microblog title).
    - `[“Feels like” temperator of 93℉ right now?`
    - Fix: Consider correcting to 'temperature' if not intentional.

### #22 — Weekly Thing for October 7, 2017

- Era: Tinyletter
- Overall: Issue is in good shape overall; only minor nits (one typo inside a quote and a missing end-of-sentence period). The static audit's broken promotion image is legitimate.
  - **[LOW] typo** — 'partices' is a clear typo for 'particles' within a blockquote.
    - `doubling the number of partices would mean`
    - Fix: This is inside a quoted passage; if the original source has the same typo leave it, otherwise correct to 'particles'.
  - **[LOW] narrative-break** — Sentence ends without terminal punctuation, making it look truncated.
    - `We are not in the [Matrix](http://www.imdb.com/title/tt0133093/)`
    - Fix: Add a period after the closing parenthesis.

### #23 — Weekly Thing for October 14, 2017

- Era: Tinyletter
- Overall: Readable issue, but contains several migration-era malformed links where anchor text boundaries absorbed surrounding prose, plus a couple of minor typos.
  - **[MEDIUM] malformed-link** — The link anchor text is split awkwardly across two links with mismatched URLs — 'search using JavaScript to Algolia' points to a Twitter profile instead of Algolia, suggesting the links got mangled during migration.
    - `Netlify [shares how they moved from Lunr.js](https://lunrjs.com) [search using JavaScript to Algolia](https://twitter.com/anna_picchetti)`
    - Fix: Rework the sentence so the link text matches the URLs, or re-point the second link to the correct Algolia/Netlify destination.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-sentence at '[of room to improve!' which is clearly a mis-placed bracket from migration — the link text should just be '@anna_picchetti'.
    - `There is a lot [of room to improve! Thanks @anna_picchetti](https://twitter.com/anna_picchetti) for the link!`
    - Fix: Move the opening bracket so only '@anna_picchetti' is the linked text.
  - **[MEDIUM] malformed-link** — Link anchor text brackets are placed mid-phrase in a way that includes stray words like 'they could combine a' and leading comma/space ', a' inside the link text — a migration artifact.
    - `[they could combine a Circuit Breaker](https://www.martinfowler.com/bliki/CircuitBreaker.html) [, a Bulkhead](https://www.amazon.co.uk/dp/1680502395/)`
    - Fix: Re-anchor the links so only 'Circuit Breaker' and 'Bulkhead' are the linked text.
  - **[MEDIUM] malformed-link** — Link anchor text absorbs surrounding prose ('went ahead and created a', 'anyway. It complements my', 'and') — classic migration artifact where link boundaries shifted.
    - `I [went ahead and created a security.txt](https://links.thingelstad.com/security.txt) [anyway. It complements my robots.txt](https://links.thingelstad.com/robots.txt) [and humans.txt](https://links.thingelstad.com/humans.txt) .`
    - Fix: Re-anchor so only 'security.txt', 'robots.txt', and 'humans.txt' are the linked text.
  - **[LOW] malformed-link** — Link anchor text includes the trailing prose 'what they include by default.' before 'Brave' — the bracket should only enclose 'Brave'.
    - `[what they include by default. Brave](https://www.brave.com)`
    - Fix: Move the opening bracket so only 'Brave' is linked.
  - **[LOW] malformed-link** — Link anchor text spans unrelated words ('me of a modern day lynx') rather than just 'lynx'.
    - `In some ways this reminds [me of a modern day lynx](http://lynx.invisible-island.net) browser`
    - Fix: Re-anchor so only 'lynx' is linked.
  - **[LOW] typo** — 'things' should be 'thinks'.
    - `Nobody things of Apple as a semiconductor company.`
    - Fix: Change 'things' to 'thinks'.
  - **[LOW] typo** — 'there' should be 'their'.
    - `going in there spam folders`
    - Fix: Change 'there' to 'their'.

### #24 — Weekly Thing for October 21, 2017

- Era: Tinyletter
- Overall: The issue is largely readable but has several migration artifacts around link formatting and bare URLs that once were images/embeds, plus one likely typo ('strategic more').
  - **[MEDIUM] malformed-link** — The link text is split awkwardly across two separate markdown links creating a broken-looking '[...]'s NextDraft' fragment, a migration artifact from reformatting.
    - `[I’m a subscriber of Dave Pell](https://twitter.com/davepell) ['s NextDraft](http://nextdraft.com) and really like it. Nice interview talking about how NextDraft came about and highlighting is workflow for making it.`
    - Fix: Merge into a single natural sentence with one link, e.g., 'I’m a subscriber of [Dave Pell](https://twitter.com/davepell)’s [NextDraft](http://nextdraft.com)'.
  - **[LOW] malformed-link** — Two adjacent link texts without a connecting word/punctuation reads as broken prose, likely a migration artifact.
    - `One [is a flat array of links](https://links.thingelstad.com/feeds/links.json) [the other is grouped by hostname](https://links.thingelstad.com/feeds/links-by-host.json) .`
    - Fix: Add 'and' between the two links: 'One [is a flat array of links](...) and [the other is grouped by hostname](...)'.
  - **[LOW] typo** — 'strategic more' appears to be a typo for 'strategic moat'.
    - `Make it your strategic more!`
    - Fix: Change 'strategic more' to 'strategic moat'.
  - **[LOW] other** — An H2 heading is used for the app author byline inside the Featured App section, which breaks the TOC hierarchy (should be plain text or a lower-level element).
    - `## by Kevin Chang`
    - Fix: Convert 'by Kevin Chang' to regular text rather than an H2 heading.
  - **[LOW] image-problem** — Bare URL on its own line in the Promotion section looks like a leftover image/embed placeholder from migration rather than intentional content.
    - `https://archive.org`
    - Fix: Either remove the bare URL or convert to an explicit image/link with alt text.
  - **[LOW] image-problem** — Bare URL on its own line in the Featured App section appears to be a leftover image embed placeholder from the original Mailchimp layout.
    - `https://itunes.apple.com/us/app/copied/id1015767349?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the bare URL or replace with a proper image reference with alt text.

### #25 — Weekly Thing for October 28, 2017

- Era: Tinyletter
- Overall: Readable issue with era-typical style, but several links in the Links and Promotion sections have anchor text that runs across sentence boundaries — likely migration artifacts worth cleaning up.
  - **[HIGH] malformed-link** — The link text incorrectly spans across a sentence boundary, suggesting the link anchor was misplaced during migration — 'totally DIY' and 'I'll stick with Feedbin' should be separate thoughts.
    - `Cool self-hosted RSS reader option. Nice to see people working on these as options for those that want to be [totally DIY. I'll stick with Feedbin](https://feedbin.com) though.`
    - Fix: Rework so only 'Feedbin' (or similar) is the link text, e.g., 'want to be totally DIY. I'll stick with [Feedbin](https://feedbin.com) though.'
  - **[HIGH] malformed-link** — Link text contains an unbalanced parenthesis and awkwardly spans unrelated phrase — the anchor clearly got misplaced in migration.
    - `[I use Pinboard](https://pinboard.in/) to save [my links (and power Link Thing](https://links.thingelstad.com) )`
    - Fix: Restructure the links so anchor text matches the target, e.g., '[I use Pinboard](https://pinboard.in/) to save my links (and power [Link Thing](https://links.thingelstad.com))'.
  - **[MEDIUM] malformed-link** — Link text spans a sentence boundary ('surface. Read the about the motivation'), indicating a migration-era anchor misplacement, and contains a grammatical glitch ('Read the about the motivation').
    - `but this looks very nice on the [surface. Read the about the motivation](https://dramatiq.io/motivation.html)`
    - Fix: Split the sentences and make only 'the motivation' (or similar) the link text.
  - **[MEDIUM] malformed-link** — Link anchor spans across a sentence boundary and points to Wikipedia though text says 'backer' — misplaced anchor from migration.
    - `I became a [backer. I've been impressed with Wikipedia](https://www.wikipedia.org)`
    - Fix: Rewrite so the link text is just 'Wikipedia' on the correct clause.
  - **[MEDIUM] malformed-link** — Nearby link '[tackle this. Become a supporter today!](https://www.wikitribune.com/become-supporter/)' spans sentence boundary; anchor text extends past sentence end.
    - `I am very curious to see how they realize these objectives. I've previously thought about how news can be reinvented.`
    - Fix: Restrict the anchor text to 'Become a supporter today!' only.
  - **[LOW] narrative-break** — Sentence ends with no terminal punctuation after the link, suggesting a minor truncation.
    - `I'd recommend [reading the similar one for sed](https://github.com/learnbyexample/Command-line-text-processing/blob/master/gnu_sed.md)`
    - Fix: Add a period at the end of the sentence.

### #26 — Weekly Thing for November 4, 2017

- Era: Tinyletter
- Overall: Readable overall, but one link-list entry (MarketWatch) is rendered as an H2 with a bare parenthetical URL instead of the standard H3 link, and several entries have link boundaries that clearly shifted during migration.
  - **[HIGH] malformed-link** — This link-list item is rendered as an H2 heading with the URL in parentheses instead of the era-standard `### [title](url)` H3 link format, breaking the TOC and the link.
    - `## The history of MarketWatch: How a sports data startup became a half-billion-dollar financial news site - Outside the Box - MarketWatch (https://www.marketwatch.com/(S(rnrsydaynixa5x55oiibxm45))/story/the-history-of-marketwatch-how-a-sports-data-startup-became-a-half-billion-dollar-financial-news-site-2017-10-30)`
    - Fix: Change to `### [The history of MarketWatch: ... - MarketWatch](https://www.marketwatch.com/...)` to match surrounding H3 link entries.
  - **[MEDIUM] malformed-link** — Not actually a problem — ignore.
    - `I've always thought it was cool to be the house that gave out the full size candy bars 🍫 but maybe not!`
    - Fix: N/A
  - **[MEDIUM] narrative-break** — The link brackets split the prose awkwardly ("fellow minnestar" / "board member Jenna Pederson"), a common migration pattern where a single link got broken into two — readable but the phrase 'fellow minnestar board member' should be one link.
    - `Love this perspective [and highlight from my fellow minnestar](https://minnestar.org) [board member Jenna Pederson](http://jennapederson.com) .`
    - Fix: Merge into a single link such as `[fellow Minnestar board member Jenna Pederson](http://jennapederson.com)`.
  - **[MEDIUM] narrative-break** — Link boundaries split the sentence across three separate hyperlinks in odd places, suggesting migration artifact where prose and links were incorrectly re-chunked.
    - `Whoa, [nice call out in The Economist](https://www.economist.com) [to my friend Jim Bernard](https://www.linkedin.com/in/bernardjim/) and the work his team [has been doing at Star Tribune](http://www.startribune.com) !`
    - Fix: Re-anchor the links to natural phrases (e.g., 'The Economist', 'Jim Bernard', 'Star Tribune') without wrapping surrounding prose inside the link text.
  - **[LOW] narrative-break** — Link text awkwardly includes 'work I jump into', a migration artifact where the anchor should only be 'Sublime Text'.
    - `When I want to do real [work I jump into Sublime Text](http://www.sublimetext.com) .`
    - Fix: Change to `When I want to do real work I jump into [Sublime Text](http://www.sublimetext.com).`
  - **[LOW] narrative-break** — Link text spans a sentence boundary ('see with data. Sorry Larry Wall'), another migration artifact.
    - `Wow, I've sort of intuitively known this but it's pretty amazing to [see with data. Sorry Larry Wall](https://en.wikipedia.org/wiki/Larry_Wall) !`
    - Fix: Restrict the anchor to 'Larry Wall' only.

### #27 — Weekly Thing for November 11, 2017

- Era: Tinyletter
- Overall: Readable Tinyletter-era issue, but several section headers have orphaned bare URLs where images or embeds should appear, and a few microblog permalinks show absorbed-URL slugs worth verifying.
  - **[MEDIUM] narrative-break** — The link text appears to have swallowed part of the sentence — 'easier to use objects backed by Redis' should read naturally but the link bracket starts mid-phrase, and the Redis link is odd placement for 'to use objects backed by Redis'.
    - `Very nice Python library to provide easier [to use objects backed by Redis](https://redis.io) .`
    - Fix: Rework so the link anchors 'Redis' only, e.g., 'easier to use objects backed by [Redis](https://redis.io).'
  - **[LOW] malformed-link** — Link anchor text spans a sentence boundary ('backer. I've been impressed with Wikipedia'), indicating the link text was mis-bracketed during composition.
    - `[backer. I've been impressed with Wikipedia](https://www.wikipedia.org)`
    - Fix: Restrict the anchor text to 'Wikipedia' and end the previous sentence before the link.
  - **[LOW] malformed-link** — Anchor text crosses a sentence boundary, suggesting the link was authored incorrectly.
    - `[tackle this. Become a supporter today!](https://www.wikitribune.com/become-supporter/)`
    - Fix: Split into two sentences and hyperlink only 'Become a supporter today!'
  - **[MEDIUM] image-problem** — A bare URL appears on its own line under the section heading, likely an image or embed placeholder that didn't render as intended.
    - `## Now Reading 📚

http://www.amazon.com/dp/0451228731/?tag=thingelstad01-20`
    - Fix: Remove the stray URL or convert it into the proper image/link markup.
  - **[MEDIUM] image-problem** — Bare URL on its own line below the header looks like an unrendered image/embed artifact from the Tinyletter source.
    - `## Promotion 🎁

https://www.wikitribune.com`
    - Fix: Remove the orphaned URL or replace with the intended image/embed.
  - **[MEDIUM] image-problem** — A bare iTunes URL sits on its own line below the header, likely a leftover image placeholder that didn't migrate.
    - `## Featured App 📱

https://itunes.apple.com/us/app/forest-by-seekrtech/id866450515?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the stray URL line or replace with the intended app icon/image.
  - **[LOW] malformed-link** — The permalink slug contains a concatenated 'httpsenwikipediaorgwikikentbeck' indicating an inline URL was absorbed into the microblog post slug — a migration artifact visible in the URL.
    - `- “The” Kent Beck sharing a lightning talk at Chaos Community Day. [→](http://www.thingelstad.com/2017/11/10/the-kent-beckhttpsenwikipediaorgwikikentbeck.html)`
    - Fix: Verify the target URL is correct; if the slug is broken on the destination site, fix the link.
  - **[LOW] malformed-link** — Permalink slug contains 'nextdrafthttpsnextdraftcom' showing an absorbed URL — migration/authoring artifact.
    - `- Dave Pell’s NextDraft has become a true daily read for me, top to bottom. Recommended! 👍⭐️ [→](http://www.thingelstad.com/2017/11/06/dave-pells-nextdrafthttpsnextdraftcom.html)`
    - Fix: Confirm link target resolves; fix slug if broken.
  - **[LOW] malformed-link** — Slug contains 'workflowhttpsworkflowis' — absorbed inline URL, likely a broken permalink.
    - `- Got Workflow working with the Mailchimp API. Weekly Thing automation leveling up! 👍🏻 [→](http://www.thingelstad.com/2017/11/04/got-workflowhttpsworkflowis-working.html)`
    - Fix: Verify destination link resolves; correct if needed.

### #28 — Weekly Thing for November 18, 2017

- Era: Tinyletter
- Overall: Readable issue in era-normal Tinyletter style; minor migration-era linking quirks and one split sentence are the only notable issues.
  - **[MEDIUM] narrative-break** — A stray hard line break splits a sentence mid-clause, likely a migration artifact from the original email formatting.
    - `The last day was shadow, and it was rainy
and dreary the entire day.`
    - Fix: Remove the line break so the sentence flows on one line.
  - **[LOW] typo** — Extraneous word 'is' makes the sentence ungrammatical.
    - `Micro.blog is still requires an invite.`
    - Fix: Change to 'Micro.blog still requires an invite.'
  - **[LOW] malformed-link** — Each comma is awkwardly included inside a separate link's bracketed text, likely an artifact of how the list was linkified during migration.
    - `[a theme for each day: Squares](http://www.thingelstad.com/2017/11/11/193440.html) [, Tasty](http://www.thingelstad.com/2017/11/12/191007.html)`
    - Fix: Move commas outside the link brackets so punctuation renders as prose between links.

### #29 — Weekly Thing for November 25, 2017

- Era: Tinyletter
- Overall: Issue is readable and era-normal overall, but contains several malformed link anchors where brackets span sentence boundaries, two stray bare URLs likely from missing images, and a couple minor typos.
  - **[MEDIUM] malformed-link** — The link text is split across two separate links in a way that creates awkward prose — the sentence reads as two consecutive bracketed phrases rather than a natural sentence with embedded links.
    - `[Very good talk by John Allspaw](https://www.kitchensoap.com/about-me/) [from DOES17](https://events.itrevolution.com/us/)`
    - Fix: Restructure the sentence so the links are embedded naturally, e.g., 'Very good talk by [John Allspaw](...) from [DOES17](...) (DevOps Enterprise Summit)...'
  - **[MEDIUM] malformed-link** — Link text spans include punctuation and clause boundaries awkwardly, suggesting the links were authored with incorrect anchor boundaries.
    - `[a strange null set. Maciej Ceglowski](http://www.idlewords.com/about.htm) [, the owner of Pinboard](http://pinboard.in/)`
    - Fix: Rework so only the proper names are linked, e.g., 'a strange null set. [Maciej Ceglowski](...), the owner of [Pinboard](...),'
  - **[MEDIUM] malformed-link** — The link text incorrectly merges two distinct thoughts ('I don't use Uber' and the site name 'Without Bullshit') into a single anchor, crossing a sentence boundary.
    - `[I don't use Uber. Without Bullshit](https://withoutbullshit.com/blog/uber-data-breach-new-ceo-dara-khosrowshahi-makes-disappointingly-incomplete-statement)`
    - Fix: Split into two links or rewrite so only 'Without Bullshit' is the anchor text for the linked article.
  - **[MEDIUM] malformed-link** — The link text crosses a sentence boundary ('license.' ends one sentence and 'Donate to Creative Commons today!' is another), indicating a misplaced bracket.
    - `you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Move the opening bracket so only 'Donate to Creative Commons today!' is the anchor text.
  - **[LOW] image-problem** — A bare URL appears on its own line before the Promotion and Featured App sections, likely a placeholder where an image was intended but did not migrate.
    - `https://creativecommons.org`
    - Fix: Either remove the stray URL line or restore the intended image/logo.
  - **[LOW] image-problem** — A bare iTunes URL appears on its own line before the SleepTown heading, likely a placeholder where the app icon image was meant to display.
    - `https://itunes.apple.com/us/app/sleeptown/id1210251567?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Replace the bare URL with the intended app icon image or remove it.
  - **[LOW] typo** — 'take along' should be 'take long' — clear word error.
    - `This incident doesn't take along to start thinking`
    - Fix: Change 'take along' to 'take long'.
  - **[LOW] typo** — Missing apostrophe in 'Ive' (should be 'I've').
    - `Ive found it much simpler to insure that investment follows opportunity`
    - Fix: Change 'Ive' to 'I've'.

### #30 — Weekly Thing for December 2, 2017

- Era: Tinyletter
- Overall: Issue is readable and era-normal for Tinyletter, but has several links where the anchor text incorrectly spans sentence boundaries, likely from a migration or authoring quirk.
  - **[MEDIUM] malformed-link** — The link text incorrectly spans a sentence boundary, with the period landing inside the link text instead of after 'it'.
    - `I had no idea this existed and it’s great that it [does. Found it via this announcement](https://www.eff.org/deeplinks/2017/11/panopticlick-30)`
    - Fix: Restructure so only 'Found it via this announcement' (or similar phrase) is the link text.
  - **[MEDIUM] malformed-link** — Link text spans a sentence boundary, pulling 'hole for Apple. 😳' into the link; likely only 'Now patched' should be the link.
    - `This is a massively embarrassing security [hole for Apple. 😳 Now patched](https://support.apple.com/en-us/HT208315)`
    - Fix: Rewrite so the linked phrase is just 'Now patched' after the sentence ends.
  - **[MEDIUM] malformed-link** — Link anchor starts mid-phrase ('mapping tools (the other is iThoughts') and includes an unmatched parenthesis, indicating the link text was incorrectly delimited.
    - `New major release of one of my favorite mind [mapping tools (the other is iThoughts](https://www.toketaware.com/ithoughts-ios)`
    - Fix: Anchor only 'iThoughts' as the link text.
  - **[MEDIUM] malformed-link** — Link text awkwardly straddles a sentence boundary; the 1Password link should wrap just '1Password'.
    - `A new entrant into the Password (Secret) [Manager space. I've been a 1Password](https://1password.com) user for years`
    - Fix: Restructure so only '1Password' is the link anchor.
  - **[LOW] malformed-link** — The descriptive phrase is linked to MediaWiki's homepage rather than the skin itself, which appears to be a mis-scoped link anchor from migration.
    - `[Very impressive skin/template for MediaWiki](https://www.mediawiki.org/wiki/MediaWiki) [by Tom Hutchison](https://github.com/Hutchy68)`
    - Fix: Consider splitting so only 'MediaWiki' links to mediawiki.org and the descriptive text stands on its own.

### #31 — Weekly Thing for December 9, 2017

- Era: Tinyletter
- Overall: Readable overall, but the issue has a recurring pattern of misplaced markdown link brackets that swallow surrounding prose and punctuation, most visibly in the Disqus, Driving Change, and Macdrifter gift-list link blurbs.
  - **[HIGH] malformed-link** — The link bracket spans a sentence boundary, making the link text read as broken prose — the period inside the link text indicates the markdown link was authored incorrectly.
    - `I've tried doing PGP plugins before [and it is a nightmare. ProtonMail](https://protonmail.com) makes a very robust`
    - Fix: Rewrite so the link wraps only 'ProtonMail' (e.g., 'and it is a nightmare. [ProtonMail](https://protonmail.com) makes a very robust...').
  - **[HIGH] malformed-link** — Link text awkwardly includes 'Disqus widgets from loading using' when the URL points only to 1Blocker; the link boundaries are misplaced.
    - `Personally I block the [Disqus widgets from loading using 1Blocker](https://1blocker.com) .`
    - Fix: Scope the link to '1Blocker' only: 'block the Disqus widgets from loading using [1Blocker](https://1blocker.com).'
  - **[HIGH] malformed-link** — The third link bracket opens before a period and parenthesis, creating malformed link text '. (See my Driving Change' that includes punctuation as part of the anchor.
    - `New [Driving Change episode with Don Smithmier](https://www.linkedin.com/in/don-smithmier-36069b1/) [of Go Kart Labs](https://gokartlabs.com) [. (See my Driving Change](https://www.thingelstad.com/2017/driving-change/) episode.)`
    - Fix: Rewrite the sentence so each link wraps clean phrases, e.g., '...with [Don Smithmier](...) of [Go Kart Labs](...). (See my [Driving Change episode](...).)'
  - **[HIGH] malformed-link** — Link text spans sentence boundaries and swallows the list numbering, indicating markdown link brackets placed around the wrong text.
    - `I’m liking some of these holiday gift lists I’m seeing come through [my feeds lately. 1. Nintendo Switch](https://www.nintendo.com/switch/)`
    - Fix: Scope the link to 'Nintendo Switch' only and unbracket the surrounding prose and numbering.
  - **[HIGH] malformed-link** — Link text again spans unrelated prose and list items, with the URL pointing to AirPods but the anchor text starting with 'good idea. 3. I have AirPods'.
    - `The Magnetic Pencil Sleeve is a [good idea. 3. I have AirPods](https://www.apple.com/airpods/)`
    - Fix: Wrap only 'AirPods' in the link: 'I have [AirPods](https://www.apple.com/airpods/)...'.
  - **[HIGH] malformed-link** — Link text includes the leading sentence fragment 'I just got a' rather than only the product name, consistent with misplaced brackets throughout this paragraph.
    - `The Caps for Apple Pencil is also a good idea for folks that have more than one. 5. [I just got a ScanSnap iX500](http://www.fujitsu.com/us/products/computing/peripheral/scanners/scansnap/ix500/)`
    - Fix: Wrap only 'ScanSnap iX500' in the link.

### #32 — Weekly Thing for December 16, 2017

- Era: Tinyletter
- Overall: Readable and era-normal overall; main issues are an orphaned photo caption with no image and two bare URLs that appear to be migration artifacts from image or link references.
  - **[MEDIUM] image-problem** — This looks like a caption for an image (photo description with timestamp and location), but no image is present in the markdown.
    - `Giant Super Mario Bros. found in the Skyways of Downtown Minneapolis.

Dec 14, 2017 at 1:57 PM
801 Marquette Ave, Minneapolis MN`
    - Fix: Restore the referenced image or remove the orphaned caption.
  - **[LOW] image-problem** — A bare URL appears on its own line above the Freedom (TM) book heading, likely an image src or link that lost its markdown wrapping during migration.
    - `http://www.amazon.com/dp/0451231899/?tag=thingelstad01-20`
    - Fix: Convert to a proper image reference or remove the stray URL if it's a duplicate of the heading link.
  - **[LOW] image-problem** — A bare URL appears on its own line above the Minnestar paragraph, likely a stray image or link artifact from migration.
    - `https://minnestar.org`
    - Fix: Remove the bare URL or restore the intended image/link.
  - **[LOW] typo** — "there" should be "their" in this possessive construction.
    - `leverage the monopoly of Facebook in their company to achieve there ends`
    - Fix: Change "there ends" to "their ends".
  - **[LOW] typo** — "there" should be "their".
    - `Finally Microsoft Windows based admins can just natively ssh from there machines!`
    - Fix: Change "there machines" to "their machines".

### #33 — Weekly Thing for December 23, 2017

- Era: Tinyletter
- Overall: Readable and era-appropriate, but contains several malformed markdown links where anchor text crosses sentence boundaries, plus a few small typos worth correcting.
  - **[MEDIUM] malformed-link** — The markdown link bracket starts mid-sentence ('well.'), indicating the link text was selected incorrectly during migration/editing — the anchor text should be 'Wassail Tea', not 'well. A batch of Wassail Tea'.
    - `Christmas Day as [well. A batch of Wassail Tea](https://www.thingelstad.com/2004/wassail-tea/) is ready`
    - Fix: Re-scope the link to wrap only 'Wassail Tea' (or similar) rather than spanning across a sentence boundary.
  - **[MEDIUM] malformed-link** — Link text spans a sentence boundary ('phone. I use Forest'), a common migration artifact where the link bracket was misplaced.
    - `Disconnect [from the phone. I use Forest](https://www.forestapp.cc/en/)`
    - Fix: Restrict the anchor text to 'Forest' so the link reads naturally.
  - **[MEDIUM] malformed-link** — Multiple links in this issue have anchor text that crosses sentence/clause boundaries, a recurring malformed-link pattern from the Tinyletter era migration (also seen throughout the bulleted micro.blog list).
    - `Semisonic](http://semisonic.com) performing Feeling Strangely Fine [in it's entirety at First Ave](http://first-avenue.com)`
    - Fix: Tighten anchor-text spans so links wrap the relevant noun phrase rather than trailing clause fragments.
  - **[LOW] typo** — 'down my a' should be 'down by a'.
    - `Vindication for when I get taken down my a “man cold”!`
    - Fix: Change 'down my a' to 'down by a'.
  - **[LOW] typo** — 'might now know about' should be 'might not know about'.
    - `new applications that I might now know about.`
    - Fix: Change 'now' to 'not'.
  - **[LOW] typo** — Stray 'it' — the sentence reads ungrammatically ('and it the content').
    - `The web is a major part of our culture and it the content that we put on it is sadly ephemeral.`
    - Fix: Remove the extra 'it' so the sentence reads 'and the content that we put on it is sadly ephemeral.'
  - **[LOW] other** — A bare URL appears on its own line immediately before the linked title, suggesting a leftover from an embedded image/preview that didn't migrate.
    - `https://archive.org

[Internet Archive](https://archive.org)`
    - Fix: Remove the bare URL line or replace it with the intended image/embed.

### #34 — Weekly Thing for December 30, 2017

- Era: Tinyletter
- Overall: Readable but marred by several migration-era link-boundary bugs — most notably the Lowertown Line paragraph and the Internet Archive donate link — where anchor text captured sentence fragments instead of the intended phrases.
  - **[HIGH] malformed-link** — The link text boundaries are misplaced so prose like 'of artists I like.' and ', Cactus Blossoms' ended up inside the link anchors instead of being plain text with only the artist names linked.
    - `I just discovered this show while browsing through stuff on Apple TV and was excited to see episodes with a number [of artists I like. Jeremy Messersmith](http://www.tpt.org/the-lowertown-line/video/jeremy-messersmith-full-episode-the-lowertown-line-abkz5z/) [, Cactus Blossoms](http://www.tpt.org/the-lowertown-line/video/lowertown-line-cactus-blossoms/) [and Trampled by Turtles](http://www.tpt.org/the-lowertown-line/video/lowertown-line-trampled-turtles/)`
    - Fix: Rewrite so only the artist names are the linked text, e.g., '[Jeremy Messersmith](...), [Cactus Blossoms](...) and [Trampled by Turtles](...)'.
  - **[MEDIUM] malformed-link** — The anchor text 'this call out from Jaron Lanier' links to Lanier's Wikipedia page, but the intended article link (James Shelley post) is only referenced by the heading; the phrasing suggests the call-out itself should be linked.
    - `I love [this call out from Jaron Lanier](https://en.wikipedia.org/wiki/Jaron_Lanier)`
    - Fix: Split into two links: link 'Jaron Lanier' to Wikipedia and link 'this call out' to the Shelley article, or restructure so the referent is clear.
  - **[MEDIUM] malformed-link** — The link text incorrectly begins with 'history.' — a sentence fragment from the prior clause got pulled into the anchor text.
    - `The Internet Archive is working hard to capture that information and keep it for [history. Donate to Internet Archive today!](https://archive.org/donate/)`
    - Fix: Move the period after 'history' out of the link so only 'Donate to Internet Archive today!' is linked.
  - **[MEDIUM] narrative-break** — A hard line break splits 'as\npossible.' mid-sentence, likely a migration wrap artifact.
    - `your finger is there and your brain and eyes want to see the reaction with as close to no latency as
possible.`
    - Fix: Remove the stray newline so the sentence reads as a single line.
  - **[LOW] other** — A bare URL appears on its own line immediately before the Tetris book heading, which duplicates the heading's link and looks like a stray/leftover reference.
    - `http://www.amazon.com/dp/162672315X/?tag=thingelstad01-20`
    - Fix: Remove the bare URL line since the heading below already links the same destination.
  - **[LOW] other** — A bare URL precedes the Internet Archive paragraph redundantly; likely a leftover from composing the section.
    - `https://archive.org`
    - Fix: Delete the standalone URL line since the paragraph already links to archive.org.
  - **[LOW] malformed-link** — Throughout the bullet list, link text anchors awkwardly capture only sentence fragments (e.g., beginning mid-clause with 'all the…' or 'thing has a lot of character'), suggesting a migration anchor-splitting bug rather than deliberate link phrasing.
    - `Tammy and I have now watched [all the 2017 Best Picture nominees.](https://www.thingelstad.com/2017/12/29/watched-hacksaw-ridgehttpimdbcomtitlett.html)`
    - Fix: Re-anchor each bullet so the link wraps a meaningful noun phrase or the whole sentence, not a tail fragment.

### #35 — Weekly Thing for January 6, 2018

- Era: Tinyletter
- Overall: Readable but marred by numerous migration-era malformed markdown links where link text boundaries were mis-scoped mid-sentence, plus a couple of clear typos worth fixing.
  - **[HIGH] malformed-link** — The link text has been split across two separate markdown links with an errant apostrophe bracket, producing broken/awkward inline link rendering.
    - `I also kicked off the [new year by taking Shawn Blanc](https://shawnblanc.net) ['s Focus Course](https://thefocuscourse.com) .`
    - Fix: Rewrite as a single coherent sentence with properly scoped link text, e.g., 'taking [Shawn Blanc's Focus Course](https://thefocuscourse.com)'.
  - **[HIGH] malformed-link** — Link text boundaries are mis-placed — 'Prometheus. Multiple parts Metrics and Labels' should not all be one link; the sentence structure is garbled.
    - `Interesting series of blog posts with a solid introduction to [Prometheus. Multiple parts Metrics and Labels](https://pierrevincent.github.io/2017/12/prometheus-blog-series-part-1-metrics-and-labels/)`
    - Fix: Restructure so 'Prometheus' is its own brief link or plain word and each part label links correctly.
  - **[MEDIUM] malformed-link** — A markdown mailto link lost its brackets during migration, leaving raw '(mailto:...)' text visible to readers.
    - `simply forward it to sp@mnesty.com (mailto:sp@mnesty.com) ,`
    - Fix: Restore as [sp@mnesty.com](mailto:sp@mnesty.com).
  - **[HIGH] malformed-link** — Link text boundaries are awkwardly split so the sentence reads strangely — 'power company provides and Luke Samaha' is mis-linked to Luke's LinkedIn.
    - `I [shared my frustration with the reporting](https://www.thingelstad.com/2017/12/29/i-want-to.html) that my [power company provides and Luke Samaha](https://www.linkedin.com/in/lukesamaha/) [pointed me to](https://twitter.com/LukeSamaha/status/947135160323059712) Sense.`
    - Fix: Re-scope link text so 'Luke Samaha' links to LinkedIn and 'pointed me to' links to the tweet, separate from the power-company clause.
  - **[MEDIUM] malformed-link** — Link text incorrectly encompasses 'this. After reading the' rather than just 'Checklist Manifesto'.
    - `Like seeing [this. After reading the Checklist Manifesto](https://en.wikipedia.org/wiki/The_Checklist_Manifesto)`
    - Fix: Narrow the link text to just 'Checklist Manifesto'.
  - **[MEDIUM] malformed-link** — Link text spans arbitrary mid-sentence phrases rather than the product names, a migration artifact pattern.
    - `Minor nitpick that [this is using Github Flavored Markdown](https://github.github.com/gfm/) for [the checklists and I think Taskpaper](https://www.taskpaper.com)`
    - Fix: Scope links to 'Github Flavored Markdown' and 'Taskpaper' only.
  - **[MEDIUM] typo** — 'cookies' should be 'cooker' — clear typo given the sous vide context mentioned later with the Joule.
    - `I'm eager to put my new sous vide cookies to work`
    - Fix: Change 'cookies' to 'cooker'.
  - **[LOW] typo** — 'Ad' should be 'Add' — clear typo at the start of the sentence.
    - `Ad this to the list of reasons`
    - Fix: Change 'Ad' to 'Add'.
  - **[MEDIUM] narrative-break** — Sentence appears to be missing a negation ('can't be') or otherwise contradicts the surrounding critique of the lava-lamp approach.
    - `This one is a great read and a good photo but it leaves me feeling like it can be a very good answer.`
    - Fix: Clarify the author's intent, likely 'can't be a very good answer'.
  - **[LOW] malformed-link** — Link text 'was to be a Creative Commons' is an awkward mid-phrase link likely migrated incorrectly.
    - `The idea of that project [was to be a Creative Commons](https://creativecommons.org) licensed collection`
    - Fix: Narrow link to 'Creative Commons' only.

### #36 — Weekly Thing for January 13, 2018

- Era: Tinyletter
- Overall: Readable issue, but it has multiple link-bracket placement errors in the Microblog list and elsewhere (clear migration artifacts), a couple of bare-URL stubs, and two obvious typos that deserve cleanup.
  - **[MEDIUM] typo** — 'think' should be 'thick' — clear typo.
    - `The fog was very think all day on the Gulf Coast in Florida.`
    - Fix: Change 'think' to 'thick'.
  - **[MEDIUM] narrative-break** — The sentence is garbled — it reads as if two phrasings were merged ('Incredibly moving speech that I hadn't heard ... the speech ... before').
    - `Incredibly moving speech that I hadn't heard [the speech from David Foster Wallace](https://en.wikipedia.org/wiki/David_Foster_Wallace) before.`
    - Fix: Rework to something like 'Incredibly moving speech. I hadn't heard [the speech from David Foster Wallace] before.'
  - **[HIGH] malformed-link** — The link anchor text incorrectly includes 'me a bit when' — the bracket placement is wrong and the link text should just be 'Julian Assange'.
    - `It pains [me a bit when Julian Assange](https://en.wikipedia.org/wiki/Julian_Assange) and Snowden are bucketed together.`
    - Fix: Rewrite as 'It pains me a bit when [Julian Assange](...) and Snowden are bucketed together.'
  - **[HIGH] malformed-link** — Link bracket starts mid-sentence at '[years.' — anchor text incorrectly spans a sentence boundary.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the opening bracket so the link text reads 'Donate to Let's Encrypt today!' only.
  - **[HIGH] malformed-link** — Link anchor text awkwardly starts mid-sentence; likely a migration artifact where the link should wrap a cleaner phrase.
    - `- Family movie night [watching Leap! Everyone liked it. 🎬](https://www.thingelstad.com/2018/01/12/family-movie-night.html)`
    - Fix: Adjust bracket placement so the link text is a coherent phrase (e.g., the whole sentence).
  - **[HIGH] malformed-link** — Same pattern — link anchor begins mid-sentence, apparent migration artifact.
    - `- A smartphone filled with social apps is the [physical manifestation of Buddhist monkey mind.](https://www.thingelstad.com/2018/01/12/a-smartphone-filled.html)`
    - Fix: Rework so the link wraps the whole thought or a cleaner phrase.
  - **[HIGH] malformed-link** — Link bracket splits the compound word/phrase 'forward facing camera' awkwardly.
    - `I continue to see more people covering the camera in their laptops. How come nobody covers the forward [facing camera on their mobile phone?](https://www.thingelstad.com/2018/01/12/i-continue-to.html)`
    - Fix: Move bracket to wrap a coherent phrase.
  - **[MEDIUM] malformed-link** — Anchor text starts mid-sentence at '[audiobook.'
    - `Enjoying 10% Happier on [audiobook. Approachable introduction to mindfulness. 📚](https://www.thingelstad.com/2018/01/10/014252.html)`
    - Fix: Adjust link placement to wrap a natural phrase.
  - **[MEDIUM] malformed-link** — Anchor begins mid-sentence at '[mind…'.
    - `Tammy grabbed this great picture of me quieting my [mind… 😊 "Mind like water…" 💧](https://www.thingelstad.com/2018/01/06/mind-like-water.html)`
    - Fix: Adjust bracket placement to wrap a coherent phrase.
  - **[MEDIUM] malformed-link** — Anchor begins mid-sentence at '[photo'.
    - `Fun with [photo booth at Pizzeria Lola! 📷](https://www.thingelstad.com/2018/01/06/fun-with-photo.html)`
    - Fix: Move bracket so the link wraps the whole sentence.
  - **[LOW] other** — Bare URL appears on its own line immediately before the linked book heading; likely a leftover from a template/migration.
    - `http://www.amazon.com/dp/0062265423/?tag=thingelstad01-20`
    - Fix: Remove the duplicate bare URL line.
  - **[LOW] other** — Bare URL on its own line before the paragraph; appears to be a migration leftover.
    - `https://letsencrypt.org`
    - Fix: Remove the bare URL line.
  - **[LOW] other** — Bare URL on its own line before the Headspace heading, a migration artifact.
    - `https://itunes.apple.com/us/app/headspace-meditation/id493145008?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the duplicate bare URL line.
  - **[LOW] typo** — 'to be focus' should be 'to be focused' (or 'to focus').
    - `Plus it was great to be focus entirely on the work that I was doing there.`
    - Fix: Change 'to be focus' to 'to be focused'.

### #37 — Weekly Thing for January 20, 2018

- Era: Tinyletter
- Overall: Readable issue but contains a clearly unreplaced 'ToDo' placeholder and two bare URL lines that appear to be migration artifacts from missing images.
  - **[HIGH] migration-artifact** — This is an author's placeholder note that was never replaced with actual welcome content before publication.
    - `ToDo: Fill in with welcome.`
    - Fix: Remove the ToDo line or replace it with the intended welcome text.
  - **[MEDIUM] image-problem** — A bare URL appears on its own line, likely a migration artifact from an image or embed that didn't come through.
    - `https://archive.org`
    - Fix: Replace with the intended image or remove the stray URL line.
  - **[MEDIUM] image-problem** — Another bare URL on its own line appears to be a migration artifact where an app icon or image was expected.
    - `https://itunes.apple.com/us/app/rise-nutrition-weight-loss-coach/id794278760?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Replace with the intended image/embed or remove the stray URL.
  - **[LOW] narrative-break** — Garbled clause: 'and it the content that we put on it' reads as a word-order error from editing.
    - `The web is a major part of our culture and it the content that we put on it is sadly ephemeral.`
    - Fix: Change to 'and the content that we put on it is sadly ephemeral.'
  - **[LOW] malformed-link** — The link text refers to a specific article but points to Schneier's homepage rather than the article (the article link appears to be the section heading URL instead).
    - `[Compelling article by Bruce Schneier](https://www.schneier.com)`
    - Fix: Verify and point the link to the actual article URL.

### #38 — Weekly Thing for January 27, 2018

- Era: Tinyletter
- Overall: Readable and era-normal overall; main issues are several links with anchor text that spans sentence/punctuation boundaries (a recurring migration artifact) plus a couple of minor typos.
  - **[LOW] typo** — 'Analaysis' is a clear misspelling of 'Analysis' (especially notable since the very next section uses the correct spelling).
    - `Analaysis of my 2017 calendar.`
    - Fix: Change 'Analaysis' to 'Analysis'.
  - **[MEDIUM] malformed-link** — The link anchor text starts mid-phrase ('or 2nd grade on a TI-99/4A'), suggesting the bracket placement is off — likely should wrap only the model name.
    - `Myself, I started coding when I was in 1st [or 2nd grade on a TI-99/4A](https://en.wikipedia.org/wiki/Texas_Instruments_TI-99/4A) using BASIC. I fall in the "5 to 10" bucket here.`
    - Fix: Rework link so anchor text is 'TI-99/4A' rather than a mid-sentence fragment.
  - **[MEDIUM] malformed-link** — Link anchor text spans a sentence boundary and includes a leading comma in the second link — awkward bracket placement from migration.
    - `in Python. Clearly Guido van Rossum](https://en.wikipedia.org/wiki/Guido_van_Rossum) [, the "Benevolent Dictator For Life"](https://en.wikipedia.org/wiki/Benevolent_dictator_for_life)`
    - Fix: Restructure so anchor text cleanly wraps the name and title rather than crossing punctuation boundaries.
  - **[MEDIUM] malformed-link** — Stray space and trailing possessive ''s thesis here' outside the link indicate malformed anchor placement.
    - `[I concur with DHH](https://en.wikipedia.org/wiki/David_Heinemeier_Hansson) 's thesis here.`
    - Fix: Rephrase so the link wraps 'DHH' and the possessive reads naturally without a leading space.
  - **[MEDIUM] malformed-link** — Anchor text starts mid-sentence ('gaming over recent years. Specifically Carcassonne') and a trailing ' .' sits orphaned — bracket placement is broken.
    - `Specifically Carcassonne](https://en.wikipedia.org/wiki/Carcassonne) [and Ticket to Ride](https://www.daysofwonder.com/tickettoride/en/) .`
    - Fix: Restructure to link just 'Carcassonne' and 'Ticket to Ride' cleanly within the sentence.
  - **[MEDIUM] malformed-link** — Link anchor text crosses sentence boundaries, suggesting brackets were placed incorrectly during composition/migration.
    - `I became a [backer. I've been impressed with Wikipedia](https://www.wikipedia.org) [and am excited about Jimmy Wales](http://jimmywales.com)`
    - Fix: Rework anchor text so each link wraps its appropriate noun (e.g., 'Wikipedia', 'Jimmy Wales') without spanning sentences.
  - **[LOW] typo** — 'Bon Thompson' should be 'Ben Thompson' — the Stratechery author referenced earlier in the same issue.
    - `My opinion on the real threat to Facebook is perfectly captured in Bon Thompson's writeup here:`
    - Fix: Change 'Bon Thompson' to 'Ben Thompson'.

### #39 — Weekly Thing for February 3, 2018

- Era: Tinyletter
- Overall: Readable Tinyletter-era issue, but two orphaned bare URLs suggest lost images and the final microblog list has consistently awkward link boundaries.
  - **[MEDIUM] image-problem** — A bare Amazon URL appears on its own line, likely a broken/missing image reference (the book cover) that lost its markdown image syntax during migration.
    - `http://www.amazon.com/dp/1439195455/?tag=thingelstad01-20

### [Why Buddhism is True: The Science and Philosophy of Meditation and Enlightenment](http://www.amazon.com/dp/1439195455/?tag=thingelstad01-20)`
    - Fix: Restore the image markdown (e.g., ![Book cover](...)) or remove the orphaned URL line.
  - **[MEDIUM] image-problem** — A bare archive.org URL on its own line before the Internet Archive section suggests a missing image (likely the IA logo) that lost its markdown image syntax.
    - `https://archive.org

[Internet Archive](https://archive.org)`
    - Fix: Restore the image markdown or remove the stray URL line.
  - **[MEDIUM] malformed-link** — Link text brackets start mid-sentence rather than wrapping the whole phrase, a consistent pattern in this microblog list suggesting migration mangled the link boundaries.
    - `- The Cactus Blossoms at [the Turf Club. So good! 🎶](https://www.thingelstad.com/2018/01/29/the-cactus-blossomshttpthecactusblossomscom.html)`
    - Fix: Rewrap each bullet so the link text covers the full sentence or a sensible phrase rather than beginning in the middle.
  - **[LOW] header-error** — An H2 is used for an author byline attached to the book title, creating an odd heading in the TOC between content sections.
    - `## by Robert Wright`
    - Fix: Demote to bold text or plain prose under the book title.
  - **[LOW] typo** — Quoted passage contains a duplicated 'are' ('Managers that ... are, according to our analysis, are 2.2 times'), though this may be verbatim from the source.
    - `according to our analysis, are 2.2 times more likely`
    - Fix: Verify against the source and remove the duplicated 'are' if it's a transcription error.

### #40 — Weekly Thing for February 10, 2018

- Era: Tinyletter
- Overall: Readable issue, but several inline links in the EFF, GraphQL, and EFF-donation paragraphs have mis-split anchor text, and two stray bare URLs appear above section headings as migration artifacts.
  - **[MEDIUM] malformed-link** — Link text boundaries are clearly misplaced — 'this article' should link to the declaration, not be grouped with Barlow's name, and comma-led link text fragments indicate broken link splitting from migration.
    - `I'm shocked that I had never read [this article. Sadly John Perry Barlow](https://en.wikipedia.org/wiki/John_Perry_Barlow) [, the founder of the EFF](https://www.eff.org)`
    - Fix: Restructure so 'this article' links to the EFF declaration and Barlow's name links cleanly to his Wikipedia page without leading commas in anchor text.
  - **[MEDIUM] malformed-link** — Link text is fragmented across multiple anchors with leading commas and awkward splits, a classic migration artifact where inline links were mis-bracketed.
    - `Good [introduction to the problem that GraphQL](http://graphql.org) is [solving and the history of RPC](https://en.wikipedia.org/wiki/Remote_procedure_call) [, SOAP](https://en.wikipedia.org/wiki/SOAP) [and REST](https://en.wikipedia.org/wiki/Representational_state_transfer)`
    - Fix: Rework so each linked term (GraphQL, RPC, SOAP, REST) is a clean single-word anchor rather than spanning prose with leading punctuation.
  - **[MEDIUM] malformed-link** — Anchor text begins with 'and' and spans awkward prose boundaries, indicating bracket placement lost during migration.
    - `[recently launched solutions like Privacy Badger](https://www.eff.org/privacybadger) [and the critically important Let's Encrypt](https://letsencrypt.org)`
    - Fix: Tighten anchors to just 'Privacy Badger' and 'Let's Encrypt' rather than wrapping surrounding prose.
  - **[LOW] other** — Bare URL appears on its own line immediately before the linked title, suggesting a leftover template/preview artifact from the source format.
    - `https://www.eff.org

[The Electronic Frontier Foundation](https://www.eff.org)`
    - Fix: Remove the stray bare URL line above the EFF section heading.
  - **[LOW] other** — Bare URL sits above the OpenTerm H3 heading, mirroring a migration artifact where the link preview was not stripped.
    - `https://itunes.apple.com/us/app/openterm/id1323205755?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com

### [OpenTerm]`
    - Fix: Delete the duplicate bare URL line above the OpenTerm heading.
  - **[LOW] typo** — 'company's' should be plural 'companies', not a possessive.
    - `Managers spend a lot of time in 1:1 meetings, and company's as a whole`
    - Fix: Change 'company's' to 'companies'.

### #41 — Weekly Thing for February 17, 2018

- Era: Tinyletter
- Overall: Readable but notably marred by repeated malformed-link boundaries (anchors swallowing sentence fragments) throughout the Software, Web, and Apps sections, plus a stray unclosed italic asterisk and an orphan footnote digit.
  - **[HIGH] malformed-link** — Link text was incorrectly sliced so prose words are embedded inside link anchors, producing malformed link phrasing that reads oddly.
    - `[I like what Brent Simmons](http://inessential.com/) is doing with this project. I’m a big user [of feed readers. I use Feedbin](https://feedbin.com) [along ReadKit](http://readkitapp.com) [and Unread](https://itunes.apple.com/us/app/unread-rss-reader/id1252376153?mt=8) .`
    - Fix: Rewrite so only the product names are linked, e.g., 'I use [Feedbin](...) along with [ReadKit](...) and [Unread](...)'.
  - **[HIGH] malformed-link** — The link anchor captures a full sentence plus 'AMP' instead of just 'AMP', a migration-style bracket/URL misalignment.
    - `Ugh. 🤦‍♂️ [This is a horrible idea. AMP](https://www.ampproject.org) was a bad idea`
    - Fix: Shorten link text to just 'AMP' so the sentence reads naturally.
  - **[HIGH] malformed-link** — Anchor text incorrectly includes the leading 'of' preposition; the link target is just 'Jack-in-the-box'.
    - `put all sorts [of digital Jack In The Box](https://en.wikipedia.org/wiki/Jack-in-the-box) traps`
    - Fix: Limit the link anchor to 'Jack In The Box'.
  - **[HIGH] malformed-link** — The link anchor spans across a sentence boundary, mixing 'Let's Encrypt' with an imperative call-to-action, and points to EFF's donate page for both.
    - `My sites are secured with free certificates from [Let's Encrypt. You should support this](https://supporters.eff.org/donate) , even if you aren't publishing content.`
    - Fix: Split into two links: 'Let's Encrypt' → letsencrypt.org and 'support this' → EFF donate URL.
  - **[HIGH] malformed-link** — Link anchors incorrectly include punctuation and sentence fragments like '. I use Headspace' and 'and Streaks', indicating botched link boundaries.
    - `reminds me of my article [on apps that make you better](https://www.thingelstad.com/2017/what-apps-make-you-better/) [. I use Headspace](https://itunes.apple.com/us/app/headspace-meditation/id493145008?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com) [and Streaks](https://itunes.apple.com/us/app/streaks/id963034692?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com)`
    - Fix: Restrict anchors to just the app names ('Headspace', 'Streaks') and clean up the sentence punctuation.
  - **[MEDIUM] malformed-link** — Anchor text incorrectly includes the word 'Notable that' instead of just the person's name.
    - `[Notable that Tim Berners-Lee](https://en.wikipedia.org/wiki/Tim_Berners-Lee) is involved.`
    - Fix: Link only 'Tim Berners-Lee'.
  - **[MEDIUM] narrative-break** — A stray asterisk begins italic markdown that is never closed, likely breaking rendering or leaving a literal asterisk.
    - `The web has *50 million more secure HTTPS endpoints now`
    - Fix: Remove the stray `*` or close the emphasis properly.
  - **[MEDIUM] malformed-link** — Micropost link anchors consistently include trailing sentence fragments and punctuation, a known migration artifact from this era.
    - `- Now I sort of want one of [these Loog Pro Electric guitars. 😊](https://www.thingelstad.com/2018/02/12/now-i-sort.html)`
    - Fix: Consider normalizing anchors to the post text without awkward mid-sentence breaks (editorial; minor).
  - **[LOW] header-error** — This H3 sits under no H2 section (appears after a horizontal rule in the sponsor/app-of-the-week area), making it an orphan heading relative to the section TOC.
    - `### [OmniOutliner 3](https://itunes.apple.com/us/app/omnioutliner-3/id1174101450?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com)`
    - Fix: Either add a section H2 (e.g., 'App of the Week') or demote/reformat to match surrounding plain-text blocks.
  - **[LOW] other** — A stray '2' appears where a footnote marker was likely intended, now reading as 'meetings2'.
    - `Let’s forget for a moment why there are so many meetings2 and focus`
    - Fix: Remove the orphaned '2' or restore the footnote reference.

### #42 — Weekly Thing #42 / Feb 24, 2018

- Era: MailChimp
- Overall: Issue is generally readable but has a structural header problem under 'Links 📌' (subsections are H2 instead of H3) and a couple of stray bare URLs in the Promotion/App sections that look like template artifacts.
  - **[MEDIUM] header-error** — The 'Links 📌' H2 has no content and is immediately followed by another H2 ('Social Media'), which appears to be a subsection heading that should be H3 under Links.
    - `## Links 📌

## Social Media`
    - Fix: Either merge 'Links 📌' into the subsequent section headings or demote 'Social Media', 'Tech', 'Interview', 'Culture', etc. to H3 under the Links H2.
  - **[LOW] malformed-link** — A bare URL appears as a standalone line under the Promotion section with no markdown formatting, suggesting a leftover or mis-rendered link preview.
    - `## Promotion 🎁

https://letsencrypt.org`
    - Fix: Remove the stray bare URL line or convert it to a proper titled link/image.
  - **[LOW] malformed-link** — A bare tracking URL appears as a standalone line above the properly-formatted H3 link, likely a migration/template artifact.
    - `## App 📱

https://itunes.apple.com/us/app/altos-odyssey/id1182456409?mt=8&uo=4&at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the standalone bare URL since the titled link immediately follows.

### #43 — Weekly Thing #43 / Mar 3, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has one clearly truncated sentence ('Nea') before a blockquote, a malformed link in the Business section, and a header hierarchy problem where the 'Links' subsections are all H2 instead of H3.
  - **[HIGH] narrative-break** — The sentence ends with a truncated word 'Nea' — likely 'Nearly' or similar, cut off mid-word before the blockquote.
    - `Warren Buffett's shareholder letter is always a great read. Nea`
    - Fix: Restore the complete sentence introducing the blockquote (e.g., 'Nearly all of the following comes directly from the letter:').
  - **[MEDIUM] header-error** — The 'Links' section uses H2, then immediately nests what should be sub-sections (Security, Software, Business, etc.) also as H2, flattening the hierarchy and breaking the TOC.
    - `## Links 📌

## Security`
    - Fix: Demote 'Security', 'Software', 'Business', 'Programming', 'Web', 'Self-Improvement', 'Privacy', 'Sports', 'Culture', 'Tech', 'Productivity' to H3 under '## Links 📌'.
  - **[HIGH] malformed-link** — The link text contains a stray '[Thinking inside a large box]' with brackets and a semicolon, suggesting broken markdown/migration artifact in the anchor text.
    - `Flavors of Engineering Management [· [Thinking inside a large box];](http://blog.benjamin-encz.de/post/flavors-of-engineering-management/)`
    - Fix: Rewrite as a clean link: '[Flavors of Engineering Management · Thinking inside a large box](http://blog.benjamin-encz.de/post/flavors-of-engineering-management/)'.
  - **[LOW] typo** — 'there' should be 'their'.
    - `many people turn there nose to it`
    - Fix: Change 'there nose' to 'their nose'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `If your working on systems`
    - Fix: Change 'If your working' to 'If you're working'.
  - **[LOW] other** — Era-canonical section name is 'Give Back 🎁'; 'Promotion' is a deviation but readable.
    - `## Promotion 🎁`
    - Fix: Consider normalizing to 'Give Back 🎁' for consistency with other MailChimp-era issues.

### #44 — Weekly Thing #44 / Mar 10, 2018

- Era: MailChimp
- Overall: Readable but substantially marred by a systemic migration artifact in which nearly every H3 link title in this issue has its leading words outside the link brackets; these should be reformatted as proper H3 linked titles.
  - **[HIGH] malformed-link** — The link title was split during migration — only the trailing portion is inside the link brackets while the leading title text sits as plain prose, instead of being a proper H3 link.
    - `Why Are There Few Women in Tech? [Watch a Recruiting Session | WIRED](https://www.wired.com/story/why-are-there-few-women-in-tech-watch-a-recruiting-session/)`
    - Fix: Reformat as `### [Why Are There Few Women in Tech? Watch a Recruiting Session | WIRED](https://...)` so the full title is the linked heading.
  - **[HIGH] malformed-link** — The link anchor text is split — the paper title starts outside the brackets, leaving only the tail phrase linked.
    - `I'd like to go back and read the original paper Puncturing the pipeline: Do technology [companies alienate women in recruiting sessions?](http://journals.sagepub.com/doi/abs/10.1177/0306312718756766)`
    - Fix: Wrap the full title in the link: `[Puncturing the pipeline: Do technology companies alienate women in recruiting sessions?](...)`.
  - **[HIGH] malformed-link** — Link title is split across plain text and bracketed link, so the H3 heading is malformed.
    - `Deep Thinking In The Age of [Distraction – The Startup – Medium](https://medium.com/swlh/deep-thinking-in-the-age-of-distraction-f7cf765b2762)`
    - Fix: Reformat as `### [Deep Thinking In The Age of Distraction – The Startup – Medium](...)`.
  - **[HIGH] malformed-link** — Link title is split; only the tail of the article title is inside the brackets.
    - `Why am I unhappy? A new study [explains Americas unhappiness epidemic — Quartz](https://qz.com/1190151/why-am-i-unhappy-a-new-study-explains-americas-unhappiness-epidemic/)`
    - Fix: Wrap the full title inside the link brackets and make it an H3.
  - **[HIGH] malformed-link** — Split link title — migration artifact where the beginning of the title sits outside the link.
    - `What I Talk [About When I Talk About Platforms](https://martinfowler.com/articles/talk-about-platforms.html)`
    - Fix: Reformat as `### [What I Talk About When I Talk About Platforms](...)`.
  - **[HIGH] malformed-link** — Link title split; the word 'Teevity' is outside the link brackets.
    - `Teevity [- Cloud costs analytics - Home](https://www.teevity.com/)`
    - Fix: Make the full title the link: `[Teevity - Cloud costs analytics - Home](...)`.
  - **[HIGH] malformed-link** — Link anchor split across plain text and brackets.
    - `What it’s like to be a [developer at … – Increment: Development](https://increment.com/development/what-its-like-to-be-a-developer-at/)`
    - Fix: Wrap the full title inside the brackets.
  - **[HIGH] malformed-link** — Link anchor split; only trailing portion of title is linked.
    - `Bad iPhone notches are happening to [good Android phones - The Verge](https://www.theverge.com/2018/3/4/17077458/iphone-design-clones-mwc-2018)`
    - Fix: Include the full title inside the brackets.
  - **[HIGH] malformed-link** — Link title is split across plain text and brackets.
    - `Amazon won't sell Nest [products from Google - Business Insider](http://www.businessinsider.com/amazon-wont-sell-nest-products-from-google-2018-3?IR=T)`
    - Fix: Place the full title inside the link brackets.
  - **[HIGH] malformed-link** — Split link title; leading portion of title is outside the link.
    - `The Indispensable Document for the [Modern Manager | First Round Review](http://firstround.com/review/the-indispensable-document-for-the-modern-manager/)`
    - Fix: Wrap the full title inside the link brackets.
  - **[HIGH] malformed-link** — Split link title.
    - `The Role of Luck in Life Success Is Far Greater Than We [Realized - Scientific American Blog Network](https://blogs.scientificamerican.com/beautiful-minds/the-role-of-luck-in-life-success-is-far-greater-than-we-realized/)`
    - Fix: Wrap the full title inside the link brackets.
  - **[HIGH] malformed-link** — Split link title.
    - `Uber and Lyft drivers' median hourly wage is just $3.37, report [finds | Technology | The Guardian](https://www.theguardian.com/technology/2018/mar/01/uber-lyft-driver-wages-median-report)`
    - Fix: Wrap the full title inside the link brackets.
  - **[MEDIUM] header-error** — '## Links 📌' is immediately followed by another H2 '## Culture' with no content between, and subsequent subsections (Tech, Business) are also H2 — these should likely be H3 subsections under Links, or the parent 'Links' header should be removed.
    - `## Links 📌

## Culture`
    - Fix: Either demote Culture/Tech/Business to H3 under Links, or remove the empty '## Links 📌' header.
  - **[LOW] typo** — 'thing' should be 'think'.
    - `This made [me thing of Fooled by Randomness]`
    - Fix: Change 'thing' to 'think'.
  - **[LOW] typo** — 'hand't' should be 'hadn't'.
    - `I hand't heard of this app`
    - Fix: Fix to 'hadn't'.
  - **[LOW] typo** — 'due' should be 'do' in the idiom 'make do'.
    - `had to due with this Wired writeup`
    - Fix: Change 'due' to 'do'.
  - **[MEDIUM] malformed-link** — Link text runs across a sentence boundary, making 'years.' part of the link anchor — clearly a split-title migration artifact.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Restrict the link to 'Donate to Let's Encrypt today!' so the prior sentence reads normally.

### #45 — Weekly Thing #45 / Mar 17, 2018

- Era: MailChimp
- Overall: Readable issue but unusually riddled with mis-anchored Markdown links where link text starts mid-title, plus several small typos; an editorial pass to re-wrap link anchors is the main concern.
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence ('learned along the way') because the linked phrase was truncated; the whole title should be the link text.
    - `How Atlassian moved Jira and Confluence users to Amazon Web Services, and what it [learned along the way – GeekWire](https://www.geekwire.com/2018/atlassian-moved-jira-confluence-users-amazon-web-services-learned-along-way/)`
    - Fix: Wrap the entire article title in the link: [How Atlassian moved Jira and Confluence users to Amazon Web Services, and what it learned along the way – GeekWire](...).
  - **[MEDIUM] malformed-link** — The link text spans a sentence boundary ('cloud. Hat tip to Peter Zaballos'), indicating the link anchor was placed incorrectly during migration.
    - `It also sounds like they evolved the solution to work better in the [cloud. Hat tip to Peter Zaballos](https://meaningfulfailure.com) for the link.`
    - Fix: Restrict the link to 'Peter Zaballos' so the sentence reads naturally.
  - **[MEDIUM] malformed-link** — Only the tail of the title is linked; the link text should include the full article title.
    - `ACME v2 and Wildcard Certificate Support is Live - Issuance [Policy - Let's Encrypt Community Support](https://community.letsencrypt.org/t/acme-v2-and-wildcard-certificate-support-is-live/55579)`
    - Fix: Make the entire title the link text.
  - **[MEDIUM] malformed-link** — Link anchor starts partway through the title, leaving 'AWS Documentation is Now Open Source' as plain text.
    - `AWS Documentation is Now Open Source [and on GitHub —AWS News Blog](https://aws.amazon.com/blogs/aws/aws-documentation-is-now-open-source-and-on-github/)`
    - Fix: Wrap the whole title as the link text.
  - **[MEDIUM] malformed-link** — Link text begins mid-title; full title should be anchored.
    - `TwitRSS.me - rss of twitter [user feeds by screenscraping with perl](https://www.twitrss.me/)`
    - Fix: Wrap the full site title in the link.
  - **[MEDIUM] malformed-link** — Product name 'Deckset for Mac' is outside the link; likely the entire title should be linked.
    - `Deckset for Mac: [Presentations from Markdown in No Time](https://www.decksetapp.com/)`
    - Fix: Include 'Deckset for Mac:' inside the link text.
  - **[MEDIUM] malformed-link** — Link text spans a clause break ('him was at John Riedl's funeral'); the anchor should be just the referent phrase.
    - `Sadly the last time I saw [him was at John Riedl's funeral](https://www.thingelstad.com/2013/goodbye-to-my-friend-john-riedl/)`
    - Fix: Limit the link to 'John Riedl's funeral'.
  - **[MEDIUM] malformed-link** — Link begins mid-title; the whole headline should be the link text.
    - `Stephen Hawking, one of the world’s [great scientists, has died - Physics](https://www.economist.com/news/obituary/21738688-groundbreaking-physicist-was-76-stephen-hawking-one-worlds-great-scientists-has)`
    - Fix: Wrap the full headline in the link.
  - **[MEDIUM] malformed-link** — Only a fragment of the headline is linked.
    - `Toys R Us to close all 800 of its [U.S. stores - The Washington Post](https://www.washingtonpost.com/news/business/wp/2018/03/14/toys-r-us-to-close-all-800-of-its-u-s-stores/)`
    - Fix: Wrap the entire headline in the link text.
  - **[MEDIUM] malformed-link** — Product name is outside the link; the whole tagline/title should be the link text.
    - `SankeyMATIC (BETA): [A Sankey diagram builder for everyone](http://sankeymatic.com/)`
    - Fix: Include 'SankeyMATIC (BETA):' inside the link.
  - **[MEDIUM] malformed-link** — Link text starts partway through the title.
    - `How to Balance Your [Media Diet – ART + marketing](https://artplusmarketing.com/how-to-balance-your-media-diet-a2140c0311ec)`
    - Fix: Wrap the entire title in the link.
  - **[MEDIUM] malformed-link** — Link text crosses sentence boundaries joining 'and am excited about Jimmy Wales' with the Wikipedia/Wales links; anchors are misaligned with referents.
    - `I've been impressed with Wikipedia](https://www.wikipedia.org) [and am excited about Jimmy Wales`
    - Fix: Re-anchor: link 'Wikipedia' to wikipedia.org and 'Jimmy Wales' to jimmywales.com separately.
  - **[MEDIUM] malformed-link** — The link text spans a sentence break ('tackle this. Become a supporter today!'), a migration artifact.
    - `I am very curious to see how they realize these objectives. I've previously thought about how news can be reinvented. I focused more on the open source model instead of wiki, but either way I feel like a fundamental rethink is possible! Let's see how they [tackle this. Become a supporter today!](https://www.wikitribune.com/become-supporter/)`
    - Fix: Limit the anchor to 'Become a supporter today!'.
  - **[LOW] header-error** — In this era the canonical section is 'Notable Links 📌'; 'Links 📌' is followed immediately by H2 subsections ('## Tech', '## Product', etc.) at the same level instead of nested H3s, flattening the TOC.
    - `## Links 📌`
    - Fix: Rename to 'Notable Links 📌' and demote subsequent category headings to H3.
  - **[LOW] typo** — 'stabalize' is a clear misspelling of 'stabilize'.
    - `It took until Thursday for me to stabalize back into something resembling a normal routine.`
    - Fix: Change 'stabalize' to 'stabilize'.
  - **[LOW] typo** — 'write' should be 'right'.
    - `This is absolutely the write way to think of being on a technology team.`
    - Fix: Replace 'write' with 'right'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `If your curious what the typical software developer looks like`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — 'to' should be 'too'.
    - `It looks like that in person to.`
    - Fix: Change 'to' to 'too'.
  - **[LOW] typo** — 'getting reading' should be 'getting ready'.
    - `🥧 #TeamSPS getting reading to celebrate π day!`
    - Fix: Change 'reading' to 'ready'.
  - **[LOW] typo** — 'find madly' appears to be a garbled phrase (likely 'fondly remember').
    - `For people who find madly remember HyperCard`
    - Fix: Replace 'find madly remember' with 'fondly remember'.

### #46 — Weekly Thing #46 / Mar 24, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has a recurring pattern where link titles were split so only the tail of the title is hyperlinked — a cosmetic migration artifact worth cleaning up.
  - **[MEDIUM] malformed-link** — This appears under a link titled 'A New Way to Work • furbo.org' but the commentary's bracketed link text reads as if the link title was split across the heading line and the following paragraph, a pattern consistent with broken link-title migration elsewhere in the issue.
    - `[I use Linea Sketch](https://linea-app.com) and this is a great dive into using tech in a very analog, and creative, way.`
    - Fix: Verify intended commentary text; likely should read plainly ('I use Linea Sketch and this is a great dive...') with the link inline rather than as the lead phrase.
  - **[LOW] malformed-link** — Across this issue link titles were migrated such that only a trailing fragment became the hyperlink (e.g., 'List: What Your Favorite Website Says [About You - McSweeney's...]', 'The Only Privacy Policy That [Matters – ...]'), leaving the leading words unlinked — a visible migration artifact pattern.
    - `Standard Notes | [A Simple And Private Notes App](https://standardnotes.org/)`
    - Fix: Re-link the full titles so the entire headline is the hyperlink rather than only the latter portion.

### #47 — Weekly Thing #47 / Mar 31, 2018

- Era: MailChimp
- Overall: Issue is generally readable and era-normal, with a couple of minor migration artifacts (bare URLs preceding link blocks) and an awkward '## Links' orphan header structure.
  - **[LOW] other** — The '## Links' section header is immediately followed by another H2 '## Web' with no content between them, and subsequent subsections (Photography, Security, Tech, etc.) are also H2, making 'Links' appear as an orphan heading rather than a parent section — likely these subsections should be H3.
    - `## Links 📌

## Web`
    - Fix: Either promote 'Links' to remain as the section header and demote Web/Photography/Security/etc. to H3, or remove the redundant '## Links 📌' header.
  - **[MEDIUM] malformed-link** — A bare Amazon URL appears on its own line directly above the linked book title, which looks like a leftover image/thumbnail reference from migration.
    - `http://www.amazon.com/dp/1501144316/?tag=thingelstad01-20

### [Why We Sleep: Unlocking the Power of Sleep and Dreams](http://www.amazon.com/dp/1501144316/?tag=thingelstad01-20)`
    - Fix: Remove the stray bare URL line above the book heading.
  - **[MEDIUM] malformed-link** — A bare URL sits alone above the paragraph, likely a migration artifact from an image/logo reference that didn't carry over.
    - `## Promotion 🎁

https://creativecommons.org

[Creative Commons](https://creativecommons.org)`
    - Fix: Remove the stray bare 'https://creativecommons.org' line.
  - **[LOW] typo** — 'their' should be 'they're' (this is a quote from Steve Jobs, but still a clear typo in transcription).
    - `Privacy means people know what their signing up for`
    - Fix: Change 'their' to 'they're'.

### #48 — Weekly Thing #48 / Apr 7, 2018

- Era: MailChimp
- Overall: Readable and coherent, but the entire 'Links 📌' section is structurally flat — category headers are H2 instead of H3 subsections — and numerous link titles are split between plain prose and bracketed text, which degrades the TOC and reading experience.
  - **[MEDIUM] header-error** — The '## Links 📌' section header is immediately followed by another H2 '## Security' with no content between, and all subsequent category headers (Security, Social Media, Photography, etc.) are H2 when they should logically be H3 subsections under Links.
    - `## Links 📌

## Security`
    - Fix: Demote the category headers (Security, Social Media, Photography, Culture, Food, Software, Tech, Media, Games, People, Research, Funny, Business, Web) to H3 so they nest under '## Links 📌'.
  - **[LOW] typo** — 'Intagram' is misspelled; should be 'Instagram'.
    - `I won't use Intagram as their Terms of Service`
    - Fix: Correct 'Intagram' to 'Instagram'.
  - **[LOW] typo** — 'Great with by' appears to be a garbled phrase, likely intended to be 'Great wit by' or 'Written by'.
    - `Great with by David Hussman`
    - Fix: Rewrite to something like 'Great wit by David Hussman and friends.'
  - **[LOW] typo** — Duplicated 'you your' — a clear editing error.
    - `This is why you your personal engagement as a leader is so important.`
    - Fix: Remove the stray 'you' so it reads 'This is why your personal engagement as a leader is so important.'
  - **[MEDIUM] malformed-link** — The link title is split — the first half of the headline is plain prose and only the tail is inside the link brackets, a pattern repeated throughout the issue that reads awkwardly.
    - `Trump's Campaign Said It Was Better [at Facebook. Facebook Agrees - Bloomberg](https://www.bloomberg.com/news/articles/2018-04-03/trump-s-campaign-said-it-was-better-at-facebook-facebook-agrees)`
    - Fix: Wrap the full headline inside the markdown link text (this pattern recurs across many link titles and should be normalized).

### #49 — Weekly Thing #49 / Apr 14, 2018

- Era: MailChimp
- Overall: Readable but marred by a systemic migration artifact: nearly every link title across the issue is split so the link text starts mid-title, and the Links section uses H2 for subcategories instead of H3, flattening the intended hierarchy.
  - **[HIGH] malformed-link** — The sentence has been split into two separate links mid-phrase, a migration artifact where a single link was broken into two awkward fragments.
    - `Tammy and [I went to see The Decemberists](http://www.decemberists.com) [playing at the Palace Theatre](http://palacestpaul.com) last weekend.`
    - Fix: Rewrite as a natural sentence with properly placed single links, e.g., 'Tammy and I went to see [The Decemberists](...) playing at the [Palace Theatre](...) last weekend.'
  - **[HIGH] malformed-link** — Title text starts outside the link and only the tail portion is hyperlinked — a recurring migration artifact where the full title should be the link text.
    - `Highlights from CodeDay 2018 Minneapolis & Toronto [at SPS Commerce | SPS Commerce](https://www.spscommerce.com/blog/codeday-minneapolis-sps-commerce-spsa/)`
    - Fix: Make the whole title the link text: '[Highlights from CodeDay 2018 Minneapolis & Toronto at SPS Commerce | SPS Commerce](url)'.
  - **[HIGH] malformed-link** — Only part of the title is linked; the link text should encompass the full title, typical of the broken MailChimp-to-markdown conversion pattern.
    - `Stream | API for [Scalable News Feeds & Activity Streams](https://getstream.io/)`
    - Fix: Wrap the entire title in the link: '[Stream | API for Scalable News Feeds & Activity Streams](...)'.
  - **[HIGH] malformed-link** — Link text begins mid-title; the full H3-style title should be the link.
    - `The best text editor [for macOS – The Sweet Setup](https://thesweetsetup.com/apps/best-text-editor-macos/)`
    - Fix: Make the full title the link: '[The best text editor for macOS – The Sweet Setup](...)'.
  - **[HIGH] malformed-link** — Link only covers the tail of the title; migration artifact splitting the title.
    - `Instagram Looks [Like Facebook’s Best Hope - Bloomberg](https://www.bloomberg.com/news/features/2018-04-10/instagram-looks-like-facebook-s-best-hope)`
    - Fix: Link the entire title.
  - **[HIGH] malformed-link** — Link text is missing the 'Johnny Cash:' prefix of the title.
    - `Johnny Cash: [American Recordings Album Review | Pitchfork](https://pitchfork.com/reviews/albums/johnny-cash-american-recordings/)`
    - Fix: Include the full title inside the link brackets.
  - **[HIGH] malformed-link** — Link text starts in the middle of the title, and the opening bracket falls inside parentheses, creating a visibly broken title.
    - `The Decemberists - Full concert (4/7/18 at Palace Theatre [in Saint Paul, MN) - YouTube](https://www.youtube.com/watch?v=P4Jz3tMddw4)`
    - Fix: Rewrite so the entire title is the link text.
  - **[HIGH] malformed-link** — Only the latter portion of the title is linked; a title-splitting migration artifact.
    - `Amazon spent nearly $23 billion [on R&D last year - Recode](https://www.recode.net/2018/4/9/17204004/amazon-research-development-rd)`
    - Fix: Wrap the full title as the link text.
  - **[HIGH] malformed-link** — 'JS' is orphaned outside the link; the entire title should be the link.
    - `JS [- Blog - GraphQL Best Practices](https://jsjaspreet.com/blog/graphql-best-practices)`
    - Fix: Link the whole title, e.g., '[JS - Blog - GraphQL Best Practices](...)'.
  - **[HIGH] malformed-link** — Title is split so only the tail is linked.
    - `Don’t Give Away Historic Details [About Yourself — Krebs on Security](https://krebsonsecurity.com/2018/04/dont-give-away-historic-details-about-yourself/)`
    - Fix: Make the full title the link text.
  - **[HIGH] malformed-link** — 'The' is orphaned outside the link text.
    - `The [Nintendo Switch's Parental Controls Are Amazing](https://kotaku.com/the-nintendo-switchs-parental-controls-are-amazing-1824301547)`
    - Fix: Include 'The' inside the link brackets.
  - **[HIGH] malformed-link** — Only the latter part of the title is linked.
    - `Back to Basics: Coffee Brewing Methods [& Gear — Tools and Toys](http://toolsandtoys.net/guides/back-to-basics-coffee-brewing-methods-and-gear/)`
    - Fix: Wrap the entire title inside the link brackets.
  - **[MEDIUM] malformed-link** — Link text begins mid-sentence ('license.' belongs to the prior clause), producing awkward grammar and an oddly scoped link.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Restructure so the link text is a natural phrase, e.g., '...under a Creative Commons license. [Donate to Creative Commons today!](...)'.
  - **[HIGH] header-error** — Under the canonical era structure, section sub-categories (Business, Software, Social Media, etc.) and individual link titles should be H3, but here subcategories are H2, making 'Links 📌' effectively empty and flattening the TOC hierarchy.
    - `## Links 📌

## Business`
    - Fix: Demote the category headings ('Business', 'Software', 'Social Media', 'Indieweb', 'Music', 'Tech', 'Productivity', 'Security', 'Games', 'Coffee') to H3, and make the individual link titles proper H3 link lines.
  - **[MEDIUM] narrative-break** — The Photo section has a geotag/caption but no actual image present, leaving a dangling reference to a photo that never appears.
    - `Apr 7, 2018 at 9:26 PM
17 7th Pl W, Saint Paul, MN`
    - Fix: Embed the photo referenced by the caption or remove the orphaned caption lines.
  - **[MEDIUM] image-problem** — The 'Photo' section contains no image — only a textual caption — so readers of the archive see a heading promising a photo with nothing to view.
    - `## Photo 📷`
    - Fix: Include the actual photo markdown image tag, or rename/remove the section if the image can't be recovered.
  - **[LOW] typo** — 'studioes' is a clear misspelling of 'studios'.
    - `I've generally found the versions of Tetris from the big game studioes to be pretty bad.`
    - Fix: Change 'studioes' to 'studios'.

### #50 — Weekly Thing #50 / Apr 21, 2018

- Era: MailChimp
- Overall: Readable but repeatedly marred by split-anchor markdown links where article titles extend outside the [] brackets; most are medium-severity rendering oddities rather than broken links.
  - **[MEDIUM] malformed-link** — The link text begins mid-title; 'Peter Stern: A Birthday' is outside the link, making the rendered link read oddly.
    - `Peter Stern: A Birthday [Note for my Daughter | LinkedIn](https://www.linkedin.com/pulse/dear-amina-peter-stern/)`
    - Fix: Wrap the full title in the link: [Peter Stern: A Birthday Note for my Daughter | LinkedIn](...).
  - **[MEDIUM] malformed-link** — Link text is split; 'How to Write a' sits outside the link anchor.
    - `How to Write a [Thank-You Note - The Morning News](https://themorningnews.org/article/how-to-write-a-thank-you-note)`
    - Fix: Include the full title inside the brackets.
  - **[MEDIUM] malformed-link** — The article title is broken by the link syntax, leaving most of the headline outside the anchor.
    - `Majority of teens worry about school shootings, and so do [most parents | Pew Research Center](http://www.pewresearch.org/fact-tank/2018/04/18/a-majority-of-u-s-teens-fear-a-shooting-could-happen-at-their-school-and-most-parents-share-their-concern/)`
    - Fix: Put the full headline inside the link brackets.
  - **[MEDIUM] malformed-link** — Link title is fractured — half of the headline is outside the anchor.
    - `Titus, the Netflix container [management platform, is now open source](https://medium.com/netflix-techblog/titus-the-netflix-container-management-platform-is-now-open-source-f868c9fb5436)`
    - Fix: Wrap the entire title in the link brackets.
  - **[MEDIUM] malformed-link** — Title is split across the anchor, leaving 'How I Use: Search' outside the link.
    - `How I Use: Search [in Mail on macOS — MyProductiveMac](http://www.myproductivemac.com/blog/how-i-use-search-in-mail-on-macos1742018)`
    - Fix: Move the whole title inside the link.
  - **[MEDIUM] malformed-link** — Headline broken across anchor boundary.
    - `Facebook Uses Artificial Intelligence to Predict Your Future [Actions for Advertisers, Says Confidential Document](https://theintercept.com/2018/04/13/facebook-advertising-data-artificial-intelligence-ai/)`
    - Fix: Enclose the full headline in the link.
  - **[MEDIUM] malformed-link** — Link text starts mid-sentence; 'Opinion | Don't Fix Facebook. Replace' is outside the anchor.
    - `Opinion | Don’t Fix Facebook. Replace [It. - The New York Times](https://www.nytimes.com/2018/04/03/opinion/facebook-fix-replace.html)`
    - Fix: Include the full headline inside the link brackets.
  - **[MEDIUM] malformed-link** — Two consecutive links awkwardly split sentences; the second link text starts with '. Wu wrote...' which reads as broken prose.
    - `This article caught my attention [because the author is Tim Wu](https://en.wikipedia.org/wiki/Tim_Wu) [. Wu wrote The Master Switch](https://www.amazon.com/Master-Switch-Rise-Information-Empires/dp/0307390993/)`
    - Fix: Restructure so only 'Tim Wu' and 'The Master Switch' are the anchor texts.
  - **[MEDIUM] malformed-link** — Title split across the anchor.
    - `The Diary of a Settler [of Catan - McSweeney’s Internet Tendency](https://www.mcsweeneys.net/articles/the-diary-of-a-settler-of-catan)`
    - Fix: Wrap the full title in the link.
  - **[MEDIUM] malformed-link** — Title split across the anchor.
    - `How to Use Static Type Checking in Python [3.6 – Adam Geitgey – Medium](https://medium.com/@ageitgey/learn-how-to-use-static-type-checking-in-python-3-6-in-10-minutes-12c86d72677b)`
    - Fix: Include the full title in the link.
  - **[MEDIUM] malformed-link** — Title fragmented; 'Drafts' sits outside the anchor.
    - `Drafts [5: The MacStories Review – MacStories](https://www.macstories.net/reviews/drafts-5-the-macstories-review/)`
    - Fix: Wrap the full title in brackets.
  - **[MEDIUM] malformed-link** — Headline split across anchor boundary.
    - `How to give feedback effectively: A guide [for managers — Quartz at Work](https://work.qz.com/1238966/how-to-give-feedback-more-effectively/)`
    - Fix: Wrap the entire headline inside the link.
  - **[LOW] malformed-link** — Breadcrumbs titles are repeatedly split across anchor boundaries, making the list items read oddly.
    - `Richard Stallman, RMS, [on Privacy, Data, and Free Software](http://nymag.com/selectall/2018/04/richard-stallman-rms-on-privacy-data-and-free-software.html)`
    - Fix: Reformat each breadcrumb with the full title inside the link brackets.
  - **[MEDIUM] malformed-link** — Multiple links in this paragraph start mid-phrase, producing awkward anchor texts like 'projects in the world, including Wikipedia' and 'internet property. Donate to Wikimedia today!'.
    - `[The Wikimedia Foundation, Inc.](https://wikimediafoundation.org/wiki/Home) is a nonprofit charitable organization dedicated to encouraging the growth, development and distribution of free, multilingual, educational content, and to providing the full content of these wiki-based projects to the public free of charge. The Wikimedia Foundation operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Rewrite so only the proper named phrases ('Wikipedia', 'top-ten internet property', 'Donate to Wikimedia today') are link anchors.
  - **[LOW] dangling-reference** — A bare URL sits under the Promotion heading with no context line before the paragraph — likely a stray artifact from a template.
    - `## Promotion 🎁

https://wikimediafoundation.org/wiki/Home`
    - Fix: Remove the bare URL or integrate it into the paragraph that follows.
  - **[LOW] dangling-reference** — Bare URL appears under the App heading before the H3 — reads like leftover template content.
    - `## App 📱

https://itunes.apple.com/us/app/id1365531024?at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the bare URL line since the H3 link below covers the same destination.

### #51 — Weekly Thing #51 / Apr 28, 2018

- Era: MailChimp
- Overall: Issue reads cleanly overall; the main concern is a recurring pattern of link anchor text starting mid-phrase (a migration artifact from the source formatter), most notably in the Promotion section.
  - **[LOW] other** — Link titles in this era are normally H3 headings; here and throughout the Links/Breadcrumbs sections the titles are plain paragraphs rather than `### [Title](url)`, which is a migration artifact from the original format but is era-consistent for some MailChimp issues.
    - `Jaron Lanier Interview on [What Went Wrong With the Internet](http://nymag.com/selectall/2018/04/jaron-lanier-interview-on-what-went-wrong-with-the-internet.html)`
    - Fix: Leave as-is if era-normal, or convert link titles to H3 headings for consistency with the template.
  - **[MEDIUM] malformed-link** — The link anchor text spans mid-sentence in an awkward way suggesting the original link placement was lost in migration; the phrase 'became a backer' links to Wikipedia rather than to a backer page.
    - `I became a [backer. I've been impressed with Wikipedia](https://www.wikipedia.org) [and am excited about Jimmy Wales](http://jimmywales.com)`
    - Fix: Rework the link anchors so 'backer' points to the Wikitribune backer page and 'Wikipedia' / 'Jimmy Wales' are separate, correctly-scoped links.
  - **[LOW] malformed-link** — Link anchors start mid-phrase ('Zoo this summer — Son Volt') suggesting the link boundaries were shifted during migration.
    - `Got great tickets to the two shows I wanted to see at the Music in the [Zoo this summer — Son Volt](http://suemclean.com/events/son-volt/) [and Michael Franti & Spearhead](http://suemclean.com/events/michael-franti-spearhead/)`
    - Fix: Rescope anchors so 'Son Volt' and 'Michael Franti & Spearhead' are the linked phrases.

### #52 — Weekly Thing #52 / May 5, 2018

- Era: MailChimp
- Overall: Readable but marred by a systemic link-formatting bug where brackets start mid-title throughout Featured/Links/Breadcrumbs sections, plus a few non-canonical section headings.
  - **[HIGH] malformed-link** — The link bracket starts mid-title rather than wrapping the whole headline, so 'The Numbers' appears as plain text preceding the link — a pattern repeated throughout the issue from a migration/automation glitch.
    - `The Numbers [Behind WeWork's Growing Empire - Bloomberg](https://www.bloomberg.com/news/articles/2018-04-24/the-18-billion-rent-bill-the-numbers-behind-wework-s-empire)`
    - Fix: Reformat so the entire article title is wrapped in the markdown link brackets (e.g., [The Numbers Behind WeWork's Growing Empire - Bloomberg](...)).
  - **[HIGH] malformed-link** — Link bracket begins partway through the title, leaving 'Inside Nintendo's secretive creative' as unlinked prose.
    - `Inside Nintendo's secretive creative [process | Games | The Guardian](https://www.theguardian.com/games/2018/apr/25/nintendo-interview-secret-innovation-lab-ideas-working)`
    - Fix: Wrap the complete title in the link brackets.
  - **[HIGH] malformed-link** — Bracket starts mid-title; the leading portion is unlinked.
    - `Stack Overflow Isn't Very Welcoming. It's Time for That [to Change. - Stack Overflow Blog](https://stackoverflow.blog/2018/04/26/stack-overflow-isnt-very-welcoming-its-time-for-that-to-change/)`
    - Fix: Wrap the full title in the link.
  - **[MEDIUM] header-error** — Per era conventions the Featured section heading should be 'Featured Links 🏅'; this also affects 'Links 📌' (should be 'Notable Links 📌') and 'Breadcrumbs 🍞' (should be 'Yet More Links 🍞') — inconsistent with canonical TOC.
    - `## Featured 🏅`
    - Fix: Rename section headings to the canonical 'Featured Links 🏅', 'Notable Links 📌', and 'Yet More Links 🍞'.
  - **[HIGH] malformed-link** — The link bracket captures prose ('to date. I personally use Enrypt.me') that shouldn't be the link text; also contains a typo 'Enrypt.me' instead of 'Encrypt.me'.
    - `This is the most comprehensive and researched view of VPN services I've seen [to date. I personally use Enrypt.me](https://encrypt.me)`
    - Fix: Restructure the sentence so only 'Encrypt.me' is the linked text, and fix the spelling.
  - **[MEDIUM] malformed-link** — The link wraps a sentence fragment starting mid-word ('years. Donate...'), producing awkward rendered link text.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Link only 'Donate to Let's Encrypt today!' and leave the preceding prose outside the link.
  - **[LOW] header-error** — Canonical heading is 'My Weekly Photo 📷'; this issue uses a shortened form inconsistent with the era's TOC.
    - `## Photo 📷`
    - Fix: Rename to 'My Weekly Photo 📷' for consistency.
  - **[LOW] typo** — 'it's' should be 'its' (possessive).
    - `It was impressive to see the falls at it's strongest.`
    - Fix: Change 'it's' to 'its'.
  - **[MEDIUM] malformed-link** — Nested brackets inside markdown link text will break the link parser in many renderers, leaving '[video]' visible and the link broken — this matches the static audit finding.
    - `[Incident Management at Netflix Velocity [video]](https://www.infoq.com/presentations/netflix-incident-management)`
    - Fix: Escape the inner brackets or rewrite as 'Incident Management at Netflix Velocity (video)'.

### #53 — Weekly Thing #53 / May 12, 2018

- Era: MailChimp
- Overall: Issue is generally readable and era-normal, but the Give Back section has clearly malformed link boundaries and several sections carry stray bare URLs beneath their H2 headings that should be cleaned up.
  - **[MEDIUM] malformed-link** — Link anchor text is broken awkwardly mid-sentence (e.g., '[projects in the world, including Wikipedia]' and '[internet property. Donate to Wikimedia today!]'), suggesting the link boundaries were misplaced during migration.
    - `[The Wikimedia Foundation, Inc.](https://wikimediafoundation.org/wiki/Home) is a nonprofit charitable organization dedicated to encouraging the growth, development and distribution of free, multilingual, educational content, and to providing the full content of these wiki-based projects to the public free of charge. The Wikimedia Foundation operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Re-scope the link anchors to the intended phrases (e.g., 'Wikipedia' and 'Donate to Wikimedia today!') so the surrounding prose reads naturally.
  - **[LOW] other** — A bare URL appears immediately under the section heading before the H3 title link, which duplicates the link and renders as stray text.
    - `## Now Reading 📚

http://www.amazon.com/dp/1250103509/?tag=thingelstad01-20`
    - Fix: Remove the bare URL line; the H3 link below already points to the same resource.
  - **[LOW] other** — Same pattern: a raw URL appears below the section heading before the H3 link that follows, producing visible duplicate link text.
    - `## Highlighted iOS App 📱

https://itunes.apple.com/us/app/id1164801111?at=1001lxyE&ct=thingelstad_com`
    - Fix: Delete the standalone bare URL line under the heading.
  - **[LOW] other** — Bare URL appears between the section heading and the paragraph, displaying as stray text.
    - `## Give Back 🎁

https://wikimediafoundation.org/wiki/Home`
    - Fix: Remove the duplicate bare URL.

### #54 — Weekly Thing #54 / May 19, 2018

- Era: MailChimp
- Overall: Content is readable, but the Yet More Links and Microposts sections contain many mis-bracketed links (migration artifact from auto-linked imports), including one awkward split in the Give Back paragraph.
  - **[MEDIUM] malformed-link** — The link bracket started mid-sentence at '[years.' so the linked anchor text awkwardly includes 'years.' — the bracket was misplaced.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the opening bracket so only 'Donate to Let's Encrypt today!' is the linked text.
  - **[MEDIUM] malformed-link** — Link brackets start mid-title so the anchor text is 'Laurel Meme Comes From | WIRED' instead of the full article title — an artifact of link-extraction in this era's Yet More Links section.
    - `- Where the Yanny and [Laurel Meme Comes From | WIRED](https://www.wired.com/story/yanny-and-laurel-true-history/) www.wired.com`
    - Fix: Rebracket to link the full title 'Where the Yanny and Laurel Meme Comes From | WIRED'.
  - **[LOW] malformed-link** — Anchor text excludes the leading 'Your' — consistent pattern of mis-bracketed titles in this section.
    - `- Your [serverless Raspberry Pi cluster with Docker](https://blog.alexellis.io/your-serverless-raspberry-pi-cluster/) blog.alexellis.io`
    - Fix: Extend bracket to include 'Your' in the link text.
  - **[LOW] malformed-link** — Anchor text duplicates 'Microsoft Devices Blog' and starts with a stray dash, indicating a scraping/migration artifact.
    - `- Meet Surface Hub 2 [- Microsoft Devices BlogMicrosoft Devices Blog](https://blogs.windows.com/devices/2018/05/15/meet-surface-hub-2/) blogs.windows.com`
    - Fix: Clean anchor text to 'Meet Surface Hub 2 - Microsoft Devices Blog'.
  - **[LOW] malformed-link** — Title 'On null' is outside the link bracket so only part of the article title is clickable.
    - `- On null | [Structure and Interpretation of Computer Programmers](https://www.sicpers.info/2018/05/on-null/) www.sicpers.info`
    - Fix: Extend bracket to include 'On null | '.
  - **[LOW] malformed-link** — Leading 'Professor Frisby's' is outside the link bracket, splitting the title.
    - `- Professor Frisby's [Mostly Adequate Guide to Functional Programming](https://mostly-adequate.gitbooks.io/mostly-adequate-guide/) mostly-adequate.gitbooks.io`
    - Fix: Extend bracket to encompass the full title.
  - **[LOW] malformed-link** — Link bracket starts mid-title, splitting 'Everything you need to know!'.
    - `- Nintendo Switch Online service: Everything [you need to know! | iMore](https://www.imore.com/nintendo-switch-online-everything-you-need-know) www.imore.com`
    - Fix: Rebracket to include the full title in the anchor.
  - **[LOW] malformed-link** — Title is split with 'Scripting News: The' outside the link bracket.
    - `- Scripting News: The [Internet is going the wrong way](http://scripting.com/2018/05/10/133513.html) scripting.com`
    - Fix: Extend bracket to cover full title.
  - **[LOW] malformed-link** — Anchor text starts mid-sentence; article title is split across link and plain text.
    - `- Boston Dynamics’ robots are learning how to run outside [and navigate autonomously - The Verge](https://www.theverge.com/circuitbreaker/2018/5/10/17341400/boston-dynamics-atlas-spotmini-robots-videos-autonomous-navigation) www.theverge.com`
    - Fix: Rebracket so the full title is the anchor.
  - **[LOW] malformed-link** — 'Pyre' is outside the link bracket.
    - `- Pyre [· A performant typechecker for Python](https://pyre-check.org/) pyre-check.org`
    - Fix: Extend bracket to include 'Pyre'.
  - **[LOW] malformed-link** — Link bracket starts mid-word in the article title, splitting the headline awkwardly.
    - `- Social media copies gambling methods 'to create psychological [cravings' | Technology | The Guardian](https://www.theguardian.com/technology/2018/may/08/social-media-copies-gambling-methods-to-create-psychological-cravings) www.theguardian.com`
    - Fix: Rebracket so the whole headline is the anchor text.
  - **[MEDIUM] malformed-link** — The quoted sentence is shattered across four separate links, making the prose read awkwardly — a migration/import artifact from micro.blog auto-linking.
    - `[“At SPS it might be Kube](https://kubernetes.io) [or Kubb](https://en.wikipedia.org/wiki/Kubb) [!” Kelly Hamm](https://www.linkedin.com/in/hammkelly/) [at SumoLogic](https://www.sumologic.com) knows #TeamSPS — and thanks for the Kubb set!`
    - Fix: Rework so the quote reads cleanly with links attached to appropriate words rather than splitting the sentence.
  - **[MEDIUM] malformed-link** — Commas and spacing are inside the link brackets producing visually odd linked punctuation like ', Kotlin' and ', and GraphQL'.
    - `[Evolutionary architecture](http://evolutionaryarchitecture.com) [, Kotlin](https://kotlinlang.org) [, and GraphQL](http://graphql.org) .`
    - Fix: Move punctuation outside the link brackets.
  - **[LOW] malformed-link** — Opening paren is inside the link and closing paren is orphaned outside, a clear migration artifact.
    - `Hanging [out with the amazing @bridgetkromhout (website](https://bridgetkromhout.com) )`
    - Fix: Rework the link so '(website)' sits properly around the anchor.
  - **[LOW] typo** — 'sites' should be 'cites'.
    - `I don't use Google Photos for the same reasons Om sites in this article.`
    - Fix: Change 'sites' to 'cites'.

### #55 — Weekly Thing #55 / May 26, 2018

- Era: MailChimp
- Overall: Readable overall, but the issue contains several migration artifacts — orphan bare URLs under section headers, a duplicated photo caption, and one broken markdown link in the Give Back section — that a copy-editor should clean up.
  - **[HIGH] malformed-link** — The markdown link bracket opens mid-sentence at "[license." which renders as link text "license. Donate to Creative Commons today!" — the intended link text was likely just "Donate to Creative Commons today!"
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Move the opening bracket so the link text reads only "Donate to Creative Commons today!" (e.g., "...under a Creative Commons license. [Donate to Creative Commons today!](https://creativecommons.org/donate/)").
  - **[MEDIUM] dangling-reference** — A bare URL appears directly below the section header, duplicating the linked title that follows — likely a migration artifact from an image/link field that wasn't rendered.
    - `## Now Reading 📚

http://www.amazon.com/dp/0062316095/?tag=thingelstad01-20`
    - Fix: Remove the stray bare URL line under the "Now Reading" heading.
  - **[MEDIUM] dangling-reference** — A bare URL appears immediately under the section header, a migration artifact where an image or logo link field didn't render.
    - `## Give Back 🎁

https://creativecommons.org`
    - Fix: Remove the orphan bare URL line.
  - **[MEDIUM] dangling-reference** — Another orphan bare URL appears directly under the section heading, duplicating the link below it — a migration artifact.
    - `## Highlighted iOS App 📱

https://itunes.apple.com/us/app/id1134727588?at=1001lxyE&ct=thingelstad_com`
    - Fix: Remove the stray bare URL line under the "Highlighted iOS App" heading.
  - **[MEDIUM] narrative-break** — The photo caption is duplicated three times (alt text, caption, then repeated again with metadata), suggesting a migration artifact.
    - `Minnesota Twins playing the Detroit Tigers at Target Field. ⚾️

Minnesota Twins playing the Detroit Tigers at Target Field.
May 22, 2018 at 8:17 PM`
    - Fix: Remove the duplicated caption line so only one caption plus the date/location metadata remains.
  - **[MEDIUM] malformed-link** — The link title contains stray empty quote marks (“ ”) — likely a failed title/alt extraction during migration.
    - `- [GDPR —xkcd.com “ ”](https://xkcd.com/1998/) xkcd.com`
    - Fix: Clean up the link title to "GDPR — xkcd.com" and remove the empty smart-quote pair.
  - **[LOW] typo** — "deliveres" is a misspelling of "delivers".
    - `[Abby Wambach](https://en.wikipedia.org/wiki/Abby_Wambach) deliveres an amazing`
    - Fix: Correct "deliveres" to "delivers".

### #56 — Weekly Thing #56 / Jun 2, 2018

- Era: MailChimp
- Overall: Readable issue but contains two clear problems: an unfilled 'ToDo: Photo caption here.' placeholder around the weekly photo and an orphan H3 because 'My Blog Posts ✍️' is not formatted as an H2.
  - **[HIGH] header-error** — The 'My Blog Posts ✍️' section heading is plain text instead of an H2, leaving the following H3 orphaned (matches the static audit finding).
    - `My Blog Posts ✍️

### [Humble Leadership Profile](https://www.thingelstad.com/2018/humble-leadership-profile/)`
    - Fix: Prefix 'My Blog Posts ✍️' with '## ' to make it a proper H2 section header.
  - **[HIGH] image-problem** — The image alt text and a trailing line both contain the placeholder 'ToDo: Photo caption here.' which was never replaced before publishing.
    - `![ToDo: Photo caption here.](https://files.thingelstad.com/weekly-thing/56/cover.jpg)`
    - Fix: Replace the 'ToDo: Photo caption here.' alt text and stray line with the intended caption (e.g., the baseball description).
  - **[MEDIUM] migration-artifact** — A stray 'ToDo: Photo caption here.' line appears in body text below the image, a clear unfilled template placeholder.
    - `ToDo: Photo caption here.
May 31, 2018 at 6:56 PM`
    - Fix: Remove the 'ToDo: Photo caption here.' line from the body.
  - **[MEDIUM] malformed-link** — Throughout 'Yet More Links', link titles are split so the first half is plain text and only the tail is linked; this is a migration artifact that makes titles look broken.
    - `- Microsoft has leapfrogged Alphabet to become the world's [third most valuable company — Quartz](https://qz.com/1291819/microsoft-has-leapfrogged-alphabet-to-become-the-worlds-third-most-valuable-company/) qz.com`
    - Fix: Rewrap each bullet so the full title is inside the link brackets (and drop the trailing bare domain).
  - **[LOW] typo** — 'PowertPort' is a misspelling of Anker's product name 'PowerPort'.
    - `Anker PowertPort Solar`
    - Fix: Correct 'PowertPort' to 'PowerPort'.
  - **[LOW] narrative-break** — Sentence ends with 'quirky and unexpected.' — appears to be missing a noun (e.g., 'quirky and unexpected content/voices').
    - `seek out personal websites with their quirky and unexpected.`
    - Fix: Add the missing noun, e.g., 'their quirky and unexpected content.'

### #57 — Weekly Thing #57 / Jun 9, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has a notable cluster of migration-era link-formatting artifacts (anchor text spanning sentence boundaries and starting mid-title) plus a missing `##` on the "My Blog Posts" header and a couple of minor typos.
  - **[MEDIUM] header-error** — This is a section header that lost its `##` prefix during migration, rendering as plain text instead of an H2 section heading, which causes the following H3 to appear orphaned.
    - `My Blog Posts ✍️`
    - Fix: Prefix with `## ` to restore it as an H2 section header.
  - **[LOW] typo** — "make" should be "made" — clear grammatical error in the tense.
    - `it caught my attention and [make me remember Do The Work]`
    - Fix: Change "make me remember" to "made me remember".
  - **[MEDIUM] malformed-link** — The link anchor text incorrectly spans across words that should be outside the link; the link wrapping begins mid-sentence and includes "sell it this way, but" which should be plain prose.
    - `They don't [sell it this way, but Sanebox](https://www.sanebox.com) is a lot like a bot for my email.`
    - Fix: Rewrite so only "Sanebox" is the linked text: `They don't sell it this way, but [Sanebox](https://www.sanebox.com) is a lot like a bot for my email.`
  - **[MEDIUM] malformed-link** — Link anchor text spans across a sentence boundary ("feature. I use Safari with 1Blocker"), which is a malformed link where only "1Blocker" should be the link text.
    - `Apple has started to lead and even use this as a leading [feature. I use Safari with 1Blocker](https://1blocker.com) [and Ghostery](https://www.ghostery.com)`
    - Fix: Restructure to link only the product names: `...as a leading feature. I use Safari with [1Blocker](https://1blocker.com) and [Ghostery](https://www.ghostery.com)...`
  - **[MEDIUM] malformed-link** — Link anchor text spans across sentence boundaries and includes surrounding prose rather than just the target phrase — a migration artifact of imported link formatting.
    - `The Wikimedia Foundation operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Restructure so only the named entities ("Wikipedia", "Donate to Wikimedia today!") are the link anchors.
  - **[LOW] narrative-break** — The photo caption "The sun setting after a fabulous day of fun on Cannon Lake." appears three times in a row (alt text, caption, and metadata line), which reads awkwardly as duplication.
    - `![The sun setting after a fabulous day of fun on Cannon Lake.](https://files.thingelstad.com/weekly-thing/57/cover.jpg)

The sun setting after a fabulous day of fun on Cannon Lake. Minnesota is beautiful. 💚

The sun setting after a fabulous day of fun on Cannon Lake.`
    - Fix: Remove the redundant third occurrence or consolidate the caption so the description isn't repeated.
  - **[LOW] migration-artifact** — A bare URL appears on its own line immediately before the linked description, a leftover artifact of the migration from a card/preview format.
    - `https://wikimediafoundation.org/wiki/Home`
    - Fix: Remove the bare URL line since the link is duplicated in the following paragraph.
  - **[LOW] migration-artifact** — Bare URL on its own line immediately before the H3 link to the same URL — a leftover from the card-preview import format.
    - `https://itunes.apple.com/us/app/omnifocus-3/id1346190318?mt=8&uo=4`
    - Fix: Remove the standalone URL line since it duplicates the subsequent linked heading.
  - **[LOW] typo** — "appliactions" is a misspelling of "applications".
    - `my most frequently used, and trusted appliactions`
    - Fix: Change to "applications".
  - **[MEDIUM] malformed-link** — The link anchor starts mid-title ("Python Application" is outside the link but should be part of it) — a common migration artifact in the Yet More Links list.
    - `- Python Application [Layouts: A Reference – Real Python](https://realpython.com/python-application-layouts/) realpython.com`
    - Fix: Wrap the full title inside the link brackets: `[Python Application Layouts: A Reference – Real Python](...)`; this applies to several similarly broken items in this list.

### #58 — Weekly Thing #58 / Jun 16, 2018

- Era: MailChimp
- Overall: Issue is generally in good shape; minor issues include an orphan footnote marker in a quote, an empty parenthesis in the book metadata, and a 'hear/here' typo in the opening.
  - **[LOW] narrative-break** — The stray '3' after 'acting on it.' appears to be an orphaned footnote marker from the source article that wasn't cleaned up during quoting.
    - `They watch to see if each other are listening to the feedback and eventually acting on it.3 Once everyone has seen`
    - Fix: Remove the stray '3' footnote reference from the quoted passage.
  - **[LOW] other** — Empty parentheses suggest a missing value (likely a year or author) that was not filled in during migration/templating.
    - `Collapse: How Societies Choose to Fail or Succeed: Revised Edition ()`
    - Fix: Either remove the empty parentheses or fill in the missing metadata.
  - **[MEDIUM] typo** — 'are hear' should be 'are here' — a clear homophone typo in the opening line.
    - `We [are hear to see Brandi Carlile](http://brandicarlile.com)`
    - Fix: Change 'are hear' to 'are here'.

### #59 — Weekly Thing #59 / Jun 23, 2018

- Era: MailChimp
- Overall: The issue is readable and complete, but it contains a recurring migration artifact where markdown link anchors span extra prose or start mid-title — affecting roughly a dozen links across Notable Links, Yet More Links, and Microposts.
  - **[MEDIUM] malformed-link** — The link anchor awkwardly wraps the headphones emoji and 'I first read Tom Peters' instead of just linking his name — likely a migration/markdown artifact where the link range was misplaced.
    - `Fabulous podcast! [🎧 I first read Tom Peters](http://tompeters.com) "Re-imagine!" a long time ago`
    - Fix: Reformat so the link wraps only 'Tom Peters', e.g., '🎧 I first read [Tom Peters](http://tompeters.com)'s "Re-imagine!"...'.
  - **[MEDIUM] malformed-link** — Link anchors swallow surrounding prose (a known migration artifact in this era), producing oddly-linked sentence fragments with trailing spaces before punctuation.
    - `[Good overview of new service, WhenWorks](https://when.works) . [In the past I've used Calendly](https://calendly.com)`
    - Fix: Restructure so only the product names are linked, e.g., 'Good overview of new service, [WhenWorks](https://when.works). In the past I've used [Calendly](https://calendly.com)...'.
  - **[MEDIUM] malformed-link** — The second link anchor starts with '. ' (period+space), clearly a migration error where link boundaries captured punctuation and prose.
    - `[they have a new YNAB API](https://api.youneedabudget.com) [. We have been using YNAB](https://www.youneedabudget.com)`
    - Fix: Rewrite so link text is just the product name: '... a new [YNAB API](https://api.youneedabudget.com). We have been using [YNAB](https://www.youneedabudget.com) for a few years...'.
  - **[MEDIUM] malformed-link** — Link anchor captures extraneous prose ('that this soon appears in') rather than just the product name — migration artifact.
    - `[that this soon appears in Zapier](https://zapier.com) [and IFTTT](https://ifttt.com)`
    - Fix: Reduce anchors to product names only: 'that this soon appears in [Zapier](https://zapier.com) and [IFTTT](https://ifttt.com)'.
  - **[MEDIUM] malformed-link** — Link anchor captures awkward prose ending with dangling 'for.' outside the link — migration artifact.
    - `[problem which I still use Doodle](https://doodle.com) for.`
    - Fix: Rework as 'problem, which I still use [Doodle](https://doodle.com) for.'
  - **[MEDIUM] malformed-link** — Link anchor awkwardly spans 'survivorship bias in Nassim Nicholas Taleb' with stray 's after the link — migration artifact.
    - `I first read about [survivorship bias in Nassim Nicholas Taleb](http://www.fooledbyrandomness.com) 's "Fooled by Randomness"`
    - Fix: Link only the author's name: 'survivorship bias in [Nassim Nicholas Taleb](http://www.fooledbyrandomness.com)'s "Fooled by Randomness"'.
  - **[MEDIUM] malformed-link** — Link anchor starts mid-sentence at 'years.' — the markdown link was incorrectly placed during migration, cutting across a sentence boundary.
    - `years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the link so only 'Donate to Let's Encrypt today!' is the anchor text.
  - **[MEDIUM] malformed-link** — Link anchor starts mid-title, leaving the first half of the title unlinked — migration artifact consistent across several 'Yet More Links' entries.
    - `- Make Way for Friends, Trading, and Gifting [in Pokémon GO! - Pokémon GO](https://pokemongolive.com/post/friendsandtrading/)`
    - Fix: Link the full title: '[Make Way for Friends, Trading, and Gifting in Pokémon GO! - Pokémon GO](https://...)'.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title; first half of title is unlinked prose — migration artifact.
    - `- It Looks Like I’m Gonna Be Super Busy Til [I’m Dead - McSweeney’s Internet Tendency](https://www.mcsweeneys.net/articles/it-looks-like-im-gonna-be-super-busy-til-im-dead)`
    - Fix: Wrap the entire title in the link.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title; the leading 'Ballerina - A cloud native programming' is unlinked, and there is no description line beneath this bullet.
    - `- Ballerina - A cloud native programming [language for integration - Ballerina Blog](https://blog.ballerina.io/posts/ballerina-a-cloud-native-programming-language/) blog.ballerina.io`
    - Fix: Link the entire title and add a description line if intended.
  - **[LOW] malformed-link** — Link anchor starts mid-title, leaving 'The Legend' outside the link.
    - `The kids got me The Legend [of Zelda: Breath of the Wild](https://www.nintendo.com/games/detail/the-legend-of-zelda-breath-of-the-wild-switch)`
    - Fix: Link the full title 'The Legend of Zelda: Breath of the Wild'.
  - **[LOW] malformed-link** — Link anchor captures 'over the Big Top Chautauqua' plus an emoji instead of just the venue name.
    - `Lightning [⚡️ over the Big Top Chautauqua](https://www.bigtop.org) resulted`
    - Fix: Link only 'Big Top Chautauqua'.
  - **[LOW] malformed-link** — Link anchor awkwardly spans a sentence boundary ('here. 🎶✨ Thank you Brandi Carlile') with trailing ' !'.
    - `Magical [here. 🎶✨ Thank you Brandi Carlile](http://www.brandicarlile.com) !`
    - Fix: Link only 'Brandi Carlile' and clean up spacing before '!'.
  - **[LOW] typo** — Grammatical error: 'may appearing' should be 'may be appearing' or 'may appear'.
    - `Custom coffee cups may appearing soon.`
    - Fix: Change to 'Custom coffee cups may be appearing soon.'

### #60 — Weekly Thing #60 / Jun 30, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has a recurring migration artifact where link anchors begin mid-phrase and the 'Yet More Links' section has trailing bare domains that should be cleaned up.
  - **[MEDIUM] narrative-break** — The link text awkwardly starts mid-phrase ('behind [the scenes look...]'), suggesting the link markup was applied to the wrong span of text during migration.
    - `Some nice pictures and behind [the scenes look into Formula 1](https://www.formula1.com) .`
    - Fix: Reflow as 'Some nice pictures and [behind the scenes look into Formula 1](https://www.formula1.com).'
  - **[MEDIUM] narrative-break** — The link wraps an odd mid-sentence span, a recurring migration artifact where link boundaries don't match the intended anchor text.
    - `I bypassed Facebook, but appreciated [them highlighting this organization and donated](https://actionnetwork.org/fundraising/bondfund) myself.`
    - Fix: Rewrite so the link anchor is a natural phrase, e.g., '[appreciated them highlighting this organization](...) and donated myself.'
  - **[MEDIUM] narrative-break** — Link anchor text is split awkwardly across the sentence, with 'Ten Arguments For Deleting' left outside the book link — a migration artifact.
    - `[Review of Jaron Lanier's](http://www.jaronlanier.com) new book Ten Arguments For Deleting [Your Social Media Accounts Right Now](https://www.indiebound.org/book/9781250196682) .`
    - Fix: Consolidate the book title inside one link: '[Ten Arguments For Deleting Your Social Media Accounts Right Now](...)'.
  - **[MEDIUM] narrative-break** — Link anchor spans a sentence boundary ('we have. I've recently gotten the HDHomeRun'), clearly a misplaced link range from migration.
    - `I've long had an Apple TV attached to each TV we [have. I've recently gotten the HDHomeRun](https://www.silicondust.com/hdhomerun/) referenced here`
    - Fix: Restrict the link to 'HDHomeRun' only and close the prior sentence properly.
  - **[MEDIUM] narrative-break** — The H3-style title has been converted into a list item where the link anchor starts mid-title and the bare domain trails afterward — a migration artifact repeated throughout 'Yet More Links'.
    - `- A one size fits all database doesn't [fit anyone - All Things Distributed](https://www.allthingsdistributed.com/2018/06/purpose-built-databases-in-aws.html) www.allthingsdistributed.com`
    - Fix: Wrap the full title in the link and drop the trailing bare domain, or restore the original H3 formatting.
  - **[LOW] malformed-link** — A stray bare domain trails the properly linked title, which is a visible migration artifact in the Yet More Links section.
    - `- [molten: modern API framework](https://moltenframework.com/) moltenframework.com`
    - Fix: Remove the trailing 'moltenframework.com' (and similar trailing domains in this section).
  - **[LOW] narrative-break** — Link anchor starts mid-sentence after 'non-profit.', so the CTA link spans a sentence boundary — migration artifact.
    - `non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Limit the anchor to '[Become a Community Supporter today!]'.
  - **[LOW] dangling-reference** — A bare URL sits on its own line directly under the heading with no context; it's likely a leftover from an image or link that didn't migrate cleanly.
    - `## Give Back 🎁

https://minnestar.org`
    - Fix: Either remove the stray URL or convert it into a proper link/image as intended.

### #61 — Weekly Thing #61 / Jul 7, 2018

- Era: MailChimp
- Overall: Issue is largely in good shape; the main concern is the 'Itty bitty sites' entry which lost its H3/link heading structure and appears as a bare parenthesized URL, plus a few minor typos.
  - **[MEDIUM] malformed-link** — The 'Itty bitty sites' entry is missing its H3 heading with link syntax — the URL appears as bare parenthesized text rather than `### [Itty bitty sites](url)`, breaking the section pattern and likely rendering oddly.
    - `Itty bitty sites
(https://itty.bitty.site/#About/XQAAAAKrCQAAAAAAAAAeHMqHyTY4PyKmqfkwr6ooCXSIMxPQ7ojYR153HqZD3W+keVdvwyoyd+luwncAksvskG/my97qDaUEyfDGB0QDbdURMwS0L90o5EpQ7O+BMmWrcB7fs71TJEJv1I/T`
    - Fix: Convert to the standard `### [Itty bitty sites](https://itty.bitty.site/#About/...)` heading format used by all surrounding Notable Links entries.
  - **[LOW] malformed-link** — Link anchor boundaries appear miscut — 'to this link from Marty Cagan' is linked to Cagan's LinkedIn while 'of SAFe, Revenge of the PMO' is linked to the article; the anchor text awkwardly starts/ends mid-phrase, suggesting link placement drift during migration.
    - `I came [to this link from Marty Cagan](https://www.linkedin.com/in/cagan/) 's total and complete takedown [of SAFe, Revenge of the PMO](https://svpg.com/revenge-of-the-pmo/)`
    - Fix: Re-anchor links to more natural phrases (e.g., link 'Marty Cagan' to LinkedIn and 'Revenge of the PMO' to the article).
  - **[LOW] typo** — 'Wether' should be 'Whether'.
    - `Wether [Facebook is a platform or not](https://stratechery.com/2018/the-bill-gates-line/)`
    - Fix: Change 'Wether' to 'Whether'.
  - **[LOW] typo** — 'webmentuons' is a clear misspelling of 'webmentions'.
    - `Detailed example for implementing webmentuons.`
    - Fix: Correct 'webmentuons' to 'webmentions'.
  - **[LOW] typo** — 'bacgkround' is a transposition typo of 'background'.
    - `Plus the remote control boat zooming by in the bacgkround!`
    - Fix: Correct 'bacgkround' to 'background'.

### #62 — Weekly Thing #62 / Jul 14, 2018

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but the Yet More Links section has a systemic link-wrapping bug where titles are split between plain text and anchor text.
  - **[MEDIUM] malformed-link** — The link anchor text was split mid-title so only 'features for pros — Apple Newsroom' is linked while the beginning of the title is plain text; this pattern repeats through the Yet More Links section.
    - `- Apple updates MacBook Pro with faster performance and new [features for pros — Apple Newsroom](https://www.apple.com/newsroom/2018/07/apple-updates-macbook-pro-with-faster-performance-and-new-features-for-pros/) www.apple.com`
    - Fix: Rewrap each bullet so the entire title is the link text, e.g., [Apple updates MacBook Pro with faster performance and new features for pros — Apple Newsroom](URL).
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence ('non-profit. Become a Community Supporter today!'), suggesting the bracket was misplaced during migration.
    - `Minnestar is a 501c3 [non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Move the opening bracket so only the call-to-action is linked, e.g., 'Minnestar is a 501c3 non-profit. [Become a Community Supporter today!](...)'.
  - **[LOW] narrative-break** — The alt text and photo metadata appear as duplicated prose below the image, looking like leftover EXIF/caption fields from migration rather than intentional body copy.
    - `The corn is definitely "knee high before the 4th of July"!

Cornfield with barn in background.
Jul 6, 2018 at 2:51 PM
Warsaw, MN`
    - Fix: Remove the duplicated 'Cornfield with barn in background.' line or format the date/location as an italicized caption.
  - **[LOW] typo** — 'cane' should be 'can'.
    - `More research that shows how precise identification cane be on metadata alone.`
    - Fix: Change 'cane be' to 'can be'.

### #63 — Weekly Thing #63 / Jul 21, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has an unusually high number of migration-era malformed markdown links where anchor text crosses sentence boundaries or starts mid-title, plus a notable name typo ('Guido Van Possum').
  - **[HIGH] malformed-link** — The link anchor text incorrectly spans a sentence boundary ('basis. I have this great bike'), indicating the markdown link was mis-formed during migration — the period and sentence break got pulled inside the link text.
    - `I should be riding my bike 🚲 to work on a regular [basis. I have this great bike](http://defiantbicycles.com/shop-fulton/defiant-one)`
    - Fix: Rewrite so only 'this great bike' (or similar) is the link text: e.g., 'on a regular basis. I have [this great bike](http://defiantbicycles.com/shop-fulton/defiant-one)'.
  - **[HIGH] malformed-link** — The link text crosses a sentence boundary ('years. Donate to Let's Encrypt today!'), a migration artifact where the anchor swallowed the preceding period and word.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Restructure so the anchor covers only the call-to-action: '…in recent years. [Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)'.
  - **[MEDIUM] malformed-link** — Link text begins mid-phrase ('Online - Now and for free') with 'Things To Read' orphaned outside the link — a migration artifact common in this era's Yet More Links list.
    - `- Things To Read [Online - Now and for free](http://thingstoread.online/) thingstoread.online`
    - Fix: Make the full title the link: '[Things To Read Online - Now and for free](http://thingstoread.online/)'.
  - **[MEDIUM] malformed-link** — Anchor starts mid-title, leaving 'AWS Kinesis with' outside the link.
    - `- AWS Kinesis with [Lambdas: Lessons Learned · trivago techblog](https://tech.trivago.com/2018/07/13/aws-kinesis-with-lambdas-lessons-learned/)`
    - Fix: Expand the anchor to cover the full title: '[AWS Kinesis with Lambdas: Lessons Learned · trivago techblog](…)'.
  - **[MEDIUM] malformed-link** — Anchor starts mid-title, splitting 'World' from 'Emoji Day — July 17, 2018'.
    - `- 📅 World [Emoji Day — July 17, 2018](https://worldemojiday.com/) worldemojiday.com`
    - Fix: Include 'World' in the link text.
  - **[MEDIUM] malformed-link** — Anchor begins mid-headline, leaving the first half of the title outside the link.
    - `- Walmart establishes strategic partnership with Microsoft to [further accelerate digital innovation in retail](https://news.walmart.com/2018/07/17/walmart-establishes-strategic-partnership-with-microsoft-to-further-accelerate-digital-innovation-in-retail)`
    - Fix: Make the whole headline the link text.
  - **[MEDIUM] malformed-link** — Link anchors include editorial filler words ('Wow,' and 'aside as') rather than the named entity — typical migration artifact, and also contains a misspelling.
    - `[Wow, Guido von Rossum](https://en.wikipedia.org/wiki/Guido_van_Rossum) , creator of Python, is stepping [aside as Benevolent Dictator for Life](https://en.wikipedia.org/wiki/Benevolent_dictator_for_life)`
    - Fix: Tighten the anchors to the proper nouns and fix spelling: '[Guido van Rossum]' and '[Benevolent Dictator for Life]'.
  - **[MEDIUM] typo** — Misspelling of the Python creator's name; should be 'Guido van Rossum' (the correct spelling appears in the very next link in the same issue: 'Guido Van Possum' is also wrong earlier).
    - `Guido von Rossum`
    - Fix: Correct to 'Guido van Rossum'.
  - **[HIGH] typo** — 'Van Possum' is a clear typo for 'van Rossum' (the Python creator's surname).
    - `post Guido Van Possum`
    - Fix: Change to 'post Guido van Rossum'.
  - **[LOW] typo** — 'it's' (contraction of 'it is') is used where possessive 'its' is required.
    - `Nice to see ACM update it’s Code of Ethics.`
    - Fix: Change 'it's' to 'its'.

### #64 — Weekly Thing #64 / Jul 28, 2018

- Era: MailChimp
- Overall: Readable and era-normal overall, but the Yet More Links section has several mis-placed link brackets and a couple of sentences elsewhere have small authoring glitches worth cleaning up.
  - **[MEDIUM] malformed-link** — The link text awkwardly includes the emoji and the word 'This' with 'Bloomberg', leaving 'article' outside the link — likely a link-boundary error.
    - `[😲 This Bloomberg](https://www.bloomberg.com/news/articles/2018-07-26/slack-and-atlassian-team-up-to-take-on-microsoft-in-chat-software) article`
    - Fix: Rework to something like '😲 This [Bloomberg article](...)' so the link text is 'Bloomberg article'.
  - **[MEDIUM] malformed-link** — The link anchor text spans a sentence boundary ('call blockers. I subscribe to NoMoRoBo'), indicating a misplaced bracket during authoring.
    - `[call blockers. I subscribe to NoMoRoBo](https://www.nomorobo.com)`
    - Fix: Limit the anchor to 'NoMoRoBo': 'call blockers. I subscribe to [NoMoRoBo](https://www.nomorobo.com)'.
  - **[MEDIUM] malformed-link** — In the Yet More Links bullets, the link anchor begins mid-title rather than wrapping the whole item title, a pattern repeated throughout this section.
    - `Knative - Built on [Kubernetes and Istio  |  Google Cloud](https://cloud.google.com/knative/)`
    - Fix: Wrap the full article title in the link, e.g., '[Knative - Built on Kubernetes and Istio | Google Cloud](...)'.
  - **[LOW] malformed-link** — Link anchor starts partway through the title rather than covering the full title.
    - `Streamline 3.0 [– The World's Largest Icon Library](https://streamlineicons.com/)`
    - Fix: Expand the link anchor to cover the whole title.
  - **[LOW] malformed-link** — Anchor text covers only the publication name, leaving most of the headline as plain text; consistent with mid-title bracket errors in this section.
    - `Target shifts cloud-computing business to Alphabet's Google - [Minneapolis / St. Paul Business Journal](https://www.bizjournals.com/twincities/news/2018/07/24/target-shifts-cloud-computing-business-to-google.html)`
    - Fix: Wrap the entire article title in the link.
  - **[LOW] narrative-break** — Reads as a dropped word — 'he many of the other people' appears to be missing a verb (e.g., 'has' or 'and').
    - `the audiobook for this is a treat as it's read by Doerr and he many of the other people quoted`
    - Fix: Revise to 'and many of the other people quoted…' or 'and he has many of the other people…'.
  - **[LOW] other** — Empty parentheses after the book title suggest a missing field (likely a year) from a template.
    - `Measure What Matters: How Google, Bono, and the Gates Foundation Rock the World with OKRs ()`
    - Fix: Fill in the missing value or remove the empty parentheses.
  - **[LOW] typo** — 'Its' should be 'It's' (contraction of 'it has').
    - `Its also been going on for over 10 years?`
    - Fix: Change 'Its' to 'It's'.

### #65 — Weekly Thing #65 / Aug 4, 2018

- Era: MailChimp
- Overall: Readable overall, but this issue has a systemic mis-bracketing problem — many link titles in 'Yet More Links' and a couple elsewhere have their opening '[' placed mid-phrase, producing awkward anchor text that a reader would notice.
  - **[HIGH] malformed-link** — The markdown link brackets wrap the wrong text — the linked phrase should be 'M. C. Escher' but instead spans 'technologists, I find M. C. Escher's', which appears to be a migration/autolink artifact.
    - `Like many [technologists, I find M. C. Escher's](https://en.wikipedia.org/wiki/M._C._Escher) art mesmerizing.`
    - Fix: Rewrite as 'Like many technologists, I find [M. C. Escher's](https://en.wikipedia.org/wiki/M._C._Escher) art mesmerizing.'
  - **[HIGH] malformed-link** — The link text mistakenly swallows the word 'years.' from the preceding sentence, so the rendered anchor reads 'years. Donate to Let's Encrypt today!' instead of a clean call-to-action.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the bracket to start at 'Donate' so the sentence reads 'in recent years. [Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)'.
  - **[HIGH] malformed-link** — The link bracket starts mid-phrase, making the anchor text 'image browser and organizer for macOS' rather than the product name 'Spect'; a recurring pattern in this list suggesting a migration artifact.
    - `- Spect - Fast [image browser and organizer for macOS](http://stevenf.com/spect/) stevenf.com`
    - Fix: Rebracket so the product name is the link, e.g., '[Spect - Fast image browser and organizer for macOS](http://stevenf.com/spect/)'.
  - **[HIGH] malformed-link** — The opening bracket is placed mid-phrase after 'On This ', splitting the title across the link and breaking the quoted feature name.
    - `- Add an "On This [Day" feature to a Micro.blog website](https://github.com/cleverdevil/micromemories) github.com`
    - Fix: Move the bracket to the start of the title: '[Add an "On This Day" feature to a Micro.blog website](https://github.com/cleverdevil/micromemories)'.
  - **[HIGH] malformed-link** — Link brackets start mid-title, so the anchor text only captures a fragment of the product title.
    - `HR Software to Motivate, Inspire [and Develop Your Workforce | BetterWorks](https://www.betterworks.com/)`
    - Fix: Rebracket the full title: '[HR Software to Motivate, Inspire and Develop Your Workforce | BetterWorks](https://www.betterworks.com/)'.
  - **[HIGH] malformed-link** — 'Perdoo.' is left outside the link as bare text while only the tagline is hyperlinked — same mis-bracketing pattern.
    - `- Perdoo. [OKR software for leaders and teams.](https://www.perdoo.com/) www.perdoo.com`
    - Fix: Include the product name in the link: '[Perdoo. OKR software for leaders and teams.](https://www.perdoo.com/)'.
  - **[HIGH] malformed-link** — Bracket opens mid-word inside a parenthetical, splitting 'Key results' across the link boundary and producing odd anchor text.
    - `- OKR (Objectives and Key [results) Software for Teams - Weekdone](https://weekdone.com/okr-software) weekdone.com`
    - Fix: Rebracket the whole title: '[OKR (Objectives and Key results) Software for Teams - Weekdone](https://weekdone.com/okr-software)'.
  - **[MEDIUM] malformed-link** — Prefix text 'Google Cloud Platform Blog:' sits outside the link while the article title is linked — inconsistent with era convention where the full title is the link.
    - `- Google Cloud Platform Blog: [Istio reaches 1.0: ready for prod](https://cloudplatform.googleblog.com/2018/07/istio-reaches-1-0-ready-for-prod.html) cloudplatform.googleblog.com`
    - Fix: Either move the prefix inside the brackets or drop it, matching the standard '### [Title](url)' pattern used elsewhere.
  - **[LOW] typo** — 'te' is a clear typo for 'the'.
    - `Istio is an important part of te Kubernetes ecosystem.`
    - Fix: Change 'te' to 'the'.
  - **[LOW] other** — Stray space before the exclamation mark, and the link bracketing again starts mid-sentence rather than wrapping a natural phrase — minor cosmetic issue consistent with the mis-bracketing pattern in this issue.
    - `Thank you [for subscribing to the Weekly Thing](https://weekly.thingelstad.com/) !`
    - Fix: Remove the space before '!' and consider rewording the link, e.g., 'Thank you for [subscribing to the Weekly Thing](https://weekly.thingelstad.com/)!'.

### #66 — Weekly Thing #66 / Aug 11, 2018

- Era: MailChimp
- Overall: Readable issue overall, but multiple migration-era link-anchor boundaries wrap the wrong text (Moom, Rosemary Orchard, Jason Greenberg), and there's one clear their/there typo.
  - **[LOW] malformed-link** — The static audit flagged `[Really]` as orphan bracketed text, but it is actually part of the link's display title (nested brackets inside markdown link text); it renders fine and is not a real issue.
    - `### [The Speed Trap: When Taking Your Time [Really] Matters](http://tompeters.com/wp-content/uploads/2018/08/speed_trap_0727_18.pdf)`
    - Fix: No fix required; the static audit's flag is a false positive.
  - **[MEDIUM] malformed-link** — The link text spans an unnatural clause boundary ("manage these things. I use Moom"), a migration artifact where the anchor wrapped too much text.
    - `I also have workflows to [manage these things. I use Moom](https://manytricks.com/moom/) instead of SizeUp, and Ulysses instead of Bear.`
    - Fix: Re-anchor the link to just "Moom" so the sentence reads naturally.
  - **[MEDIUM] malformed-link** — The link anchor begins mid-quotation with "- this time on the Mac!”" rather than wrapping the title, a migration artifact that makes the linked text read oddly.
    - `OmniFocus 3 for Mac Sneak Peek —Rosemary Orchard “I am once again lucky enough to be in the early preview for OmniFocus 3 [- this time on the Mac!”](https://www.rosemaryorchard.com/blog/omnifocus-3-mac-sneak-peek)`
    - Fix: Re-anchor the URL to the title ("OmniFocus 3 for Mac Sneak Peek") instead of the trailing quote fragment.
  - **[MEDIUM] malformed-link** — The second link's anchor text starts with "! 🐖 Thanks Jason Greenberg", wrapping punctuation and emoji from the prior sentence — a migration-era anchor boundary error.
    - `Enjoying [a delicious lunch at Dinosaur Bar-B-Que](http://www.dinosaurbarbque.com) [! 🐖 Thanks Jason Greenberg](https://www.linkedin.com/in/jason-greenberg-7b01768/)`
    - Fix: Re-anchor the LinkedIn URL to just "Jason Greenberg".
  - **[LOW] malformed-link** — Like several entries in Yet More Links, the link anchor begins mid-phrase ("Horrors of" left outside), an era-typical migration pattern but worth noting as a readability degradation.
    - `Horrors of [using Azure Kubernetes Service in production](https://movingfulcrum.com/horrors-of-using-azure-kubernetes-service-in-production/) movingfulcrum.com`
    - Fix: Re-anchor the link to the full title so "Horrors of" is inside the link.
  - **[LOW] typo** — "there" should be "their" — a clear homophone error.
    - `Another example of tech employees disagreeing with the direction there companies are going.`
    - Fix: Change "there companies" to "their companies".

### #67 — Weekly Thing #67 / Aug 18, 2018

- Era: MailChimp
- Overall: Readable overall, but the issue has several malformed markdown links — most notably in the Health Checks paragraph and across the 'Yet More Links' bullets — where bracket placement mangles sentence structure.
  - **[HIGH] malformed-link** — The link text brackets were placed around sentence fragments rather than the intended descriptive labels, causing the prose to read as broken sentences interrupted by the link anchors.
    - `I have been running health checks [for decades. BigCharts server is happy](http://bigcharts.marketwatch.com/up2.aspx) is [the first. MarketWatch is also happy](https://www.marketwatch.com/up2.aspx) .`
    - Fix: Rewrite so the sentence flows naturally, e.g., 'I have been running health checks for decades. [BigCharts server is happy](...) is the first. [MarketWatch is also happy](...) is another.'
  - **[MEDIUM] malformed-link** — The link bracket wraps across a sentence boundary, so 'non-profit.' ends up as part of the link text along with the call-to-action.
    - `Minnestar is a 501c3 [non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Move the opening bracket so only 'Become a Community Supporter today!' is the linked phrase.
  - **[MEDIUM] malformed-link** — A bare URL appears on its own line immediately before the same link is reintroduced as a proper markdown link, suggesting a stray leftover from editing.
    - `## Give Back 🎁

https://minnestar.org

[Minnestar](https://minnestar.org/)`
    - Fix: Delete the orphan bare 'https://minnestar.org' line.
  - **[LOW] narrative-break** — 'there' should be 'their' — a clear homophone error, not a stylistic choice.
    - `The kids did there school shopping`
    - Fix: Change 'there' to 'their'.
  - **[LOW] typo** — 'detect and impending' should be 'detect an impending' — a clear typo.
    - `the framework for considering how to detect and impending situation like this`
    - Fix: Change 'and' to 'an'.
  - **[LOW] malformed-link** — Across multiple 'Yet More Links' bullets, the opening bracket is placed mid-title so the first word is outside the link text (e.g., 'Best' then '[Practices…]'), which is a consistent migration/formatting artifact.
    - `- Best [Practices for Newsletters — CJ Chilvers](https://www.cjchilvers.com/blog/best-practices-for-newsletters) www.cjchilvers.com`
    - Fix: Move the opening brackets to wrap the full titles in these bullet list items.

### #68 — Weekly Thing #68 / Aug 25, 2018

- Era: MailChimp
- Overall: Readable issue overall, but the missing H2 on 'My Blog Posts ✍️', a stray bare EFF URL, and a small 'iI' typo should be cleaned up.
  - **[MEDIUM] header-error** — The 'My Blog Posts ✍️' section header is plain text instead of an H2, causing the following H3 to be an orphan subheading (as noted by static audit).
    - `My Blog Posts ✍️

### [Goodbye to my friend, David Hussman]`
    - Fix: Prefix 'My Blog Posts ✍️' with '## ' to make it a proper H2 section header.
  - **[LOW] typo** — Double letter 'iI' is a clear typo at the start of the sentence.
    - `iI reminds [me of the Race Across America]`
    - Fix: Change 'iI reminds' to 'It reminds'.
  - **[MEDIUM] malformed-link** — Two adjacent link brackets with no connecting prose read awkwardly — the phrase 'and the critically important Let's Encrypt' appears to have been split from the previous link's anchor text rather than flowing naturally.
    - `[recently launched solutions like Privacy Badger](https://www.eff.org/privacybadger) [and the critically important Let's Encrypt](https://letsencrypt.org)`
    - Fix: Rework the sentence so the link anchors are separated by natural prose (e.g., 'like Privacy Badger and the critically important Let's Encrypt service').
  - **[LOW] dangling-reference** — A bare URL appears on its own line immediately before a properly linked reference to the same site, looking like a leftover/migration artifact.
    - `## Give Back 🎁

https://www.eff.org

[The Electronic Frontier Foundation](https://www.eff.org)`
    - Fix: Remove the stray bare 'https://www.eff.org' line above the linked paragraph.

### #69 — Weekly Thing #69 / Sep 1, 2018

- Era: MailChimp
- Overall: Readable overall, but the 'Yet More Links' section has a systemic markdown-link issue where many titles start outside the link brackets, which degrades the list's presentation.
  - **[MEDIUM] malformed-link** — The link text only wraps the latter half of the title; the first half ('Exclusive: Apple Watch Series 4 revealed — massive display,') is plain text outside the link, suggesting the link bracket placement was broken during migration.
    - `- Exclusive: Apple Watch Series 4 revealed — massive display, [dense watch face, more | 9to5Mac](https://9to5mac.com/2018/08/30/exclusive-apple-watch-series-4/) 9to5mac.com`
    - Fix: Wrap the entire title in the link markdown so the link text reads 'Exclusive: Apple Watch Series 4 revealed — massive display, dense watch face, more | 9to5Mac'.
  - **[MEDIUM] malformed-link** — Same broken-link pattern: the leading portion of the headline is outside the link brackets.
    - `- Exclusive: This is ‘iPhone XS’ — design, larger version, [and gold colors confirmed | 9to5Mac](https://9to5mac.com/2018/08/30/2018-iphone-xs-design-larger-version-gold-exclusive/) 9to5mac.com`
    - Fix: Expand the link text to wrap the whole article title.
  - **[MEDIUM] malformed-link** — Only part of the title is linked; 'Sinkholes: When the' sits outside the link.
    - `- Sinkholes: When the [Earth Opens Up - The Atlantic](https://www.theatlantic.com/photo/2018/08/sinkholes-when-the-earth-opens-up/568762/) www.theatlantic.com`
    - Fix: Move the opening bracket to the start of the title so the entire title is the anchor text.
  - **[MEDIUM] malformed-link** — Link bracket starts mid-title, leaving 'Serverless Best' outside the hyperlink.
    - `- Serverless Best [Practices – Paul Johnston – Medium](https://medium.com/@PaulDJohnston/serverless-best-practices-b3c97d551535) medium.com`
    - Fix: Wrap the full title in the link.
  - **[MEDIUM] malformed-link** — The word 'Manifesto' falls outside the link brackets, truncating the anchor text.
    - `- Manifesto [for Minimalist Software Engineers | Minifesto.org](http://minifesto.org/) minifesto.org`
    - Fix: Include 'Manifesto' inside the link text.
  - **[MEDIUM] malformed-link** — Only part of the title is contained in the link; the leading 'A Case Against' is plain text.
    - `- A Case Against [Optimizing Your Life : zen habits](https://zenhabits.net/unoptimizing/) zenhabits.net`
    - Fix: Wrap the full title inside the link brackets.
  - **[MEDIUM] malformed-link** — 'The original' is outside the anchor text, producing an incomplete link title.
    - `- The original [demo of Imagine by John Lennon](https://kottke.org/18/08/the-original-demo-of-imagine-by-john-lennon) kottke.org`
    - Fix: Include 'The original' inside the link brackets.
  - **[MEDIUM] malformed-link** — The beginning of the title sits outside the link brackets.
    - `- littleBits: Award-winning electronic building blocks [for creating inventions large and small](https://littlebits.com/) littlebits.com`
    - Fix: Expand the link to cover the entire title.
  - **[LOW] malformed-link** — The anchor text awkwardly begins with 'history.' because the opening bracket was placed mid-sentence, breaking the sentence visually when rendered.
    - `The Internet Archive is working hard to capture that information and keep it for [history. Donate to Internet Archive today!](https://archive.org/donate/)`
    - Fix: Move the bracket to start at 'Donate' (or similar) so the anchor reads as a standalone call to action.
  - **[LOW] typo** — 'Your' should be 'You're' (you are).
    - `My opinion? Your absolutely bonkers to believe that WhatsApp is going to continue to fight for user privacy after Facebook bought it.`
    - Fix: Change 'Your' to 'You're'.

### #70 — Weekly Thing #70 / Sep 8, 2018

- Era: MailChimp
- Overall: Readable issue overall, but the 'Yet More Links' section has a consistent migration artifact where link anchors start mid-title, and one micropost has tangled link/parenthesis markup worth fixing.
  - **[MEDIUM] malformed-link** — The link text starts mid-title; 'Serverless Microservice' is outside the link and the bracketed portion starts with 'Patterns', suggesting the link anchor was split awkwardly during migration.
    - `- Serverless Microservice [Patterns for AWS - Jeremy Daly](https://www.jeremydaly.com/serverless-microservice-patterns-for-aws/) www.jeremydaly.com`
    - Fix: Wrap the full title 'Serverless Microservice Patterns for AWS - Jeremy Daly' inside the link brackets.
  - **[MEDIUM] malformed-link** — The link anchor only covers part of the title; this pattern repeats across the Yet More Links list and looks like a migration artifact that split titles.
    - `- Why does everyone hate Read Receipts? We [did some research to find out.](https://medium.com/@jameslynden/why-does-everyone-hate-read-receipts-we-did-some-research-to-find-out-11f224cd7974) medium.com`
    - Fix: Rewrap the full title as the link text.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title, leaving 'Reboot Your Dreamliner Every' as plain text outside the link.
    - `- Reboot Your Dreamliner Every [248 Days To Avoid Integer Overflow](https://www.i-programmer.info/news/149-security/8548-reboot-your-dreamliner-every-248-days-to-avoid-integer-overflow.html) www.i-programmer.info`
    - Fix: Wrap the full title in the link.
  - **[MEDIUM] malformed-link** — Only the latter half of the title is linked; first portion is orphaned plain text.
    - `- How to Manage Your Mood [by Managing Your Mind —Matt Norman](http://www.mattnorman.com/mood/) www.mattnorman.com`
    - Fix: Include the full title within the link text.
  - **[MEDIUM] malformed-link** — Link anchor is split; 'Symbol in' sits outside the bracketed title.
    - `- Symbol in [Ruby – Mehdi Farsi – Medium](https://medium.com/@farsi_mehdi/symbol-in-ruby-daca5abd4ab2) medium.com`
    - Fix: Wrap the entire title in the link brackets.
  - **[LOW] typo** — 'immediatley' is a clear misspelling of 'immediately'.
    - `puts the ebook on your phone immediatley when available`
    - Fix: Correct to 'immediately'.
  - **[LOW] narrative-break** — The markdown link brackets are interleaved with parentheses awkwardly, causing the rendered link text to include 'Solar Space War) and Turing Tumble' — clearly broken link structure from migration.
    - `[Rainy morning of Snap Circuits](https://www.elenco.com/brand/snap-circuits/) (#562 [Solar Space War) and Turing Tumble](https://www.turingtumble.com) (#18 Entanglement).`
    - Fix: Restructure so each product name is its own link without overlapping brackets, e.g., '[Snap Circuits](...) (#562 Solar Space War) and [Turing Tumble](...) (#18 Entanglement)'.

### #71 — Weekly Thing #71 / Sep 15, 2018

- Era: MailChimp
- Overall: Readable overall, but the issue has a recurring pattern of link brackets spanning sentence boundaries and list-item commentary not indented under its bullet in 'Yet More Links'.
  - **[MEDIUM] malformed-link** — The link text awkwardly spans multiple sentences, suggesting the link bracket was placed wrong — likely only 'Brandi Carlile' should be the linked text.
    - `planning a weekend away for just the two of us [in Indianapolis. Why Indianapolis? Brandi Carlile](https://www.brandicarlile.com) was playing there`
    - Fix: Rewrite so only 'Brandi Carlile' is linked, e.g., 'in Indianapolis. Why Indianapolis? [Brandi Carlile](...) was playing there'.
  - **[LOW] malformed-link** — Bracket placement makes the link text start mid-phrase; likely the author intended 'my book club' to be the link.
    - `I get some [of this through my book club](https://rwbook.club)`
    - Fix: Move the link brackets to wrap just the intended anchor text ('my book club').
  - **[LOW] malformed-link** — Link anchor spans across a sentence boundary, a recurring pattern indicating misplaced brackets.
    - `this contest they made for people to build with it is a great [idea. I downloaded Allowance for YNAB](https://itunes.apple.com/us/app/allowance-for-ynab/id1422989571?mt=8) right away`
    - Fix: Re-anchor the link to just 'Allowance for YNAB'.
  - **[LOW] malformed-link** — Link text spans a sentence boundary rather than wrapping just the call-to-action.
    - `possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Re-anchor to 'Donate to Let's Encrypt today!'.
  - **[MEDIUM] narrative-break** — In the 'Yet More Links' list, the commentary line is not indented under the bullet, so it renders as a new paragraph breaking out of the list (this pattern repeats for every bullet in the section).
    - `- Fidget spinners, weighted blankets, and the [rise of anxiety consumerism - Vox](https://www.vox.com/the-goods/2018/9/10/17826856/fidget-spinners-weighted-blankets-anxiety-products) www.vox.com
What a huge market. Seems too big. 👀`
    - Fix: Indent the commentary lines under each bullet (or add two-space line breaks) so they render as part of each list item.

### #72 — Weekly Thing #72 / Sep 22, 2018

- Era: MailChimp
- Overall: Readable issue overall; main concern is a malformed anchor in the Linus Torvalds paragraph that produces a garbled sentence, plus minor consistency and typo issues.
  - **[MEDIUM] malformed-link** — The link text awkwardly spans a sentence boundary, pulling 'Linus Torvald's' into the anchor and leaving a dangling apostrophe-s and stray space before the comma, indicating a broken link placement.
    - `Flame wars and such [got their start somewhere. Linus Torvald's](https://en.wikipedia.org/wiki/Linus_Torvalds) , the creator of Linux and Git, two of the most important software products of our era is legend`
    - Fix: Restructure so the link wraps only '[Linus Torvalds](...)' and the sentence reads naturally without the trailing possessive inside the anchor.
  - **[LOW] narrative-break** — Sentence is grammatically garbled ('two of the most important software products of our era is legend') due to the link text swallowing part of the sentence.
    - `Linus Torvald's](https://en.wikipedia.org/wiki/Linus_Torvalds) , the creator of Linux and Git, two of the most important software products of our era is legend for being a complete jerk to people.`
    - Fix: Rewrite to: 'Linus Torvalds, the creator of Linux and Git — two of the most important software products of our era — is legendary for being a jerk to people.'
  - **[LOW] other** — 'Now Reading' and 'Highlighted iOS App' are not in the canonical MailChimp-era H2 section list but are recurring sections in this era; flagged only as low-confidence deviation — likely era-normal.
    - `## Now Reading 📚`
    - Fix: No change needed if these are accepted recurring sections.
  - **[LOW] dangling-reference** — Bare Amazon URL appears above the book title with no H3 heading wrapping it, inconsistent with the pattern used elsewhere (e.g., Highlighted iOS App has both a bare URL and a following H3 link).
    - `https://www.amazon.com/Change-Your-Mind-Consciousness-Transcendence/dp/1594204225/ref=sr_1_4?s=books&ie=UTF8&qid=1537551430&sr=1-4&keywords=how+to+change+your+mind`
    - Fix: Either remove the bare URL or convert the book title to a proper H3 linked heading for consistency.
  - **[LOW] typo** — 'Its' should be 'It's' (contraction of 'it has').
    - `Its also been going on for over 10 years?`
    - Fix: Change 'Its' to 'It's'.

### #73 — Weekly Thing #73 / Sep 29, 2018

- Era: MailChimp
- Overall: Readable but unusually messy for a MailChimp-era issue — multiple link-bracket boundaries are broken in both Notable Links and Yet More Links, the 'My Blog Posts' H2 is missing, and there's a stray duplicate caption and URL.
  - **[MEDIUM] header-error** — 'My Blog Posts ✍️' is written as plain text rather than as an H2 header, causing the following H3 'Goodbye Chase' to be an orphan subheading (as the static audit noted).
    - `My Blog Posts ✍️

### [Goodbye Chase](https://www.thingelstad.com/2018/goodbye-chase/)`
    - Fix: Change 'My Blog Posts ✍️' to '## My Blog Posts ✍️' so the H3 has a proper parent H2.
  - **[HIGH] malformed-link** — The link brackets clearly span the wrong text — 'Ben Brooks' should link to Brooks, and '1Blocker X' should link to 1blocker; similarly 'BlockBear' should be the linked term, not 'custom blocker rules. I've tried BlockBear'.
    - `Like [Ben Brooks I use 1Blocker X](https://1blocker.com) on all of my iOS and macOS devices. I love how powerful it is and that I can create my own [custom blocker rules. I've tried BlockBear](https://blockbear.com)`
    - Fix: Rewrite as 'Like Ben Brooks I use [1Blocker X](https://1blocker.com)...I can create my own custom blocker rules. I've tried [BlockBear](https://blockbear.com)'.
  - **[HIGH] malformed-link** — The link text boundaries are broken — punctuation ('. ') is inside the anchor text of the second link, producing visibly malformed link text like '. "Don't be evil."'.
    - `Matthew Greene has a more direct reaction to [this, and is done with Chrome](https://blog.cryptographyengineering.com/2018/09/23/why-im-leaving-chrome/) [. "Don't be evil."](https://en.wikipedia.org/wiki/Don't_be_evil)`
    - Fix: Rewrite so the anchor text is just 'this' and '"Don't be evil."' with the period outside the brackets.
  - **[HIGH] malformed-link** — 'Don't be evil.' appears as a second standalone H3 but is clearly meant to be inline commentary following the Google Intercept link, not a separate link entry.
    - `### [Google Suppresses Memo Revealing Plans to Closely Track Search Users in China](https://theintercept.com/2018/09/21/google-suppresses-memo-revealing-plans-to-closely-track-search-users-in-china/)

### [“Don't be evil.”](https://en.wikipedia.org/wiki/Don%27t_be_evil)`
    - Fix: Merge the '"Don't be evil."' link into the prose of the preceding item rather than leaving it as a standalone H3.
  - **[MEDIUM] narrative-break** — The line 'Rose in the Lyndale Park Rose Garden.' is a duplicate of the image alt text and appears as orphaned caption text — likely a migration artifact from a photo-metadata block.
    - `![Rose in the Lyndale Park Rose Garden.](https://files.thingelstad.com/weekly-thing/73/cover.jpg)

Blooming Rose 🌹 [in the Lyndale Park Rose Garden](https://www.minneapolisparks.org/parks__destinations/gardens__bird_sanctuaries/lyndale_park_rose_garden/) .

Rose in the Lyndale Park Rose Garden.`
    - Fix: Remove the duplicated 'Rose in the Lyndale Park Rose Garden.' line or format the Sep 23/location info as a proper caption.
  - **[MEDIUM] malformed-link** — Link text boundaries are wrong — the title is split so the anchor begins mid-phrase at 'Use iPhone's', leaving dangling 'Hey Siri, Drive My Tesla (How To' outside the link.
    - `- Hey Siri, Drive My Tesla (How To [Use iPhone's New Shortcuts)! - YouTube](https://www.youtube.com/watch?v=jZc8qMNiONo&app=desktop) www.youtube.com`
    - Fix: Wrap the entire title as the link text: '[Hey Siri, Drive My Tesla (How To Use iPhone's New Shortcuts)! - YouTube](...)'.
  - **[MEDIUM] malformed-link** — The title is split with only the tail portion inside the link, leaving 'Walmart Requires Lettuce, Spinach Suppliers to Join' as unlinked prose.
    - `- Walmart Requires Lettuce, Spinach Suppliers to Join [Blockchain - CIO Journal. - WSJ](https://blogs.wsj.com/cio/2018/09/24/walmart-requires-lettuce-spinach-suppliers-to-join-blockchain/) blogs.wsj.com`
    - Fix: Wrap the full title in the link brackets.
  - **[MEDIUM] malformed-link** — The anchor text excludes 'macOS', splitting the title awkwardly across unlinked and linked text.
    - `- macOS [Mojave: The MacStories Review – MacStories](https://www.macstories.net/stories/macos-mojave-the-macstories-review/) www.macstories.net`
    - Fix: Wrap the full title in the link brackets.
  - **[MEDIUM] malformed-link** — Link brackets begin mid-title, leaving the first half of the headline unlinked.
    - `- Apple and Salesforce partner to help redefine [customer experiences on iOS - Apple](https://www.apple.com/newsroom/2018/09/apple-and-salesforce-partner-to-help-redefine-customer-experiences-on-ios/) www.apple.com`
    - Fix: Wrap the entire headline inside the link.
  - **[MEDIUM] malformed-link** — This Forbes item is missing the H3 header prefix and its link only wraps the tail of the title, making it appear as body prose rather than a section entry like the surrounding Notable Links.
    - `Exclusive: WhatsApp Cofounder Brian Acton Gives The Inside Story On #DeleteFacebook And [Why He Left $850 Million Behind](https://www.forbes.com/sites/parmyolson/2018/09/26/exclusive-whatsapp-cofounder-brian-acton-gives-the-inside-story-on-deletefacebook-and-why-he-left-850-million-behind/#53b644b63f20)`
    - Fix: Add '### ' and wrap the full Forbes title inside the link brackets.
  - **[LOW] other** — A bare URL 'https://archive.org' appears on its own line immediately before the paragraph, a leftover/duplicate reference since the linked '[Internet Archive](https://archive.org)' is in the following sentence.
    - `## Give Back 🎁

https://archive.org`
    - Fix: Remove the stray 'https://archive.org' line.
  - **[LOW] typo** — 'Wether' should be 'Whether'.
    - `Wether it is Instagram or WhatsApp`
    - Fix: Change 'Wether' to 'Whether'.

### #74 — Weekly Thing #74 / Oct 6, 2018

- Era: MailChimp
- Overall: Readable overall, but the 'Yet More Links' and 'Give Back' sections have multiple misplaced link brackets and the Weekly Photo caption contains an encoded-URL artifact that should be cleaned up.
  - **[HIGH] migration-artifact** — URL-encoded curly quotes wrap a URL in a broken parenthetical, showing as raw %E2%80%9C characters—clearly a migration artifact.
    - `Pumpkins at Fireside Orchard (%E2%80%9Chttp://www.firesideorchard.com%E2%80%9D) .`
    - Fix: Remove the broken encoded fragment or replace it with a proper link to firesideorchard.com.
  - **[MEDIUM] narrative-break** — The link's anchor text spans across a sentence boundary, which indicates a misplaced bracket from the migration; the link should wrap 'ping' not 'people now? What is this ping'.
    - `Wait, there is an HTML attribute just to spy on [people now? What is this ping](https://www.w3.org/TR/2010/WD-html5-20100304/interactive-elements.html#hyperlink-auditing) !`
    - Fix: Restructure so only 'ping' (or similar) is the link anchor.
  - **[MEDIUM] narrative-break** — The link anchor text starts mid-sentence ('years. Donate...'), indicating a misplaced opening bracket.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the opening bracket so only 'Donate to Let's Encrypt today!' is the link anchor.
  - **[MEDIUM] narrative-break** — Link anchor begins mid-phrase; the title should be the entire item, not just 'water damage — Apple World Today'.
    - `Fibaro HomeKit-enabled Flood Sensor can minimize costly [water damage — Apple World Today](https://www.appleworld.today/blog/2018/9/28/fibaro-homekit-enabled-flood-sensor-can-minimize-costly-water-damage)`
    - Fix: Reformat so the full title is the link anchor at the start of the bullet.
  - **[MEDIUM] narrative-break** — Anchor text splits the article title awkwardly—likely a migration artifact where the bracket was misplaced.
    - `The design and implementation of modern column-oriented [database systems | the morning paper](https://blog.acolyer.org/2018/09/26/the-design-and-implementation-of-modern-column-oriented-database-systems/)`
    - Fix: Make the whole article title the link anchor.
  - **[MEDIUM] narrative-break** — Link anchor starts mid-headline; common pattern of bracket placement error in this section.
    - `SEC charges [Tesla CEO Elon Musk with fraud](https://www.cnbc.com/2018/09/27/tesla-falls-4percent-on-report-elon-musk-sued-by-sec.html)`
    - Fix: Place the opening bracket at the start of the headline.
  - **[MEDIUM] narrative-break** — Link anchor begins mid-title, indicating misplaced bracket.
    - `Building With Workers KV, a [Fast Distributed Key-Value Store — Cloudflare](https://blog.cloudflare.com/building-with-workers-kv/)`
    - Fix: Wrap the whole title in the link anchor.
  - **[LOW] typo** — 'blog their trackers' should be 'block their trackers'—a clear word substitution typo.
    - `I don’t store any private data with Google and blog their trackers.`
    - Fix: Change 'blog' to 'block'.

### #75 — Weekly Thing #75 / Oct 13, 2018

- Era: MailChimp
- Overall: Readable overall but the introduction and nearly every 'Yet More Links' bullet contain misplaced markdown link brackets that split titles/sentences awkwardly — an editor pass on link anchors is warranted.
  - **[HIGH] malformed-link** — The link anchor text incorrectly starts with 'sure' — the markdown link bracket was placed wrong, so it reads 'For sure School of Rock' instead of 'For sure, School of Rock: The Musical'.
    - `For [sure School of Rock: The Musical](https://schoolofrockthemusical.com) was a big highlight for her.`
    - Fix: Rewrite as 'For sure, [School of Rock: The Musical](https://schoolofrockthemusical.com) was a big highlight for her.'
  - **[HIGH] malformed-link** — Link anchor bracket is misplaced, breaking the phrase 'Weekly Thing' across the link boundary.
    - `I also want to welcome a group of subscribers that discovered the Weekly [Thing via Azeem Azhar's Exponential View](https://www.exponentialview.co)`
    - Fix: Adjust the brackets so the link reads naturally, e.g. 'discovered the Weekly Thing via [Azeem Azhar's Exponential View](https://www.exponentialview.co)'.
  - **[MEDIUM] malformed-link** — Link anchor brackets start mid-title, splitting the article title awkwardly; the same pattern repeats across every bullet in 'Yet More Links'.
    - `- Rosie Pattern Language: Improving on 50-year Old [Regular Expression Technology - Strange Loop](https://thestrangeloop.com/2018/rosie-pattern-language-improving-on-50-year-old-regular-expression-technology.html) thestrangeloop.com`
    - Fix: Move the opening bracket to the start of each article title so the full title is the link text.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title, splitting the article title in the middle.
    - `- The Pixel 3: Everything You Need [To Know About Google's New Phone](https://www.buzzfeednews.com/article/nicolenguyen/pixel-3-price-google-hands-on) www.buzzfeednews.com`
    - Fix: Wrap the entire article title in the link brackets.
  - **[MEDIUM] malformed-link** — Title split mid-phrase by link brackets; also link points to Twitter while the displayed title says 'Daring Fireball'.
    - `- Latest Revision to ARM Instruction Set Includes Optimizations [Just for JavaScript — Daring Fireball](https://twitter.com/gparker/status/1047246359261106176) twitter.com`
    - Fix: Wrap the full title in the link and verify the intended URL.
  - **[MEDIUM] malformed-link** — Link anchor starts mid-title, splitting the title text.
    - `- Scaling Engineering Teams via Writing Things [Down and Sharing - aka RFCs](https://blog.pragmaticengineer.com/scaling-engineering-teams-via-writing-things-down-rfcs/) blog.pragmaticengineer.com`
    - Fix: Expand the bracketed anchor to include the full title.
  - **[MEDIUM] malformed-link** — Sentence boundary falls inside the link anchor, producing awkward link text spanning two sentences.
    - `Mazie and I returned home from our Daddy/Daughter trip to [NYC. We brought a Birthday Cake](https://milkbarstore.com/recipes/birthday-cake/) from Milk Bar home for everyone.`
    - Fix: Restrict the link anchor to 'Birthday Cake' (or similar) rather than spanning a period.
  - **[LOW] other** — Likely missing article 'an' before 'angry heart' — the common phrasing is 'an angry heart'.
    - `Never let the sun set on angry heart.`
    - Fix: Consider 'Never let the sun set on an angry heart.'

### #76 — Weekly Thing #76 / Oct 20, 2018

- Era: MailChimp
- Overall: Content is intact and readable, but the issue has an unusually high number of malformed markdown links where anchor text spans sentence/clause boundaries — likely a migration or editor artifact worth a cleanup pass.
  - **[HIGH] malformed-link** — Link text spans sentence boundaries — the anchor text should be just 'Dave Grohl' and 'Taylor Hawkins' but swallowed preceding prose.
    - `Every time I’m struck by how much [they just love music. Dave Grohl](https://en.wikipedia.org/wiki/Dave_Grohl) seems like someone that is all consumed and in [love with his craft. Taylor Hawkins](https://en.wikipedia.org/wiki/Taylor_Hawkins)`
    - Fix: Rewrap the links so only the names are the hyperlink text, e.g., 'they just love music. [Dave Grohl](…) seems like…' and '[Taylor Hawkins](…) has a grin…'.
  - **[HIGH] malformed-link** — The link brackets are split across the song title and author, producing nonsensical anchor text with a stray quote bracket.
    - `Tonight they played “Breakdown](https://www.youtube.com/watch?v=qNxfPAF1frM) [” by Tom Petty](https://en.wikipedia.org/wiki/Tom_Petty)`
    - Fix: Rewrite as 'Tonight they played [“Breakdown”](https://www.youtube.com/watch?v=qNxfPAF1frM) by [Tom Petty](https://en.wikipedia.org/wiki/Tom_Petty)'.
  - **[MEDIUM] malformed-link** — Anchor text swallows surrounding prose instead of linking only 'GTD' and 'OmniFocus'.
    - `One of the best things I ever did [was decide to commit to GTD](https://www.gettingthingsdone.com) as a [long-term investment as well as OmniFocus](https://www.omnigroup.com/omnifocus)`
    - Fix: Reformat so only product names are linked: 'commit to [GTD](…) as a long-term investment as well as [OmniFocus](…)'.
  - **[MEDIUM] malformed-link** — Link text inappropriately includes 'and recharge. Link from' — only 'Tor Flatebo' should be the anchor.
    - `disconnect [and recharge. Link from Tor Flatebo](https://www.linkedin.com/in/torflatebo/) .`
    - Fix: Rewrite as 'disconnect and recharge. Link from [Tor Flatebo](…).'
  - **[MEDIUM] malformed-link** — Link text fragments span clause boundaries; anchor text should be just the object names ('microblog', 'linkblog', 'blog').
    - `[One may note that my microblog](https://www.thingelstad.com) [and linkblog](https://links.thingelstad.com) are [both very active while my blog](https://www.thingelstad.com) is pretty quiet.`
    - Fix: Restructure to link just the nouns: 'my [microblog](…) and [linkblog](…) are both very active while my [blog](…) is pretty quiet'.
  - **[MEDIUM] malformed-link** — Link text crosses sentence boundary; only 'Forestry' should be the hyperlink.
    - `That is almost entirely because writing for Jekyll, the static site generator I use, [is too hard. Tools like Forestry](https://forestry.io) offer some hope`
    - Fix: Rewrite as 'is too hard. Tools like [Forestry](https://forestry.io) offer some hope…'.
  - **[MEDIUM] malformed-link** — Link brackets break awkwardly across clauses, and there is a stray space before the comma.
    - `I [serve on the board of Minnestar](https://minnestar.org) [with Jenna Pederson](https://twitter.com/jennapederson) , one of the founders of Hack the Gap`
    - Fix: Rewrite so only 'Minnestar' and 'Jenna Pederson' are the anchors and remove the space before the comma.
  - **[MEDIUM] malformed-link** — Link anchor text starts mid-title rather than wrapping the whole item title, leaving 'Announcing Camelot, a Python Library to Extract' unlinked.
    - `- Announcing Camelot, a Python Library to Extract [Tabular Data from PDFs - SocialCops](https://blog.socialcops.com/technology/engineering/camelot-python-library-pdf-data/) blog.socialcops.com`
    - Fix: Wrap the entire title in the link: '[Announcing Camelot, a Python Library to Extract Tabular Data from PDFs - SocialCops](…)'.
  - **[MEDIUM] malformed-link** — Only a fragment of the project description is linked; title 'birdseye' and leading description are unlinked.
    - `- birdseye: Quick, convenient, expression-centric, [graphical Python debugger using the AST](https://github.com/alexmojaki/birdseye) github.com`
    - Fix: Wrap the full title in the link anchor.
  - **[MEDIUM] malformed-link** — The word 'Fake' is orphaned outside the link; anchor text should be the full title.
    - `- Fake [Followers Audit from SparkToro | SparkToro](https://sparktoro.com/tools/fake-followers-audit) sparktoro.com`
    - Fix: Move 'Fake' inside the link brackets: '[Fake Followers Audit from SparkToro | SparkToro](…)'.
  - **[MEDIUM] malformed-link** — Stray space between the link and the exclamation point, and anchor text swallows prose that shouldn't be linked.
    - `We had a great [morning exploring the Franconia Sculpture Park](http://www.franconia.org) !`
    - Fix: Rewrite as 'We had a great morning exploring the [Franconia Sculpture Park](http://www.franconia.org)!'
  - **[LOW] malformed-link** — Anchor text swallows prose; only 'Kitchen Window' should be linked.
    - `Had a fun [and delicious evening at Kitchen Window’s](https://kitchenwindow.com) Spanish Wine Dinner Class last night.`
    - Fix: Rewrite so the link wraps just the business name.
  - **[LOW] malformed-link** — Anchor text begins with 'is created by' instead of limiting to the organization name.
    - `It [is created by Passion for Pumpkins](http://passionforpumpkins.com/photo-gallery/) with 5,000 pumpkins!`
    - Fix: Rewrite as 'It is created by [Passion for Pumpkins](…) with 5,000 pumpkins!'
  - **[LOW] typo** — 'we’re' should be 'were' — the subject is the band, not first-person, and the tense is past.
    - `Once I saw them play for over 2 hours straight and we’re ready to keep going.`
    - Fix: Change 'we’re' to 'were'.
  - **[LOW] typo** — Capitalization typo: 'WIth' should be 'With'.
    - `WIth this Portal surveillance device`
    - Fix: Correct to 'With'.

### #77 — Weekly Thing #77 / Oct 27, 2018

- Era: MailChimp
- Overall: Readable overall, but the Microposts section contains a badly mangled Mölkky link and the My Weekly Photo section has a duplicated caption line; a couple of 'Yet More Links' entries also have brackets placed mid-title.
  - **[HIGH] malformed-link** — The Mölkky link is badly mangled with URL-encoded brackets and a broken nested markdown link structure, rendering as garbled text instead of a clean link.
    - `[Fun (and chilly!) day playing Kubb](https://en.wikipedia.org/wiki/Kubb) and Mölkky (%5Ben.wikipedia.org/wiki/M%5D(https://en.wikipedia.org/wiki/M)%C3%B6lkky)`
    - Fix: Replace with a proper markdown link: [Mölkky](https://en.wikipedia.org/wiki/M%C3%B6lkky).
  - **[MEDIUM] narrative-break** — The caption sentence is duplicated — it appears once as a full paragraph and then again as a stray line before the date/location metadata.
    - `During blustery fall days the autumn leaves cling to the trees, flapping in the wind. You can hear them crinkle as they blur into a rusty orange pile on the ground. 🍁

During blustery fall days the autumn leaves cling to the trees, flapping in the wind.
Oct 20, 2018 at 12:40 PM`
    - Fix: Remove the duplicated caption line so only the date and location appear as metadata after the descriptive paragraph.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-title after 'Father of ', so the anchor text is a truncated fragment rather than the full article title.
    - `- How Google Protected Andy Rubin, the ‘Father of [Android’ - The New York Times](https://www.nytimes.com/2018/10/25/technology/google-sexual-harassment-andy-rubin.html) www.nytimes.com`
    - Fix: Move the opening bracket to the start of the title: [How Google Protected Andy Rubin, the 'Father of Android' - The New York Times](...).
  - **[LOW] malformed-link** — Link anchor text starts with a pipe character because the bracket was placed mid-title, producing awkward rendered text.
    - `- Trek10 [| The Business Case For Serverless](https://www.trek10.com/blog/business-case-for-serverless/)`
    - Fix: Rebracket to include the full title, e.g. [Trek10 | The Business Case For Serverless](...).
  - **[LOW] typo** — Stray word 'a' before 'we' — likely a leftover from editing.
    - `It looks like a we are getting on this train!`
    - Fix: Remove 'a': 'It looks like we are getting on this train!'
  - **[LOW] other** — Empty parentheses after the book title suggest a template field (author/year) that did not populate.
    - `Life After Google: The Fall of Big Data and the Rise of the Blockchain Economy ()`
    - Fix: Either remove the empty parentheses or fill in the intended metadata.

### #78 — Weekly Thing #78 / Nov 3, 2018

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but several Give Back/Microposts links have misplaced anchor boundaries that an editor should tighten.
  - **[HIGH] malformed-link** — The link boundaries are misplaced — the link text spans across a sentence break, so 'years.' is incorrectly part of the link anchor rather than plain prose.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Rewrite as '...in recent years. [Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)' so the link wraps only the call-to-action.
  - **[MEDIUM] malformed-link** — The anchor text swallows the entire sentence including 'found my trick-or-treat!' when the link should only be on the @ajdomie handle.
    - `I [found my trick-or-treat! 🍺 Thanks @ajdomie](https://twitter.com/ajdomie) ! White Oak Jai Alai IPA – such a great IPA!`
    - Fix: Restrict the link to the handle, e.g., 'I found my trick-or-treat! 🍺 Thanks [@ajdomie](https://twitter.com/ajdomie)!'
  - **[MEDIUM] malformed-link** — The link anchor awkwardly breaks the sentence, linking 'Whiskey, and Scotch with Rich Howard' to a Twitter profile instead of just the person's name.
    - `Had a fabulous evening learning and tasting Bourbons, [Whiskey, and Scotch with Rich Howard](https://twitter.com/scotchprophet) tonight! 🥃`
    - Fix: Link only the person's name, e.g., '...Bourbons, Whiskey, and Scotch with [Rich Howard](https://twitter.com/scotchprophet) tonight!'
  - **[LOW] other** — A bare URL appears on its own line immediately above the same link as markdown, likely a migration/formatting artifact.
    - `## Give Back 🎁

https://letsencrypt.org

[Let's Encrypt](https://letsencrypt.org)`
    - Fix: Remove the stray bare URL line so only the prose paragraph remains.

### #79 — Weekly Thing #79 / Nov 10, 2018

- Era: MailChimp
- Overall: Issue is readable and well-structured; main issues are several Notable/Yet More Links entries where markdown link anchors were placed mid-phrase, plus a name typo ('Gloms' vs 'Glomb').
  - **[MEDIUM] malformed-link** — Link text boundaries are awkwardly placed mid-sentence, making the rendered links read strangely (e.g., '[internet property. Donate to Wikimedia today!]' as one link).
    - `operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Rework the link anchors to more natural phrases like 'Wikipedia' and 'Donate to Wikimedia today' placed at natural word boundaries.
  - **[LOW] malformed-link** — Link anchor starts mid-phrase; 'The Verge Holiday' is outside the link while it should logically be part of the title.
    - `- The Verge Holiday [Gift Guide 2018 - The Verge](https://www.theverge.com/2018/11/5/18039736/holiday-gift-ideas-2018-christmas-hannukah-guide) www.theverge.com`
    - Fix: Move the opening bracket to include 'The Verge Holiday Gift Guide 2018' as the link text.
  - **[LOW] malformed-link** — Link anchor starts mid-sentence rather than covering the full headline.
    - `- Citi's Mark May: Amazon relies [on robots; less temporary holiday hires](https://www.cnbc.com/2018/11/02/citi-mark-may-amazon-relies-on-robots-less-temporary-holiday-hires.html)`
    - Fix: Adjust bracket placement so the full article title is the link text.
  - **[LOW] malformed-link** — Link anchor covers only the trailing phrase instead of the product/title.
    - `- Statamic - Make better, easier to manage websites. Enjoy [simplicity like the days of summer.](https://statamic.com/) statamic.com`
    - Fix: Move brackets so 'Statamic' or the full tagline is the link text.
  - **[LOW] typo** — Name is misspelled; the section heading and link show 'Theresa Glomb'.
    - `Dr. Theresa Gloms presented at our company Growth Summit`
    - Fix: Change 'Gloms' to 'Glomb'.
  - **[LOW] narrative-break** — Sentence has a grammatical glitch ('developers are just aren't') that reads like a missed edit.
    - `I would highlight that there are a lot of developers are just aren't all that great at being on-call.`
    - Fix: Change to 'there are a lot of developers who just aren't all that great at being on-call.'

### #80 — Weekly Thing #80 / Nov 17, 2018

- Era: MailChimp
- Overall: Issue is readable and era-normal overall, but contains several split/malformed links (especially in Yet More Links and Give Back) and recurring spacing artifacts around link punctuation that an editor should clean up.
  - **[MEDIUM] malformed-link** — The link bracketing is broken — the period and space are inside the link text of the second link, producing awkward rendering where ". The privacy policy" becomes the link text.
    - `This looks like a simple, fast, and easy solution for doing polls, so you can [ask people all sorts of questions](https://fast-poll.com/poll/94d6b1c0) [. The privacy policy](https://fast-poll.com/privacy/) looks reasonably friendly.`
    - Fix: Restructure to: "...[ask people all sorts of questions](https://fast-poll.com/poll/94d6b1c0). The [privacy policy](https://fast-poll.com/privacy/) looks reasonably friendly."
  - **[MEDIUM] malformed-link** — The link text was split mid-title so only "Crisis - The New York Times" is linked while the beginning of the title is plain text — a common migration artifact in this Yet More Links section.
    - `- Delay, Deny and Deflect: How Facebook’s Leaders Fought Through [Crisis - The New York Times](https://www.nytimes.com/2018/11/14/technology/facebook-data-russia-election-racism.html) www.nytimes.com`
    - Fix: Wrap the entire title in the link: [Delay, Deny and Deflect: How Facebook's Leaders Fought Through Crisis - The New York Times](...).
  - **[MEDIUM] malformed-link** — Only the tail of the title is a link; the beginning of the title is plain text due to a split link.
    - `- Mosaic Versions | National Center for Supercomputing Applications [(NCSA) at the University of Illinois](http://www.ncsa.illinois.edu/enabling/mosaic/versions) www.ncsa.illinois.edu`
    - Fix: Wrap the full title in the markdown link.
  - **[MEDIUM] malformed-link** — Split link: only the parenthetical/author portion is the hyperlink, leaving the main title unlinked.
    - `- Front-end Web Development on iPad Pro [(2018) – Craig Morey – Medium](https://medium.com/@pixelthing/fe-webdev-on-ipad-pro-2018-c55283f01e4c) medium.com`
    - Fix: Make the full title the link text.
  - **[LOW] malformed-link** — The link text starts with "license." making the sentence read oddly — the period is inside the anchor and the word "license" was pulled into the link.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Rephrase to close the preceding sentence and link just "Donate to Creative Commons today!".
  - **[LOW] narrative-break** — Multiple instances throughout the issue of a stray space before a comma or period after a closing link paren — a consistent migration artifact.
    - `[I've been traveling in Kiev](https://en.wikipedia.org/wiki/Kiev) , Ukraine this week.`
    - Fix: Remove the extraneous spaces between closing link parentheses and following punctuation.

### #81 — Weekly Thing #81 / Nov 24, 2018

- Era: MailChimp
- Overall: The issue is readable overall, but several links in the intro and in the Notable/Yet More Links sections have misplaced anchor brackets that look like migration artifacts and should be rewrapped.
  - **[HIGH] malformed-link** — The link text incorrectly spans across what should be two separate ideas ('Christmas Music' and 'watching Elf'), making the linked phrase read as a single awkward clause pointing only to the Elf Wikipedia page.
    - `listening to Christmas [Music 🎶, and eventually watching Elf](https://en.wikipedia.org/wiki/Elf_(film)) 🎬!`
    - Fix: Move the link brackets to wrap only 'Elf' (or 'watching Elf') so the sentence reads naturally: 'listening to Christmas Music 🎶, and eventually watching [Elf](...)'.
  - **[HIGH] malformed-link** — The link text brackets are misplaced — 'Via Leah Cunningham' is swept into the link text along with 'the basic terms', and the Kubernetes link anchor text awkwardly overshoots, suggesting broken link-wrapping from migration.
    - `This is a very easy to understand breakdown [of the basic components of Kubernetes](https://kubernetes.io) . It’s a good read if you are just trying to ground yourself with [the basic terms. Via Leah Cunningham](https://www.linkedin.com/in/leahcunningham/) .`
    - Fix: Rewrap so only relevant phrases are linked, e.g. link 'Kubernetes' to kubernetes.io and make 'Leah Cunningham' the only linked text for the LinkedIn URL.
  - **[MEDIUM] malformed-link** — Across the Yet More Links list, brackets consistently wrap only a fragment of the title with the bare domain trailing after the link — indicating migration-mangled link anchors (same pattern in Mini Kubb, Chartify, Camp Fire, Icosahedral Puzzle entries).
    - `- If you want to understand Silicon Valley, [watch Silicon Valley | Bill Gates](https://www.gatesnotes.com/About-Bill-Gates/Silicon-Valley) www.gatesnotes.com`
    - Fix: Rewrap each bullet so the full article title is the link text and remove the trailing bare domain, e.g. '[watch Silicon Valley | Bill Gates](...)'.
  - **[LOW] typo** — 'bully doing' is a clear typo for 'by doing'.
    - `Shortcuts is one of those tools that is best learned bully doing`
    - Fix: Change 'bully doing' to 'by doing'.
  - **[LOW] typo** — Subject-verb agreement error ('band no longer compete' should be 'competed' in this past-tense quoted passage).
    - `that band no longer compete with the entire internet`
    - Fix: If this is a direct quotation, verify against the source; otherwise correct to 'competed'.

### #82 — Weekly Thing #82 / Dec 1, 2018

- Era: MailChimp
- Overall: Readable and content-complete, but the Yet More Links section and a few inline links suffer from a systematic migration artifact where link anchors start mid-title, and two 'word.aword' typos appear.
  - **[HIGH] malformed-link** — The list marker '1.' was accidentally pulled into the link text, so item 1 renders as a hyperlink starting with '1.' rather than a numbered list item with an inline link.
    - `[1. Curious to see BetterWorks](https://www.betterworks.com) highlighted. They seem to show up in this topic more than most.`
    - Fix: Rewrite as '1. Curious to see [BetterWorks](https://www.betterworks.com) highlighted...' to restore the list numbering and proper link anchor.
  - **[MEDIUM] malformed-link** — The link text awkwardly spans a sentence boundary ('evolves and grows. Via Juselly French'), likely a migration artifact where only 'Juselly French' should be linked.
    - `Good things to consider as your organization [evolves and grows. Via Juselly French](https://www.linkedin.com/in/jusellyfrench/) .`
    - Fix: Restrict the link to the name: 'evolves and grows. Via [Juselly French](https://www.linkedin.com/in/jusellyfrench/).'
  - **[MEDIUM] malformed-link** — Link text spans a sentence boundary ('years. Donate to Let's Encrypt today!'), a migration artifact where only the call-to-action should be linked.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Close the previous sentence and link only the CTA: '...in recent years. [Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)'
  - **[MEDIUM] malformed-link** — The link anchor starts mid-title at 'Code (Preview)', leaving the first part of the headline as plain text — a recurring migration artifact in the Yet More Links section.
    - `- AWS Toolkits for PyCharm, IntelliJ (Preview), and Visual Studio [Code (Preview) | AWS News Blog](https://aws.amazon.com/blogs/aws/new-aws-toolkits-for-pycharm-intellij-preview-and-visual-studio-code-preview/) aws.amazon.com`
    - Fix: Wrap the full title in the link: '[AWS Toolkits for PyCharm, IntelliJ (Preview), and Visual Studio Code (Preview) | AWS News Blog](...)'.
  - **[MEDIUM] malformed-link** — The link text begins mid-title ('games, from Guess Who to Catan.') leaving 'The 40 greatest family' unlinked.
    - `- The 40 greatest family [games, from Guess Who to Catan.](https://slate.com/human-interest/2018/11/best-family-games-list-catan-sushi-go-codenames.html) slate.com`
    - Fix: Wrap the full title in the link anchor.
  - **[MEDIUM] malformed-link** — Link starts mid-title, leaving 'Amazon CloudWatch Logs Insights – Fast, Interactive' unlinked — migration artifact.
    - `- Amazon CloudWatch Logs Insights – Fast, Interactive [Log Analytics | AWS News Blog](https://aws.amazon.com/blogs/aws/new-amazon-cloudwatch-logs-insights-fast-interactive-log-analytics/) aws.amazon.com`
    - Fix: Extend the link anchor to cover the full title.
  - **[MEDIUM] malformed-link** — The SumoLogic link anchor incorrectly includes the preceding phrase 'log analytics better. Companies like', producing a nonsensical link span.
    - `Amazon will continue to make [log analytics better. Companies like SumoLogic](https://www.sumologic.com) [and even Splunk](https://www.splunk.com)`
    - Fix: Restrict the anchor to 'SumoLogic': 'Companies like [SumoLogic](https://www.sumologic.com) and even [Splunk](https://www.splunk.com)...'
  - **[MEDIUM] malformed-link** — The link starts mid-title, leaving 'Introducing AWS App Mesh -' outside the anchor.
    - `- Introducing AWS App Mesh - [Service Mesh for Microservices on AWS](https://aws.amazon.com/about-aws/whats-new/2018/11/introducing-aws-app-mesh---service-mesh-for-microservices-on-aws/) aws.amazon.com`
    - Fix: Extend the link to cover the entire headline.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title at 'a MacBook Air', leaving 'Ditching the MacBook Pro for' unlinked.
    - `- Ditching the MacBook Pro for [a MacBook Air | Brad Frost](http://bradfrost.com/blog/post/ditching-the-macbook-pro-for-a-macbook-air/) bradfrost.com`
    - Fix: Wrap the full headline in the link.
  - **[MEDIUM] malformed-link** — Link starts mid-title, leaving 'Best EDI Software | 2018' as plain text.
    - `- Best EDI Software | 2018 [Reviews of the Most Popular Systems](https://www.capterra.com/edi-software/#infographic) www.capterra.com`
    - Fix: Extend the anchor to cover the full title.
  - **[MEDIUM] malformed-link** — The opening curly quote is swallowed into the link text while the closing quote and exclamation sit outside, producing odd rendering.
    - `[“Announcing AWS Lake Formation](https://aws.amazon.com/lake-formation/) !” — “Sounds glacial!” 🤣`
    - Fix: Move the opening quote outside the link: '“[Announcing AWS Lake Formation](...)!” — “Sounds glacial!”'
  - **[LOW] typo** — 'after.a' is a clear typo — a period appears where a space should be between 'after' and 'a'.
    - `It didn’t surprise me to hear that after.a 10 year run she's stepping aside.`
    - Fix: Replace 'after.a' with 'after a'.
  - **[LOW] typo** — 'like.a' has a period instead of a space — a clear typo.
    - `This looks like.a very well done and comprehensive guide.`
    - Fix: Change 'like.a' to 'like a'.

### #83 — Weekly Thing #83 / Dec 8, 2018

- Era: MailChimp
- Overall: Content is intact and readable, but the issue has a recurring pattern of misplaced Markdown link boundaries (link text beginning mid-sentence) throughout the Notable Links and Yet More Links sections, plus one small typo.
  - **[MEDIUM] malformed-link** — The link text awkwardly starts mid-sentence ('it sinks in. Via Leah Cunningham'), suggesting the link boundary was misplaced during migration — only 'Via Leah Cunningham' should be the link.
    - `This is worth reading a few times, just to make sure [it sinks in. Via Leah Cunningham](https://www.linkedin.com/feed/update/urn:li:activity:6474770166122102784)`
    - Fix: Restructure so only the attribution ('Via Leah Cunningham') is the linked text, e.g., 'just to make sure it sinks in. [Via Leah Cunningham](...)'.
  - **[MEDIUM] malformed-link** — The link text spans mid-phrase ('to me that I'm a Headspace'), indicating a misplaced link boundary — only 'Headspace' should be linked.
    - `It's crazy [to me that I'm a Headspace](https://www.headspace.com) subscriber but didn't know that there was a book!`
    - Fix: Reformat so only 'Headspace' is the link text.
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence; likely only 'Via Kottke.org' should be linked.
    - `What awesome pictures – [they crack me up! Via Kottke.org](https://kottke.org/18/11/dogs-catching-treats)`
    - Fix: Restructure to 'they crack me up! [Via Kottke.org](...)'.
  - **[MEDIUM] malformed-link** — The link text starts mid-sentence ('years. Donate...'), indicating a misplaced link boundary.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Restructure so only the call-to-action ('Donate to Let's Encrypt today!') is the link text.
  - **[LOW] malformed-link** — Link boundary begins mid-title; only part of the article title is hyperlinked.
    - `- Day One Version 3.4: Drawing, Fonts, [and Photo Layout | Day One](http://dayoneapp.com/2018/12/version-3-4/) dayoneapp.com`
    - Fix: Make the entire title ('Day One Version 3.4: Drawing, Fonts, and Photo Layout | Day One') the link text.
  - **[LOW] malformed-link** — Link title starts mid-phrase, leaving 'Fujitsu' outside the hyperlink.
    - `- Fujitsu [ScanSnap 64-bit Software Update — macsparky](https://www.macsparky.com/blog/2018/12/fujitsu-scansnap-64-bit-software-update)`
    - Fix: Include 'Fujitsu' inside the link text.
  - **[LOW] malformed-link** — The link text starts mid-title, leaving the beginning of the article title unlinked.
    - `- Show your skills with Pokémon [GO Trainer Battles! - Pokémon GO](https://pokemongolive.com/post/trainerbattles)`
    - Fix: Link the full title.
  - **[LOW] malformed-link** — Link text begins mid-title; 'Apple presents' is outside the link.
    - `- Apple presents [the best of 2018 - Apple](https://www.apple.com/newsroom/2018/12/apple-presents-the-best-of-2018/)`
    - Fix: Make the full title the link.
  - **[LOW] malformed-link** — Link text begins partway through the headline.
    - `- Hackers breach Quora.com and steal password data for [100 million users | Ars Technica](https://arstechnica.com/information-technology/2018/12/quora-says-hackers-stole-password-data-and-other-details-for-100-million-users/)`
    - Fix: Link the entire headline.
  - **[LOW] typo** — '64-but' should be '64-bit'.
    - `I have a ScanSnap scanner and was worried they were not going to make a 64-but release!`
    - Fix: Change '64-but' to '64-bit'.

### #84 — Weekly Thing #84 / Dec 15, 2018

- Era: MailChimp
- Overall: Readable overall, but contains clear migration artifacts (literal mp-photo-alt[]= fragments, concatenated photo captions) and several malformed Yet More Links where link brackets begin mid-title.
  - **[HIGH] migration-artifact** — Leftover micropub photo-alt template parameters appear as literal text where photos should have rendered.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these stray mp-photo-alt[]= fragments and restore the missing photo(s) with proper alt text.
  - **[HIGH] migration-artifact** — Another instance of leftover micropub photo-alt parameter fragments rendered as plain text.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these fragments and restore the original photos with alt text.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-title ('Up By Right Networks'); the leading words 'TECHdotMN Bootstrapped Software Maker Propelware Scooped' are outside the link, indicating a broken link wrap.
    - `- TECHdotMN Bootstrapped Software Maker Propelware Scooped [Up By Right Networks - TECHdotMN](https://tech.mn/news/2018/12/11/lakeville-software-maker-propelware-scooped-up-by-right-networks/) tech.mn`
    - Fix: Rewrap so the full article title is inside the link markdown.
  - **[MEDIUM] malformed-link** — Link brackets begin mid-title, leaving 'Scripting API' outside the link — same migration pattern as the previous item.
    - `- Scripting API [now in public beta! | Minecraft](https://minecraft.net/en-us/article/scripting-api-now-public-beta) minecraft.net`
    - Fix: Include 'Scripting API' inside the link text.
  - **[MEDIUM] malformed-link** — 'Lime' is outside the link brackets when it should be part of the title.
    - `- Lime [and Bird are each worth 10B+](https://www.futureengine.org/articles/scooters-are-worth-10b) www.futureengine.org`
    - Fix: Include 'Lime' in the linked text.
  - **[MEDIUM] malformed-link** — Title 'Gorogoa' is outside the link brackets, a truncated link wrap from migration.
    - `- 'Gorogoa' [for iOS — Tools and Toys](http://toolsandtoys.net/gorogoa-for-ios/) toolsandtoys.net`
    - Fix: Include 'Gorogoa' inside the link text.
  - **[LOW] typo** — 'anout' is a clear typo for 'about'.
    - `Didn’t think anout skyways being closed later.`
    - Fix: Change 'anout' to 'about'.
  - **[LOW] narrative-break** — These appear to be concatenated photo captions run together as a single sentence, suggesting missing images/line breaks from migration.
    - `Big Crowd for the Lutefisk Dinner My nephew Garrett and I having lefse. family selfie! family selfie!`
    - Fix: Restore the associated photos or separate the captions into distinct lines.

### #85 — Weekly Thing #85 / Dec 22, 2018

- Era: MailChimp
- Overall: Issue reads cleanly overall; main concern is the stray `## Oh my…` H2 that disrupts the Notable Links section, plus a recurring pattern of link anchors that start mid-title in the Yet More Links list.
  - **[MEDIUM] header-error** — This is an H2 inside the 'Notable Links' section, which breaks the section hierarchy and TOC — it should be prose or a lower heading/blockquote intro.
    - `## Oh my…`
    - Fix: Change `## Oh my…` to plain text or a blockquote lead-in so the Notable Links section structure stays intact.
  - **[LOW] malformed-link** — The link bracket starts mid-sentence ('[license.') causing the linked anchor text to awkwardly span two clauses, suggesting the link placement was mangled.
    - `you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Rework so the link covers natural anchor text like '[Donate to Creative Commons today!](https://creativecommons.org/donate/)'.
  - **[LOW] malformed-link** — Link anchor text starts mid-title (word 'Stripe' is outside the link) — a pattern repeated throughout Yet More Links where the first word is orphaned from the link.
    - `- Stripe [Atlas: Writing copy for landing pages](https://stripe.com/atlas/guides/landing-page-copy) stripe.com`
    - Fix: Move the first word inside the link brackets so the entire title is linked (e.g., `[Stripe Atlas: Writing copy for landing pages](...)`).

### #86 — Weekly Thing #86 / Dec 29, 2018

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but the Microposts section contains visible `mp-photo-alt[]=` migration artifacts and the `My Blog Posts ✍️` header lost its `##`, which are the main concerns.
  - **[MEDIUM] header-error** — This is a section header (should be H2 `## My Blog Posts ✍️`) but was left as plain text, so the following H3 becomes an orphan subheading as the static audit noted.
    - `My Blog Posts ✍️`
    - Fix: Prefix with `## ` to make it an H2 consistent with other section headers.
  - **[LOW] malformed-link** — The static audit flagged `[LWN.net]` as a bracketed no-link, but it is actually nested inside a valid markdown link; the nested brackets may render oddly but the link works — low severity.
    - `Python [gets a new governance model [LWN.net]](https://lwn.net/SubscriberLink/775105/5db16cfe82e78dc3/) lwn.net`
    - Fix: Consider rewording to avoid nested brackets, e.g., `Python [gets a new governance model (LWN.net)](...)`.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt template placeholders leaked into the rendered body where images should have appeared.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these artifacts and, if possible, restore the intended photo(s) with proper alt text.
  - **[HIGH] migration-artifact** — Second occurrence of leaked micropub template placeholder text in the Microposts section.
    - `mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these artifacts and restore the intended photos.
  - **[MEDIUM] narrative-break** — Link boundaries are misplaced so punctuation/sentences are swallowed into anchors (e.g., `[. Tammy got an Earth Puzzle]`), producing awkward rendering and sentence breaks.
    - `The kids each got [big Lego projects: a Ferris Wheel](https://shop.lego.com/en-US/product/Ferris-Wheel-10247) [and an Old Fishing Store](https://shop.lego.com/en-US/product/Old-Fishing-Store-21310) [. Tammy got an Earth Puzzle](https://n-e-r-v-o-u-s.com/shop/product.php?code=368)`
    - Fix: Rewrap link text so anchors contain only the thing being linked and the period/sentence break stays outside the link.
  - **[LOW] narrative-break** — Link text spans a sentence boundary, pulling the word `years.` into the anchor and breaking normal prose flow.
    - `[years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: End the prior sentence outside the link and limit anchor text to `Donate to Let's Encrypt today!`.
  - **[LOW] other** — A bare URL appears immediately under the section header before the linked prose, likely a leftover from editing.
    - `## Give Back 🎁

https://letsencrypt.org`
    - Fix: Remove the redundant bare URL line.
  - **[LOW] typo** — Obvious capitalization typo: `HIs` should be `His`.
    - `HIs list of apps`
    - Fix: Change `HIs` to `His`.

### #87 — Weekly Thing #87 / Jan 5, 2019

- Era: MailChimp
- Overall: Readable overall, but the 'Yet More Links' and Give Back sections have several malformed markdown link brackets that split titles and commentary, plus a few minor typos in the Microposts.
  - **[MEDIUM] malformed-link** — The markdown link bracket spans across a sentence boundary, making 'license. Donate to Creative Commons today!' all one link when 'license' should likely be outside the link text.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Restructure so the link text is only 'Donate to Creative Commons today!' and 'license.' ends the prior sentence normally.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-sentence, splitting the title between plain text and link text; this pattern repeats throughout the 'Yet More Links' section and appears to be a migration artifact from a different link format.
    - `- In 2019, blockchains will start to [become boring - MIT Technology Review](https://www.technologyreview.com/s/612687/in-2019-blockchains-will-start-to-become-boring/)`
    - Fix: Rewrap so the entire article title is the link text, e.g., `[In 2019, blockchains will start to become boring - MIT Technology Review](...)`.
  - **[MEDIUM] malformed-link** — Link brackets are split across the title and the commentary so 'to reading this book. Via @SamPierson' becomes the link text instead of just an attribution.
    - `- Trillion Dollar [Coach - Eric Schmidt - Hardcover](https://www.harpercollins.com/9780062839268/trillion-dollar-coach/) www.harpercollins.com
Will be looking forward [to reading this book. Via @SamPierson](https://twitter.com/sam_pierson/status/1078476847522988032?s=20) .`
    - Fix: Make the full title the link and limit the Twitter link to 'Via @SamPierson'.
  - **[LOW] typo** — Missing conjunction/punctuation ('but' or a comma) between 'at first' and 'a lot of fun' makes the sentence ungrammatical.
    - `Didn’t make sense at first a lot of fun after we figured it out.`
    - Fix: Insert 'but' or a comma: 'Didn’t make sense at first, but a lot of fun after we figured it out.'
  - **[LOW] typo** — 'Turns our' should be 'Turns out'.
    - `Turns our New Years Eve is a busy night at theaters!`
    - Fix: Change 'Turns our' to 'Turns out'.
  - **[LOW] typo** — 'your' should be 'you're' (you are).
    - `Chores are things you do because your part of the family`
    - Fix: Change 'your' to 'you’re'.

### #88 — Weekly Thing #88 / Jan 12, 2019

- Era: MailChimp
- Overall: Content is readable and era-appropriate, but the issue has several malformed markdown links — especially the badly split Blot intro and the 'Yet More Links' bullets where anchor text starts mid-title — that an editor should clean up.
  - **[HIGH] malformed-link** — The markdown link syntax is badly broken with parentheses split across two link anchors, producing garbled rendered text like 'around with a (new to me' and ') blogging service called Blot'.
    - `I've also been playing [around with a (new to me](https://blot.thingelstad.com/2018/12/maybe-blot) [) blogging service called Blot](https://blot.im) .`
    - Fix: Rewrite as two cleanly-separated links, e.g., 'playing around with a [(new to me) blogging service called Blot](https://blot.im)' with the 'maybe-blot' reference placed as a separate link.
  - **[MEDIUM] malformed-link** — The link boundaries are split awkwardly so the anchor text includes leading punctuation (', a book my book club'), which renders as an odd clickable phrase.
    - `Interesting post that reminded me of [Sustainable Energy Without the Hot Air](https://www.withouthotair.com) [, a book my book club](https://rwbook.club) read a while back.`
    - Fix: Reflow the links so anchor text is the natural phrase, e.g., '[Sustainable Energy Without the Hot Air](https://www.withouthotair.com), a book [my book club](https://rwbook.club) read...'
  - **[MEDIUM] malformed-link** — The link anchor awkwardly begins mid-sentence with 'years.' making the rendered clickable text start with a stray word and period.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the link to wrap only the call-to-action phrase: 'in recent years. [Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)'.
  - **[MEDIUM] malformed-link** — The link anchor begins mid-title ('work this year...') instead of wrapping the whole article title, a pattern repeated throughout the 'Yet More Links' section.
    - `- What I learned at [work this year | Bill Gates](https://www.gatesnotes.com/About-Bill-Gates/Year-in-Review-2018) www.gatesnotes.com`
    - Fix: Rewrap each bullet so the full article title is the link anchor, e.g., '[What I learned at work this year | Bill Gates](...)'.
  - **[MEDIUM] malformed-link** — Only part of the article title is inside the link, breaking the expected pattern of the full title as anchor text.
    - `- Pokémon GO Caught Nearly $800 Million in Global Revenue [Last Year, Growing 35% Over 2017](https://sensortower.com/blog/pokemon-go-revenue-december-2018) sensortower.com`
    - Fix: Expand the anchor text to cover the whole headline.
  - **[MEDIUM] malformed-link** — The link anchor starts mid-title, leaving 'How to Delete Online Accounts You' as plain text.
    - `- How to Delete Online Accounts You [No Longer Need - Consumer Reports](https://www.consumerreports.org/privacy/how-to-delete-online-accounts-you-no-longer-need/) www.consumerreports.org`
    - Fix: Wrap the full title as the link anchor.
  - **[LOW] typo** — Missing apostrophe in 'this weeks' (should be 'this week's').
    - `I will admit this weeks picture is a bit of a stretch though.`
    - Fix: Change 'this weeks' to 'this week's'.

### #89 — Weekly Thing #89 / Jan 19, 2019

- Era: MailChimp
- Overall: Readable overall, but the Yet More Links section and a couple of mailto links have systematically malformed markdown that degrades link rendering.
  - **[HIGH] malformed-link** — The mailto link uses parentheses instead of markdown link syntax, so 'Send an email' is not a link and the raw mailto URL will render as visible text.
    - `Send an email (mailto:?subject=Check%20out%20the%20Weekly%20Thing&body=Hello!%0A%0AI%20subscribe%20to%20this%20weekly%20email`
    - Fix: Convert to proper markdown: [Send an email](mailto:?subject=...&body=...).
  - **[HIGH] malformed-link** — The link bracket starts mid-title ('Areas | ...') rather than wrapping the full title, so the rendered link text is truncated — this pattern repeats throughout Yet More Links.
    - `- More PM Problem [Areas | Silicon Valley Product Group](https://svpg.com/more-pm-problem-areas/) svpg.com`
    - Fix: Rewrap each Yet More Links entry so the entire title is inside the link brackets (e.g., [More PM Problem Areas | Silicon Valley Product Group](...)).
  - **[HIGH] malformed-link** — Link bracket begins with '|' leaving 'mailtolink.me' outside the link; rendered link text starts with a stray pipe.
    - `- mailtolink.me [| markup generator for mailto links](https://mailtolink.me/) mailtolink.me`
    - Fix: Rewrap as [mailtolink.me | markup generator for mailto links](https://mailtolink.me/).
  - **[MEDIUM] malformed-link** — Another mailto URL placed in bare parentheses instead of a markdown link, so it renders as raw text; also the address 'jamie@thingelstad' lacks a TLD.
    - `These are handy (mailto:jamie@thingelstad?subject=Mail%20to%20links%20are%20great!&body=What's%20up%3F)`
    - Fix: Make it a proper markdown link like [these are handy](mailto:jamie@thingelstad.com?subject=...) and fix the email domain.
  - **[MEDIUM] malformed-link** — Split link brackets produce two awkward links with an apostrophe-s dangling between them instead of one coherent link phrase.
    - `This is the [best description of what Tim Berners-Lee](https://www.w3.org/People/Berners-Lee/) ['s Solid](https://solid.mit.edu) is about.`
    - Fix: Restructure so the sentence uses single, coherent link anchors rather than two adjacent bracketed fragments.
  - **[MEDIUM] malformed-link** — The link anchor text 'is pretty great. Via Leah Cunningham' awkwardly combines commentary and attribution into one hyperlink, indicating the intended anchor was just the name.
    - `I've been using DuckDuckGo for a long time, and this behind the scenes look at the company [is pretty great. Via Leah Cunningham](http://www.cunningleah.com)`
    - Fix: Limit link anchor to 'Leah Cunningham' and leave the commentary as plain text.
  - **[LOW] typo** — 'advise' (verb) should be 'advice' (noun).
    - `This is usable advise that I’m positive I can put to use.`
    - Fix: Change 'advise' to 'advice'.

### #90 — Weekly Thing #90 / Jan 26, 2019

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but the 'My Blog Posts' heading lost its H2 prefix and the 'Yet More Links' / Give Back link brackets are split awkwardly from migration.
  - **[MEDIUM] header-error** — This should be an H2 section header (## My Blog Posts ✍️) matching the era-standard emoji-H2 pattern, but it's rendered as plain text, making the following H3 an orphan subheading.
    - `My Blog Posts ✍️`
    - Fix: Change 'My Blog Posts ✍️' to '## My Blog Posts ✍️' so the H3 link sits under a proper section.
  - **[LOW] narrative-break** — 'and it the content' reads as a dropped word during editing (likely intended 'and the content' or 'and it is the content').
    - `The web is a major part of our culture and it the content that we put on it is sadly ephemeral.`
    - Fix: Remove the stray 'it' so the sentence reads 'and the content that we put on it is sadly ephemeral.'
  - **[MEDIUM] malformed-link** — The 'Yet More Links' bullets have the link text split mid-title ('The Tech' outside the bracket, 'Revolt — …' inside), a migration artifact that makes link labels read oddly.
    - `- The Tech [Revolt — The California Sunday Magazine](https://story.californiasunday.com/tech-revolt) story.californiasunday.com`
    - Fix: Reformat each bullet so the entire article title is inside the link text, e.g. '[The Tech Revolt — The California Sunday Magazine](…)'.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-sentence at 'history.', so the word 'history' becomes part of the link anchor instead of the prose — a bracket-placement error.
    - `The Internet Archive is working hard to capture that information and keep it for [history. Donate to Internet Archive today!](https://archive.org/donate/)`
    - Fix: Move the opening bracket after 'history.' so only 'Donate to Internet Archive today!' is the link text.

### #91 — Weekly Thing #91 / Feb 2, 2019

- Era: MailChimp
- Overall: Readable overall, but the Microposts section is littered with unprocessed 'mp-photo-alt[]=' fragments and several Yet More Links / Give Back entries have migration-damaged link boundaries that need cleanup.
  - **[MEDIUM] header-error** — 'My Blog Posts ✍️' is formatted as plain text rather than an H2 heading, which breaks the TOC and leaves the following H3 as an orphan subheading.
    - `My Blog Posts ✍️

### [Hack the Gap 2019](https://www.thingelstad.com/2019/hack-the-gap-2019)`
    - Fix: Prefix 'My Blog Posts ✍️' with '## ' so it renders as an H2 section header consistent with other sections.
  - **[HIGH] migration-artifact** — Literal 'mp-photo-alt[]=' tokens appear repeatedly in the Microposts section; these are micropub photo-alt parameter fragments that weren't processed into images, leaving visible stray text.
    - `mp-photo-alt[]=`
    - Fix: Remove the mp-photo-alt[]= fragments or replace them with the intended image embeds/alt text.
  - **[MEDIUM] malformed-link** — The link bracket begins mid-title ('Block Ad Transparency Tools') rather than wrapping the full title 'Facebook Moves to Block Ad Transparency Tools', indicating a migration-era title/link split.
    - `- Facebook Moves to [Block Ad Transparency Tools — ProPublica](https://www.propublica.org/article/facebook-blocks-ad-transparency-tools) www.propublica.org`
    - Fix: Rewrap the markdown so the entire article title is inside the link text.
  - **[MEDIUM] malformed-link** — Link bracket starts after 'Omni', splitting the title so 'Omni' is outside the link text.
    - `- Omni [Roadmap 2019 - The Omni Group](https://www.omnigroup.com/blog/omni-roadmap-2019) www.omnigroup.com`
    - Fix: Move the opening bracket before 'Omni' so the full title is the link text.
  - **[MEDIUM] malformed-link** — Only the tail of the description is linked; the link text should be the site/title, not a fragment of prose.
    - `- Custom Mission Patches - design and print NASA-style [mission patch stickers for your team.](https://mission-patch.com/) mission-patch.com`
    - Fix: Restructure so the title 'Custom Mission Patches' is the link text and the description follows as plain prose.
  - **[HIGH] malformed-link** — Link boundaries clearly slipped during migration — link text spans across unrelated prose ('projects in the world, including Wikipedia' and 'internet property. Donate to Wikimedia today!'), producing awkward inline links.
    - `operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Re-anchor the links to the intended short phrases (e.g., 'Wikipedia' and 'Donate to Wikimedia today!') so prose reads naturally.
  - **[MEDIUM] dangling-reference** — A bare URL appears under the Give Back heading with no context before the paragraph; it looks like a stray leftover from migration.
    - `## Give Back 🎁

https://wikimediafoundation.org/wiki/Home`
    - Fix: Remove the bare URL line or convert it into a proper heading/link for the Wikimedia Foundation entry.

### #92 — Weekly Thing #92 / Feb 9, 2019

- Era: MailChimp
- Overall: Issue is readable but marred by many link-span errors in which link text begins mid-sentence, plus visible `mp-photo-alt[]=` migration artifacts in Microposts and a missing H2 for 'My Blog Posts' that causes the three orphan H3s the static audit flagged.
  - **[MEDIUM] header-error** — This should be an H2 section header (`## My Blog Posts ✍️`) like the other sections, but it's plain text — which is why the static audit sees the following H3s as orphans.
    - `My Blog Posts ✍️`
    - Fix: Change `My Blog Posts ✍️` to `## My Blog Posts ✍️` to restore the section hierarchy.
  - **[HIGH] malformed-link** — The link text spans two distinct thoughts — the phrase 'read only' belongs outside the link, and a separate link for datasette appears to have been merged incorrectly.
    - `Looks like it’s [read only. Reminds me of datasette](https://github.com/simonw/datasette)`
    - Fix: Split into `Looks like it's read only. Reminds me of [datasette](https://github.com/simonw/datasette).`
  - **[HIGH] malformed-link** — Link text spans a sentence boundary — 'these platforms.' should be outside the link and only 'Marshmello' (or similar) should be linked.
    - `engaging friends via [these platforms. This concert from Marshmello](https://marshmellomusic.com) inside of the game`
    - Fix: Rework as `engaging friends via these platforms. This concert from [Marshmello](https://marshmellomusic.com) inside of the game`.
  - **[HIGH] malformed-link** — Link text appears to split the site name awkwardly — 'My Brand New Logo' is outside the link while 'maker | create your own logo' is inside.
    - `My Brand New Logo – logo [maker | create your own logo](https://mybrandnewlogo.com/) mybrandnewlogo.com`
    - Fix: Make the whole title the link text, e.g. `[My Brand New Logo – logo maker | create your own logo](https://mybrandnewlogo.com/)`.
  - **[HIGH] malformed-link** — Link text starts mid-phrase — the title 'Lapis - A web framework for' is outside the link.
    - `Lapis - A web framework for [Lua or MoonScript powered by OpenResty](http://leafo.net/lapis/#lang=lua) leafo.net`
    - Fix: Wrap the full title: `[Lapis - A web framework for Lua or MoonScript powered by OpenResty](http://leafo.net/lapis/#lang=lua)`.
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence, crossing a period — 'non-profit.' should be outside the link.
    - `Minnestar is a 501c3 [non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Rephrase as `Minnestar is a 501c3 non-profit. [Become a Community Supporter today!](https://minnestar.donortools.com/)`.
  - **[MEDIUM] malformed-link** — The opening parenthesis is inside the link text but the matching close parenthesis is outside, and the linked text is truncated mid-phrase.
    - `It’s great to get teams in front of the people that represent the work they do! [(Picture of me from Amy Patton](https://twitter.com/pattonamyj/status/1093556370203426817) ! Thanks!)`
    - Fix: Balance parens and tighten link text, e.g. `(Picture of me from [Amy Patton](https://twitter.com/pattonamyj/status/1093556370203426817)! Thanks!)`.
  - **[MEDIUM] malformed-link** — The first link text improperly spans across '#TeamSPS 2019 Sales Kickoff!' and the person's name that the LinkedIn URL actually points to.
    - `I had a great morning joining the [#TeamSPS 2019 Sales Kickoff! Dan Juckniess](https://www.linkedin.com/in/dan-juckniess-68920a10/) [and Jim Frome](https://www.linkedin.com/in/jim-frome-5a55984/)`
    - Fix: Limit the link text to the person's name: `joining the #TeamSPS 2019 Sales Kickoff! [Dan Juckniess](...) and [Jim Frome](...)`.
  - **[MEDIUM] malformed-link** — Link text starts mid-sentence and wraps more than the person's name being linked.
    - `Nearly [all #TeamSPS events have Thad Brenny](https://www.linkedin.com/in/thad-brenny-a-c-e-cts-cte-6b2a869/) making it all look great`
    - Fix: Reduce link text to `[Thad Brenny]` only.
  - **[MEDIUM] malformed-link** — Link text begins mid-phrase; only 'Shawn Achor' corresponds to the URL.
    - `A tremendous [talk on happiness by Shawn Achor](http://www.shawnachor.com)`
    - Fix: Shorten link text to the speaker name: `A tremendous talk on happiness by [Shawn Achor](http://www.shawnachor.com)`.
  - **[MEDIUM] malformed-link** — The second link wraps 'tonight and introduced SPS Commerce' when only 'SPS Commerce' matches the URL.
    - `[I visited Minnehack](https://minnehack.io) [tonight and introduced SPS Commerce](https://jobs.spscommerce.com) to 300+ students`
    - Fix: Scope the links tightly: `I visited [Minnehack](https://minnehack.io) tonight and introduced [SPS Commerce](https://jobs.spscommerce.com)`.
  - **[MEDIUM] malformed-link** — Link text starts mid-phrase; 'Minnesota Kubb' is the actual linked entity.
    - `Kubbchucks playing [in our 8th annual Minnesota Kubb](http://minnesotakubb.com) winter tournament`
    - Fix: Limit to `[Minnesota Kubb](http://minnesotakubb.com)`.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt placeholder tokens leaked into the body — these are import artifacts that should not be visible to readers.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove all `mp-photo-alt[]=` fragments throughout the Microposts section (multiple occurrences).
  - **[LOW] migration-artifact** — A bare URL precedes the linked text for the same site, likely a migration leftover from an autolinked preview.
    - `https://minnestar.org

[Minnestar](https://minnestar.org/)`
    - Fix: Remove the redundant bare `https://minnestar.org` line.

### #93 — Weekly Thing #93 / Feb 16, 2019

- Era: MailChimp
- Overall: Readable overall, but the Yet More Links section has a systemic pattern of misplaced opening brackets that truncates link titles, and one nested-bracket case likely breaks markdown rendering.
  - **[HIGH] malformed-link** — The link bracket starts mid-title (after 'LIVE ') rather than wrapping the full title, so the visible link text reads awkwardly starting with 'at the 61st GRAMMYs'.
    - `- Brandi Carlile - The Joke (LIVE [at the 61st GRAMMYs) - YouTube](https://www.youtube.com/watch?feature=youtu.be&v=KJqL1yIm9e0&app=desktop) www.youtube.com`
    - Fix: Move the opening bracket to the start of the title so the entire title is the link text.
  - **[HIGH] malformed-link** — Link text begins partway through the title, leaving the opening phrase as plain text; the full title should be the link.
    - `- Letting neural networks be weird — Candy Heart [messages written by a neural network](http://aiweirdness.com/post/170685749687/candy-heart-messages-written-by-a-neural-network) aiweirdness.com`
    - Fix: Wrap the entire title in the link markdown.
  - **[HIGH] malformed-link** — Only the subtitle is linked while the product name is outside the brackets; consistent with other malformed Yet More Links entries.
    - `- Leave Me Alone - [Take back control of your inbox](https://leavemealone.xyz/) leavemealone.xyz`
    - Fix: Include the full title 'Leave Me Alone - Take back control of your inbox' inside the link brackets.
  - **[HIGH] malformed-link** — Link bracket starts mid-title, leaving 'Python Itertools: For a faster' as non-linked text.
    - `- Python Itertools: For a faster [and memory efficient code – Kanoki](https://kanoki.org/2019/02/08/python-itertools/) kanoki.org`
    - Fix: Move the opening bracket to the start of the title.
  - **[HIGH] malformed-link** — Link bracket opens mid-title after 'Mr.', splitting the title across linked and non-linked text.
    - `- No thank you, Mr. [Pecker – Jeff Bezos – Medium](https://medium.com/@jeffreypbezos/no-thank-you-mr-pecker-146e3922310f) medium.com`
    - Fix: Wrap the full title in the link markdown.
  - **[HIGH] malformed-link** — Bracket opens mid-title and the nested [Etsy] inside the link text likely breaks the markdown link parser, producing broken output (this is the static audit's [Etsy] finding).
    - `- Video Game Controller Cufflinks [by ElegantLocketShop [Etsy] —Tools and Toys](http://toolsandtoys.net/video-game-controller-cufflinks-by-elegantlocketshop-etsy/) toolsandtoys.net`
    - Fix: Wrap the full title in the link and remove or rephrase the nested brackets around Etsy.
  - **[MEDIUM] malformed-link** — Link text spans a sentence boundary ('building. Amazing space. Thanks to Nick'), which is clearly a misplaced bracket rather than intended link text.
    - `the mechanics of the [building. Amazing space. Thanks to Nick](https://www.linkedin.com/in/nick-swenson-976b7337/) for the link.`
    - Fix: Restrict the link to 'Nick' (or similar) so the link text is a proper phrase.
  - **[MEDIUM] malformed-link** — Bracket opens mid-sentence so the link text awkwardly begins with 'years.' instead of a clean phrase.
    - `most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the opening bracket to 'Donate to Let's Encrypt today!'
  - **[LOW] narrative-break** — The micropost appears to reference an HTML entity that was rendered/stripped, so the punchline ('&') is missing its point.
    - `Tesla, your HTML encoding is showing. & 😳`
    - Fix: Restore the literal entity string (e.g., '&amp;') that Tesla was displaying.

### #94 — Weekly Thing #94 / Feb 23, 2019

- Era: MailChimp
- Overall: Readable overall, but this issue has an unusually high number of malformed markdown links where link text spans unintended prose, plus a leaked 'mp-photo-alt[]=' template artifact that should be cleaned up.
  - **[HIGH] malformed-link** — The link bracket wraps 'I put Tetris 99' but the intended link text is just 'Tetris 99'; the phrase 'I put' is incorrectly inside the link.
    - `[I put Tetris 99](https://www.nintendo.com/games/detail/tetris-99-switch) on my Switch and you may not hear from me for a very long time.`
    - Fix: Rewrite as 'I put [Tetris 99](...) on my Switch' so only the product name is linked.
  - **[HIGH] malformed-link** — The link text 'in tech. If you remember BeOS' incorrectly spans a sentence boundary; the link should only wrap 'BeOS'.
    - `writing some very fun retrospectives of his time [in tech. If you remember BeOS](https://en.wikipedia.org/wiki/BeOS) [and the BeBox](https://en.wikipedia.org/wiki/BeBox)`
    - Fix: Restructure so only 'BeOS' is the link text, e.g. 'his time in tech. If you remember [BeOS](...) [and the BeBox](...)'.
  - **[HIGH] malformed-link** — The link points to the NeXTSTEP Wikipedia page but wraps descriptive text 'little inside baseball look at NeXTSTEP', suggesting the intended article link was lost and only the Wikipedia gloss remains.
    - `I also found this [little inside baseball look at NeXTSTEP](https://en.wikipedia.org/wiki/NeXTSTEP) and Apple's acquisition of NeXT fun.`
    - Fix: Restore the original article URL for the 'inside baseball look' phrase, or reduce the link text to just 'NeXTSTEP'.
  - **[HIGH] malformed-link** — The link text incorrectly includes 'ads (I'm looking at you ' and an unmatched open parenthesis, with a stray ') ' following; bracketing is malformed.
    - `[ads (I’m looking at you Disqus](https://disqus.com) )`
    - Fix: Rewrite as 'ads (I'm looking at you [Disqus](https://disqus.com))' so only 'Disqus' is linked.
  - **[HIGH] malformed-link** — The link text 'have thought of a Battle Royale' incorrectly wraps surrounding prose rather than just 'Battle Royale'.
    - `I never would [have thought of a Battle Royale](https://en.wikipedia.org/wiki/Battle_royale_game) version of Tetris!`
    - Fix: Change to 'I never would have thought of a [Battle Royale](...) version of Tetris!'
  - **[HIGH] malformed-link** — Link text awkwardly spans 'Windmere Castle" at Escape MSP Lakeville', crossing a closing quote; the intended link was likely just the venue name.
    - `We played “Quest for the Amulet at [Windmere Castle” at Escape MSP Lakeville](https://escapemsp.com/tickets-lakeville/) today.`
    - Fix: Rewrite so the link wraps just 'Escape MSP Lakeville' (or the full game title), not a cross-clause fragment.
  - **[MEDIUM] malformed-link** — Link text begins mid-sentence at 'State Fair year-round', leaving 'New Minnetonka restaurant's deep-fried burger is like eating at' as unlinked preamble; inconsistent with the other bullet items.
    - `- New Minnetonka restaurant's deep-fried burger is like eating at [State Fair year-round | Star Tribune](http://www.startribune.com/new-minnetonka-restaurant-s-deep-fried-burger-is-like-eating-at-state-fair-year-round/506163112/) www.startribune.com`
    - Fix: Wrap the full article title as the link text, consistent with the other items in this list.
  - **[HIGH] migration-artifact** — This is a stray micropost photo-alt template parameter that leaked into the rendered body between microposts.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' line from the body.
  - **[LOW] typo** — 'rain out' should be 'ran out'.
    - `we were nowhere even close to solving it when the clock rain out`
    - Fix: Change 'rain out' to 'ran out'.
  - **[LOW] header-error** — Per the era's canonical ordering, 'My Weekly Photo' typically appears later; here it's placed between Featured Links and Notable Links, which is unusual but not strictly broken.
    - `## My Weekly Photo 📷`
    - Fix: Optional: relocate to the standard position, or leave as an intentional choice.

### #95 — Weekly Thing #95 / Mar 2, 2019

- Era: MailChimp
- Overall: Readable issue, but numerous link boundaries were set mid-sentence (likely migration artifacts) and two stray 'mp-photo-alt[]=' tokens appear in the Microposts section and should be removed.
  - **[MEDIUM] malformed-link** — The link text starts mid-sentence at 'me.' — the anchor boundary was placed incorrectly, likely during migration, so the visible link reads awkwardly as 'me. MacStories has a good writeup'.
    - `"instant buy" for [me. MacStories has a good writeup](https://www.macstories.net/reviews/spectre-a-computational-approach-to-long-exposure-iphone-photography/)`
    - Fix: Rewrite so only 'MacStories has a good writeup' (or similar) is the link text, e.g., '...an "instant buy" for me. [MacStories has a good writeup](...)'.
  - **[MEDIUM] malformed-link** — The link text swallows 'I've seen' which should be prose; only the name should be the link.
    - `[I've seen Allison Liuzzi](https://www.linkedin.com/in/allison-liuzzi-6564aa159/) of Compass`
    - Fix: Change to: I've seen [Allison Liuzzi](...) of Compass...
  - **[MEDIUM] malformed-link** — The link text begins with ': Beautiful...' because 'bullet' was left outside the brackets, producing a broken-looking title.
    - `- bullet [: Beautiful Python Prompts Made Simple](https://github.com/Mckinsey666/bullet) github.com`
    - Fix: Make the full title the link text: [bullet: Beautiful Python Prompts Made Simple](...).
  - **[MEDIUM] malformed-link** — Only the tail of the title is linked; 'Carrot | Leadership' was left outside the brackets.
    - `- Carrot | Leadership [communication for fast-growing and remote teams.](https://carrot.io/) carrot.io`
    - Fix: Place the whole title inside the link: [Carrot | Leadership communication for fast-growing and remote teams.](https://carrot.io/).
  - **[MEDIUM] malformed-link** — The link text is split; the leading 'AWS API Performance Comparison: Serverless' is outside the brackets.
    - `- AWS API Performance Comparison: Serverless [vs. Containers vs. API Gateway integration](https://www.alexdebrie.com/posts/aws-api-performance-comparison/)`
    - Fix: Wrap the full title in the link: [AWS API Performance Comparison: Serverless vs. Containers vs. API Gateway integration](...).
  - **[LOW] malformed-link** — Link boundary breaks mid-sentence, making the anchor text start with 'history.' rather than the intended CTA.
    - `keep it for [history. Donate to Internet Archive today!](https://archive.org/donate/)`
    - Fix: End the sentence at 'history.' and put only 'Donate to Internet Archive today!' inside the link.
  - **[HIGH] migration-artifact** — Literal 'mp-photo-alt[]=' strings appear twice in the Microposts section — these are micropub form-field artifacts that leaked through from the posting tool.
    - `mp-photo-alt[]=`
    - Fix: Delete both 'mp-photo-alt[]=' lines.
  - **[LOW] malformed-link** — Link text absorbs 'was introduced to' rather than only the term being linked.
    - `[was introduced to ”fractal” Romanesco broccoli](https://en.wikipedia.org/wiki/Romanesco_broccoli)`
    - Fix: Limit the link to 'fractal Romanesco broccoli' (or 'Romanesco broccoli').
  - **[LOW] malformed-link** — Adjacent link anchors spill normal prose ('event from', 'of') into link text, producing awkward anchor phrasing.
    - `[this morning at MHTA Tech Talent](https://mhta.org/event/techtalent/) [event from Deb Broberg](https://www.linkedin.com/in/deb-broberg-sphr/)`
    - Fix: Narrow each anchor to the proper noun (event name, person name) and leave the connecting words as plain text.

### #96 — Weekly Thing #96 / Mar 9, 2019

- Era: MailChimp
- Overall: Readable overall, but several `mp-photo-alt[]=` template tokens leaked into the Microposts section and a couple of malformed link anchors should be cleaned up.
  - **[HIGH] migration-artifact** — Literal micropost template placeholder tags leaked into the rendered body in several Microposts entries instead of being replaced with photos.
    - `mp-photo-alt[]=`
    - Fix: Remove the `mp-photo-alt[]=` tokens and insert the intended photo(s) or delete the orphan placeholder lines.
  - **[MEDIUM] malformed-link** — The FastCharts.io section links 'Financial Times' to ft.com but the H3 link to fastcharts.io appears correct; however the linked phrase starts with 'Cool to see' which suggests the wrong text was wrapped — the link anchor 'Cool to see the Financial Times' is awkward and likely a migration/markdown error.
    - `[Cool to see the Financial Times](https://www.ft.com) making their chart generation software available.`
    - Fix: Re-wrap the link so only 'Financial Times' is the anchor text, e.g., 'Cool to see the [Financial Times](https://www.ft.com) making…'.
  - **[MEDIUM] malformed-link** — The link anchor text incorrectly spans across a sentence boundary, indicating a misplaced opening bracket that should have been after 'Creative Commons'.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Move the opening bracket so the anchor reads 'Donate to Creative Commons today!' and leave 'license.' as plain text.
  - **[LOW] narrative-break** — Grammatically broken phrase ('enjoyed to the') suggests a missing word like 'listening'.
    - `I enjoyed to the Recode Decode`
    - Fix: Change to 'I enjoyed listening to the Recode Decode'.
  - **[LOW] other** — A bare URL appears immediately above a linked version of the same URL, likely a migration duplication.
    - `https://creativecommons.org

[Creative Commons](https://creativecommons.org)`
    - Fix: Delete the bare `https://creativecommons.org` line.

### #97 — Weekly Thing #97 / Mar 16, 2019

- Era: MailChimp
- Overall: Readable overall, but this issue has several high-severity migration artifacts: a duplicated photo, leaked mp-photo-alt[]= tokens where micropost images should appear, and multiple mis-bounded links in the Yet More Links section.
  - **[MEDIUM] image-problem** — The same image is embedded twice consecutively, likely a migration duplication error.
    - `![Dreaming of summer.](https://files.thingelstad.com/weekly-thing/97/cover.jpg)

![Dreaming of summer.](https://files.thingelstad.com/weekly-thing/97/cover.jpg)`
    - Fix: Remove one of the duplicate image embeds.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt form field syntax leaked into the rendered body instead of being processed into image alt text.
    - `mp-photo-alt[]=`
    - Fix: Remove the stray mp-photo-alt[]= tokens (they appear multiple times) or replace with the intended photos/alt text.
  - **[HIGH] migration-artifact** — Three consecutive leaked micropub photo-alt tokens appear in the body as visible text.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Delete these tokens and, if possible, restore the missing photos.
  - **[HIGH] malformed-link** — The link markup starts mid-title so only part of the headline is linked and the domain is dangling as plain text.
    - `- Facebook backtracks after removing Warren ads [calling for Facebook breakup - POLITICO](https://www.politico.com/story/2019/03/11/facebook-removes-elizabeth-warren-ads-1216757) www.politico.com`
    - Fix: Rewrap the full title as the link text and remove the trailing bare domain.
  - **[HIGH] malformed-link** — Link only covers the tail of the headline, leaving the first half unlinked and a dangling bare domain.
    - `- Emma Haruka Iwao smashes pi world record [with Google help - BBC News](https://www.bbc.com/news/technology-47524760) www.bbc.com`
    - Fix: Wrap the full title in the link and drop the trailing www.bbc.com.
  - **[HIGH] malformed-link** — Partial-title link with trailing bare domain, same migration pattern as the other Yet More Links items.
    - `- Tesla launches new Supercharger with 1,000 mph charging, [better efficiency, and more - Electrek](https://electrek.co/2019/03/06/tesla-supercharger-v3-kw-capacity-efficiency/) electrek.co`
    - Fix: Rewrap the whole title as the link and remove the trailing domain.
  - **[MEDIUM] malformed-link** — The link text starts mid-sentence ("non-profit. Become a...") suggesting the link boundary was misplaced during migration.
    - `Minnestar is a 501c3 [non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Adjust the link so only "Become a Community Supporter today!" (or similar) is the link text.
  - **[MEDIUM] malformed-link** — The second link's text awkwardly includes "tonight. Wow!" before Alex Honnold's name, indicating misplaced link boundaries.
    - `[Watched Free Solo](https://www.rottentomatoes.com/m/free_solo/) [tonight. Wow! Alex Honnold](https://en.wikipedia.org/wiki/Alex_Honnold) is an amazing climber.`
    - Fix: Restrict the Wikipedia link text to "Alex Honnold" only.

### #98 — Weekly Thing #98 / Mar 23, 2019

- Era: MailChimp
- Overall: Readable but littered with migration artifacts: several links have misplaced brackets (most notably the Richmond game URL dumped on its own line), and the Microposts section has multiple literal 'mp-photo-alt[]=' placeholders that should be cleaned up.
  - **[HIGH] malformed-link** — The 'Richmond v Carlton game' text has its URL on a separate line in parentheses, meaning the link text and URL are disconnected and won't render as a proper markdown link.
    - `[Victoria is the heart of Footy](https://en.wikipedia.org/wiki/Victoria_(Australia)#Sport) , and this Richmond v Carlton game
(https://www.richmondfc.com.au/video/2019-03-21/round-1-highlights)`
    - Fix: Join the link text and URL into proper markdown syntax: [this Richmond v Carlton game](https://www.richmondfc.com.au/video/2019-03-21/round-1-highlights).
  - **[MEDIUM] malformed-link** — Link anchor text awkwardly spans a sentence boundary, suggesting the link was meant to wrap only 'Michael Pollan'.
    - `[of how food works. Michael Pollan](https://michaelpollan.com/)`
    - Fix: Rewrite so the hyperlink wraps only the author's name: 'of how food works. [Michael Pollan](https://michaelpollan.com/)'.
  - **[MEDIUM] malformed-link** — Link anchor text spans across a sentence boundary ('years.' belongs to the previous sentence), an artifact of misplaced link delimiters.
    - `[years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Move the opening bracket so only 'Donate to Let's Encrypt today!' is hyperlinked.
  - **[HIGH] migration-artifact** — These are leftover micropost photo-alt template placeholders that escaped rendering and appear as literal text multiple times in the Microposts section.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove all 'mp-photo-alt[]=' stubs (or replace with the intended photo alt text/images).
  - **[MEDIUM] malformed-link** — The opening curly quote is inside the link text and the closing quote is outside, splitting the quoted phrase across the link boundary.
    - `[I tried a Melbourne “Magic](https://www.afar.com/magazine/8-ways-to-order-a-coffee-in-australia-and-get-what-you-actually-want) ”`
    - Fix: Reframe as 'I tried a Melbourne ["Magic"](...)' so the quotes wrap the linked word cleanly.
  - **[LOW] malformed-link** — The link anchor begins mid-title ('Rented Box Today...') because the opening bracket was placed after 'Automate Your', splitting the article title across plain text and link.
    - `[Rented Box Today :: vas3k's blog](https://vas3k.com/blog/dumbass_home/?ref=sn)`
    - Fix: Place the opening bracket at the start of the full title so the entire article name is the link text.
  - **[LOW] malformed-link** — Link anchor starts mid-sentence instead of wrapping the whole title 'Create UML diagrams online...', a migration artifact consistent with other malformed links in this issue.
    - `Create UML diagrams online [in seconds, no special tools needed.](https://yuml.me/diagram/scruffy/class/draw)`
    - Fix: Rebracket so the entire title is the link text.

### #99 — Weekly Thing #99 / Mar 30, 2019

- Era: MailChimp
- Overall: Readable overall, but contains several mis-bracketed links crossing sentence boundaries and a clear migration artifact ('mp-photo-alt[]=') that should be cleaned up.
  - **[HIGH] migration-artifact** — Stray template/migration tokens from the micropost photo alt field are exposed in the rendered body.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove the literal 'mp-photo-alt[]=' tokens or replace with the intended image/alt content.
  - **[MEDIUM] malformed-link** — Link anchor text spans across sentence boundaries (e.g., '[excited. I think the Apple Card]'), indicating the links were mis-bracketed during authoring/migration.
    - `Not a ton of links this week. A bunch of folks have been asking [me about the Apple Media event](https://www.apple.com/apple-events/march-2019/) from earlier this week. In general it didn't get me that [excited. I think the Apple Card](https://www.apple.com/apple-card/)`
    - Fix: Re-bracket link text so anchors wrap only the relevant phrase (e.g., 'Apple Card') rather than crossing sentence boundaries.
  - **[MEDIUM] malformed-link** — Anchor text awkwardly spans a clause boundary, suggesting the link brackets are misplaced.
    - `If you go way back to when the iPhone [was introduced, Apple introduced Visual Voicemail](https://support.apple.com/en-us/HT201436)`
    - Fix: Tighten the anchor text to just 'Visual Voicemail' or similar.
  - **[LOW] malformed-link** — Link anchor text crosses a sentence boundary, a recurring mis-bracketing pattern in this issue.
    - `Minnestar is a 501c3 [non-profit. Become a Community Supporter today!](https://minnestar.donortools.com/)`
    - Fix: Limit the anchor to 'Become a Community Supporter today!' and leave 'non-profit.' outside the link.
  - **[LOW] typo** — 'desires traits' should be 'desired traits'.
    - `This is a great set of desires traits for technical leaders`
    - Fix: Change 'desires traits' to 'desired traits'.
  - **[LOW] typo** — Missing 'and' — reads 'I enjoyed this read the lesson it contains'.
    - `the lesson it contains`
    - Fix: Insert 'and' so it reads 'enjoyed this read and the lesson it contains'.

### #100 — Weekly Thing #100 / Apr 6, 2019

- Era: MailChimp
- Overall: Readable overall, but the Microposts section is littered with unrendered mp-photo-alt[]= placeholders and a couple of link-wrapping errors (Give Back, Yet More Links) that should be cleaned up.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt template placeholders leaked into the rendered body throughout the Microposts section, appearing many times where images should have been embedded.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Replace these placeholders with the actual micropost photos or remove the stray template tokens.
  - **[MEDIUM] image-problem** — These repeated tokens indicate images were expected in the micropost entries but never got rendered into the archive, leaving the posts visually incomplete.
    - `mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Restore the referenced photos from the original microposts or drop the placeholders so the text reads cleanly.
  - **[MEDIUM] malformed-link** — The link text wraps across a sentence boundary ("recent [years. Donate to Let's Encrypt today!]"), which was clearly not the author's intent — only "Donate to Let's Encrypt today!" should be linked.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Close the sentence after "recent years." and move the link bracket to enclose only "Donate to Let's Encrypt today!".
  - **[MEDIUM] malformed-link** — Several Yet More Links entries have link text starting mid-phrase ("on top of Perl text processing", "Love Story – On my Om", "Be Revolutionary to Be a Hit", etc.), indicating the title/URL pairing got mangled during migration.
    - `- bsed: Simple SQL-like syntax [on top of Perl text processing.](https://github.com/andrewbihl/bsed) github.com`
    - Fix: Re-wrap each list item so the full article title is the link text, as in other issues.
  - **[LOW] typo** — "your think" should be "your thing".
    - `If the pictures aren't your think, it'll be pretty short this week.`
    - Fix: Change "your think" to "your thing".
  - **[LOW] narrative-break** — The "But there's that other 90%..." paragraph appears to be an unmarked block quote from the linked article rather than Jamie's commentary, making the voice confusing.
    - `Funny anecdotes here but mostly just something that I agree is absolutely true.

But there's that other 90% that keeps nagging me.`
    - Fix: Format the quoted passage as a blockquote to distinguish it from the editor's commentary.

### #101 — Weekly Thing #101 / Apr 13, 2019

- Era: MailChimp
- Overall: Readable overall, but several migration artifacts—especially literal `mp-photo-alt[]=` placeholders in the Microposts section and multiple mis-anchored links—should be cleaned up.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt template placeholder leaked into the rendered body where an image or alt text should appear.
    - `mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these placeholder strings or replace with actual images/alt text from the original microposts.
  - **[HIGH] migration-artifact** — Stray micropub template placeholder visible in the rendered body.
    - `mp-photo-alt[]=`
    - Fix: Remove the placeholder or replace with the actual image reference.
  - **[HIGH] migration-artifact** — Triple micropub template placeholder leaked in place of images.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove the placeholders or restore the original micropost images with alt text.
  - **[MEDIUM] malformed-link** — The link bracket wraps prose that spans a sentence boundary ("want to learn from. The book"), indicating the link text was mis-captured during migration.
    - `Good questions for 1:1 sessions with people that you work with or [want to learn from. The book](https://juliezhuo.com/book/manager.html)`
    - Fix: Split so the sentence ends after "learn from." and only "The book" is the linked text.
  - **[MEDIUM] malformed-link** — The opening quote is outside the link but the closing quote is inside, indicating the link anchor captured text incorrectly during migration.
    - `Our anthem for our time in San Antonio, TX has been “In [San Antonio, They Got The Alamo”](https://itunes.apple.com/us/album/in-san-antonio-they-got-the-alamo/512961235?i=512961310)`
    - Fix: Adjust link boundaries so the full song title is the link text and quotes balance outside it.
  - **[MEDIUM] malformed-link** — Link text begins mid-phrase ("Cream stop was…"), a migration artifact from auto-linking.
    - `Today’s Vacation Ice [Cream stop was Steel City Pops](https://steelcitypops.com)`
    - Fix: Rewrite so only "Steel City Pops" is the link text.
  - **[MEDIUM] malformed-link** — Link text starts mid-phrase and a second link begins with ". Also checked out", both malformed anchor spans from migration.
    - `We had an amazing afternoon in San [Antonio at the Pearl Farmers Market](http://atpearl.com/farmers-market) [. Also checked out Hotel Emma](https://www.thehotelemma.com)`
    - Fix: Re-anchor links so only the venue names are linked and sentence punctuation sits outside the link text.
  - **[LOW] malformed-link** — Trailing space before "!" suggests the original had punctuation outside the link (minor migration artifact pattern seen throughout).
    - `We saw a very cool magic show and got a magic lesson from [Scott Pepper and the Magicians Agency](https://scottpepper.com)`
    - Fix: Tighten spacing between link close and punctuation.
  - **[LOW] other** — Bare URL on its own line immediately followed by the same URL as a proper link appears to be a leftover duplicate from migration.
    - `https://www.eff.org

[The Electronic Frontier Foundation](https://www.eff.org)`
    - Fix: Remove the bare URL line.
  - **[LOW] typo** — "desert" should be "dessert" in this context.
    - `This was like a delicious desert at the end of a good meal.`
    - Fix: Change "desert" to "dessert".

### #102 — Weekly Thing #102 / Apr 20, 2019

- Era: MailChimp
- Overall: The issue is mostly clean but has a duplicated photo caption, a stray `mp-photo-alt[]=` micropub artifact, and a couple of awkward link wrappings plus a name typo that an editor should clean up.
  - **[MEDIUM] narrative-break** — The photo caption is duplicated verbatim after the image alt text, appearing twice in the body as a migration artifact.
    - `This United sign stands proudly in front of the just opened Allianz Field, the new Minnesota United home. Our family name is on there somewhere. ⚽️

This United sign stands proudly in front of the just opened Allianz Field, the new Minnesota United home. Our family name is on there somewhere.`
    - Fix: Remove the duplicated caption block so the caption appears only once.
  - **[HIGH] migration-artifact** — A stray micropub form field token is visible in the rendered body of a micropost, clearly a migration/publishing artifact.
    - `mp-photo-alt[]=`
    - Fix: Remove the `mp-photo-alt[]=` line from the micropost body.
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence ('Eat' is outside the link), which is awkward linking and likely a migration mis-wrap; also 'Pollen' is a misspelling of Michael Pollan.
    - `As Michael Pollen stated so succinctly: Eat [food. Not too much. Mostly plants.](https://michaelpollan.com/articles-archive/unhappy-meals/) .`
    - Fix: Rewrap the link to cover the full quote and correct 'Pollen' to 'Pollan'.
  - **[LOW] typo** — The author's name is Michael Pollan, not Pollen.
    - `As Michael Pollen stated so succinctly`
    - Fix: Change 'Pollen' to 'Pollan'.
  - **[LOW] malformed-link** — Link text starts mid-sentence with 'of them.' included inside the link, indicating a misplaced markdown link boundary.
    - `There are so many food tracking applications, and I've used a lot [of them. I currently use Ate](https://youate.com)`
    - Fix: Move the link boundaries so only 'Ate' (or similar) is the link anchor.

### #103 — Weekly Thing #103 / Apr 27, 2019

- Era: MailChimp
- Overall: Issue is generally in good shape and readable; the main concern is a misplaced link bracket in the intro that makes 'lot of fun! 🎉 Minnebar 14' one anchor, plus a stray duplicate URL in the Give Back section.
  - **[MEDIUM] narrative-break** — The link text awkwardly spans 'lot of fun! 🎉 Minnebar 14' — the opening bracket was placed mid-sentence, suggesting the link anchor was intended to be just 'Minnebar 14' but the bracket is misplaced.
    - `It’s going to be a [lot of fun! 🎉 Minnebar 14](https://minnestar.org/minnebar/) is also this weekend.`
    - Fix: Move the opening bracket so only 'Minnebar 14' is the link text: 'It's going to be a lot of fun! 🎉 [Minnebar 14](...) is also this weekend.'
  - **[LOW] other** — A bare URL appears on its own line immediately before the same URL is linked in the following paragraph, which looks like a leftover/duplicate.
    - `https://www.hackthegap.com

[The mission of Hack the Gap](https://www.hackthegap.com/)`
    - Fix: Remove the stray bare URL line above the 'Give Back' paragraph.
  - **[LOW] malformed-link** — In the 'Yet More Links' list, link titles are split so the opening words are outside the link anchor (e.g., 'MindNode 6' before the bracketed link), which is a recurring pattern throughout this section suggesting a migration/format artifact.
    - `- MindNode 6 [Review: Refined Mind Mapping – MacStories](https://www.macstories.net/reviews/mindnode-6-review-refined-mind-mapping/) www.macstories.net`
    - Fix: Reformat list items so the full title is within the link anchor, or confirm intentional; consistent across items but visually awkward.

### #104 — Weekly Thing #104 / May 4, 2019

- Era: MailChimp
- Overall: Issue is readable and era-normal overall, but several markdown links in the Give Back and Yet More Links sections have anchor text starting mid-phrase, suggesting a migration/formatting artifact worth cleaning up.
  - **[MEDIUM] malformed-link** — The link text boundaries appear misplaced — phrases like '[projects in the world, including Wikipedia]' and '[internet property. Donate to Wikimedia today!]' wrap prose rather than the intended anchor words, making the linked text read awkwardly.
    - `operates some of the largest collaboratively edited reference [projects in the world, including Wikipedia](https://www.wikipedia.org) , a top-ten [internet property. Donate to Wikimedia today!](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&uselang=&country=US)`
    - Fix: Re-anchor the links so that 'Wikipedia' and 'Donate to Wikimedia today' (or similar discrete phrases) are the link text rather than engulfing surrounding sentence fragments.
  - **[LOW] malformed-link** — Throughout the 'Yet More Links' section, link anchor text begins mid-title (e.g., '[me Level Up | Data Stuff]', '[of 200+ Mac menu bar apps]', '[| macOS translation layer for Linux]'), which looks like a migration artifact from a template that split titles.
    - `- 3 Machine Learning Books that Helped [me Level Up | Data Stuff](http://www.datastuff.tech/data-science/3-machine-learning-books-that-helped-me-level-up-as-a-data-scientist/) www.datastuff.tech`
    - Fix: Expand the link text to include the full title of each item (e.g., '[3 Machine Learning Books that Helped me Level Up | Data Stuff](...)').

### #105 — Weekly Thing #105 / May 11, 2019

- Era: MailChimp
- Overall: Readable issue but contains several malformed markdown links where anchor text over-spans prose, plus visible 'mp-photo-alt[]=' migration artifacts in the Microposts section that should be cleaned up.
  - **[HIGH] malformed-link** — The link anchor text incorrectly wraps across a sentence boundary — 'my iPhone. I'd previously used Terminology' is linked when only 'Terminology' should be.
    - `I'm not sure why but I like to have a good dictionary app on [my iPhone. I'd previously used Terminology](https://agiletortoise.com/terminology/) but I really like the modern feel of LookUp.`
    - Fix: Rewrite as: 'a good dictionary app on my iPhone. I'd previously used [Terminology](https://agiletortoise.com/terminology/) but...'
  - **[HIGH] malformed-link** — Link anchor spans a sentence boundary; 'license.' should be outside the link and only 'Donate to Creative Commons today!' linked.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Split into: '...under a Creative Commons license. [Donate to Creative Commons today!](https://creativecommons.org/donate/)'
  - **[HIGH] malformed-link** — Link anchor text incorrectly wraps extra prose; only '@ken_korth' should be the linked text.
    - `I just 💙 this Tech Jam ["comic" sticker! So nicely done @ken_korth](https://twitter.com/ken_korth)`
    - Fix: Rewrite so only '@ken_korth' is linked: '...So nicely done [@ken_korth](https://twitter.com/ken_korth)!'
  - **[MEDIUM] malformed-link** — Link anchor absorbs too much prose; only 'Carcassonne' should be linked.
    - `Had fun playing [board games with friends today: Carcassonne](https://boardgamegeek.com/boardgame/822/carcassonne)`
    - Fix: Rewrite as: 'Had fun playing board games with friends today: [Carcassonne](https://boardgamegeek.com/boardgame/822/carcassonne)...'
  - **[HIGH] migration-artifact** — Literal micropub form-field token 'mp-photo-alt[]=' appears in the body (twice, once duplicated) — a migration artifact from the micropost source that should have been replaced with an image or stripped.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' strings or replace them with the intended image/alt-text.
  - **[MEDIUM] migration-artifact** — A bare URL appears immediately before the same link as markdown — looks like a duplicated/leftover URL from migration.
    - `https://creativecommons.org

[Creative Commons](https://creativecommons.org)`
    - Fix: Remove the bare 'https://creativecommons.org' line above the markdown link.

### #106 — Weekly Thing #106 / May 18, 2019

- Era: MailChimp
- Overall: The issue is readable and largely clean, but the `Yet More Links 🍞` heading lost its `##` prefix during migration and will render as body text rather than a section header.
  - **[MEDIUM] header-error** — This canonical section heading is missing its `##` markdown prefix, so it will render as plain text rather than as an H2 section header, breaking the TOC/structure.
    - `Yet More Links 🍞`
    - Fix: Prepend `## ` to make it `## Yet More Links 🍞`.
  - **[LOW] typo** — Doubled period with stray space (". .") is an obvious punctuation artifact within a quoted passage transition.
    - `And of course I rarely get to build software anymore. . I would like to.`
    - Fix: Remove the extra period and space so it reads `anymore. I would like to.`

### #107 — Weekly Thing #107 / May 25, 2019

- Era: MailChimp
- Overall: Issue is largely clean and readable; the main concern is a leaked 'mp-photo-alt[]=' metadata line in the Microposts section, plus a couple of minor typos.
  - **[HIGH] migration-artifact** — This is a stray micropub/micropost metadata field that leaked into the rendered content instead of being processed as metadata.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' line or replace it with the intended image/alt text.
  - **[LOW] typo** — 'wether' should be 'whether'.
    - `It’s awesome to experience this, and wether other companies catch up`
    - Fix: Change 'wether' to 'whether'.
  - **[LOW] typo** — Missing word — likely 'feels a lot like using an early iPhone'.
    - `driving my Tesla Model 3 feels a lot using an early iPhone`
    - Fix: Insert 'like' before 'using'.

### #108 — Weekly Thing #108 / Jun 1, 2019

- Era: MailChimp
- Overall: Readable overall, but this issue has several malformed link boundaries and two literal 'mp-photo-alt[]=' migration artifacts that should be cleaned up.
  - **[HIGH] malformed-link** — The link text spans across a sentence boundary, incorrectly including 'days meditating. I've been using Headspace' as the anchor text — likely a markdown linking mistake.
    - `crossed over 100 consecutive [days meditating. I've been using Headspace](https://www.headspace.com) and I like`
    - Fix: Rework the link so only 'Headspace' (or similar short phrase) is the anchor text.
  - **[HIGH] malformed-link** — Link anchor text is broken across natural word boundaries in awkward ways, suggesting link fragments were placed incorrectly during editing.
    - `[Good read for Liverpool](https://www.liverpoolfc.com) [fans coming into the UEFA](https://www.uefa.com/uefachampionsleague/) Championship this weekend. It’s nice to see the data [driven analysis made famous in Moneyball](https://en.wikipedia.org/wiki/Moneyball)`
    - Fix: Rework the anchor text to use concise, properly bounded link phrases like 'Liverpool', 'UEFA Champions League', and 'Moneyball'.
  - **[MEDIUM] malformed-link** — This link appears outside the H3 pattern used for other Notable Links entries, and is followed by a stray domain line — inconsistent with the section's structure.
    - `[(Don't Fear) The Reaper](https://www.highcaffeinecontent.com/blog/20190522-(Dont-Fear)-The-Reaper)
www.highcaffeinecontent.com`
    - Fix: Convert to an `### [Title](url)` heading consistent with surrounding Notable Links entries.
  - **[HIGH] migration-artifact** — Literal micropost photo-alt template placeholder left in the body; appears twice and will render as raw text.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' lines or replace them with the intended image/alt text.
  - **[MEDIUM] malformed-link** — The link anchor awkwardly includes an opening quote but excludes the closing one, leaving a stray ' after the link.
    - `I've also got [a bit of a 'man crush](https://www.urbandictionary.com/define.php?term=mancrush) ' on Franklin.`
    - Fix: Adjust link boundaries so the quoted phrase 'man crush' is cleanly wrapped.
  - **[MEDIUM] malformed-link** — Anchor text spans sentence fragments unnaturally — 'and the critically important Let's Encrypt' is used as link text for letsencrypt.org.
    - `[recently launched solutions like Privacy Badger](https://www.eff.org/privacybadger) [and the critically important Let's Encrypt](https://letsencrypt.org) service`
    - Fix: Tighten anchor text to 'Privacy Badger' and 'Let's Encrypt' respectively.

### #109 — Weekly Thing #109 / Jun 8, 2019

- Era: MailChimp
- Overall: Readable issue with several minor migration-era link-bracket issues and a duplicated weekly photo; fixes are cosmetic and easy.
  - **[MEDIUM] image-problem** — The My Weekly Photo image is duplicated — the same image markdown appears twice back-to-back, likely a migration artifact.
    - `![Peony Flowering in Lyndale Rose Garden.](https://files.thingelstad.com/weekly-thing/109/cover.jpg)

![Peony Flowering in Lyndale Rose Garden.](https://files.thingelstad.com/weekly-thing/109/cover.jpg)`
    - Fix: Remove the duplicate image reference so the photo only appears once.
  - **[MEDIUM] malformed-link** — The link text "and our families. Via Patrick Rhone" spans a sentence boundary, indicating the link brackets were placed incorrectly during migration.
    - `[Great, short talk from Michael Pollan](https://michaelpollan.com) on the importance of the fundamental act of cooking food for ourselves [and our families. Via Patrick Rhone](https://www.patrickrhone.net/how-cooking-can-change-your-life-michael-pollan/)`
    - Fix: Split the link so only "Via Patrick Rhone" (or similar attribution phrase) is the link text, not the phrase starting mid-sentence.
  - **[MEDIUM] malformed-link** — The link text awkwardly starts mid-sentence with "years.", indicating misplaced bracket boundaries from migration.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Adjust the link so only "Donate to Let's Encrypt today!" is the link text.
  - **[MEDIUM] malformed-link** — The link text begins mid-title ("Files Confidentially...") with "Exercise-Bike Maker Peloton" left outside the link, and there is a trailing bare domain; this is a malformed bullet.
    - `- Exercise-Bike Maker Peloton [Files Confidentially for IPO - WSJ](https://www.wsj.com/articles/exercise-bike-maker-peloton-files-confidentially-for-ipo-11559746316) www.wsj.com`
    - Fix: Wrap the full title in the link and remove the trailing bare domain (same pattern applies to the SEC.gov bullet below).
  - **[LOW] malformed-link** — Same pattern as the Peloton bullet — the link text starts mid-title with prefix text outside the link and a trailing bare domain.
    - `- SEC.gov | SEC Charges Issuer [With Conducting $100 Million Unregistered ICO](https://www.sec.gov/news/press-release/2019-87) www.sec.gov`
    - Fix: Wrap the complete title in the link and drop the trailing "www.sec.gov".
  - **[LOW] typo** — "in there twenties" should be "in their twenties".
    - `ones that seemed like they were in there twenties`
    - Fix: Change "there" to "their".
  - **[LOW] typo** — Sentence begins with a lowercase "it’s" after a paragraph break.
    - `it’s very interesting to drill down to towns you know`
    - Fix: Capitalize to "It’s".

### #110 — Weekly Thing #110 / Jun 15, 2019

- Era: MailChimp
- Overall: The issue is readable and in generally good shape, but contains several misplaced markdown link boundaries and a small duplicated/stray-URL artifact in the Creative Commons and photo sections.
  - **[MEDIUM] malformed-link** — The link text awkwardly spans a sentence boundary, suggesting the intended link was just 'Make: Magazine' and the lead-in 'This bums me out.' was accidentally absorbed into the link.
    - `[This bums me out. Make: Magazine](https://makezine.com) and Maker Faire's are really cool events.`
    - Fix: Rewrite as 'This bums me out. [Make: Magazine](https://makezine.com) and Maker Faire's are really cool events.'
  - **[MEDIUM] malformed-link** — The link text incorrectly spans two sentences; the period falls inside the link brackets, indicating the link boundary is misplaced.
    - `In addition to donating, you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Rewrite as '...under a Creative Commons license. [Donate to Creative Commons today!](https://creativecommons.org/donate/)'
  - **[LOW] malformed-link** — The link text awkwardly starts with 'as', suggesting the bracket placement is off — intended link is 'Terms of Service; Didn't Read'.
    - `This is where services such [as Terms of Service; Didn't Read](https://tosdr.org) should be able to help`
    - Fix: Rewrite as 'This is where services such as [Terms of Service; Didn't Read](https://tosdr.org) should be able to help'.
  - **[LOW] narrative-break** — The caption 'Giant slip-n-slide in Newton Sledding Hill in South Minneapolis.' is duplicated immediately after the fuller caption, reading like migration metadata that leaked into the body.
    - `![Giant slip-n-slide in Newton Sledding Hill in South Minneapolis.](https://files.thingelstad.com/weekly-thing/110/cover.jpg)

Giant slip-n-slide in Newton Sledding Hill in South Minneapolis celebrating a hot summers day! ☀️💦

Giant slip-n-slide in Newton Sledding Hill in South Minneapolis.`
    - Fix: Remove the duplicated bare caption line, keeping only the descriptive caption and the date/location metadata.
  - **[LOW] migration-artifact** — A bare URL appears immediately above the properly formatted Creative Commons link, suggesting a stray leftover from editing or migration.
    - `https://creativecommons.org

[Creative Commons](https://creativecommons.org) helps you`
    - Fix: Delete the bare 'https://creativecommons.org' line above the paragraph.

### #111 — Weekly Thing #111 / Jun 22, 2019

- Era: MailChimp
- Overall: Readable issue, but it contains a stray micropub form artifact, a duplicated photo caption, and several malformed Yet More Links entries from the migration that should be cleaned up.
  - **[HIGH] narrative-break** — This is a stray micropub form field artifact that leaked into the rendered body between micropost entries.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' line from the Microposts section.
  - **[MEDIUM] narrative-break** — The photo caption is duplicated back-to-back, likely a migration artifact from combining alt text and caption.
    - `Gorgeous evening, clouds overhead at Lake Harriet bandshell for Music in the Park. 🎶

Gorgeous evening, clouds overhead at Lake Harriet bandshell for Music in the Park.`
    - Fix: Remove the duplicate caption line so the description only appears once.
  - **[MEDIUM] malformed-link** — The link text is split mid-title with the leading words outside the link and the domain appended as plain text, a migration formatting artifact repeated throughout 'Yet More Links'.
    - `- 20 Rules For Making the Best Salads [of Your Life | Bon Appétit](https://www.bonappetit.com/gallery/salad-ideas) www.bonappetit.com`
    - Fix: Reformat each Yet More Links entry so the full title is inside the link and the trailing bare domain is removed.
  - **[MEDIUM] malformed-link** — The link text begins mid-sentence ('years. Donate...'), indicating the link markup was misaligned during migration.
    - `Let's Encrypt is possibly one of the most important things to happen on the web in recent [years. Donate to Let's Encrypt today!](https://letsencrypt.org/donate/)`
    - Fix: Adjust the link so only 'Donate to Let's Encrypt today!' (or similar) is the anchor text.
  - **[LOW] malformed-link** — A bare URL appears on its own line immediately before the same URL is linked, likely a leftover from migration.
    - `https://letsencrypt.org

[Let's Encrypt](https://letsencrypt.org)`
    - Fix: Remove the stray bare URL line above the Let's Encrypt paragraph.
  - **[LOW] typo** — 'wether' should be 'whether'.
    - `I track wether I scheduled the meeting`
    - Fix: Change 'wether' to 'whether'.
  - **[LOW] typo** — 'whince' should be 'wince'.
    - `I whince though at it being a VPN service`
    - Fix: Change 'whince' to 'wince'.

### #112 — Weekly Thing #112 / Jun 29, 2019

- Era: MailChimp
- Overall: Readable issue but contains several malformed link anchor boundaries that split sentences awkwardly, plus a few small typos including one in a section heading.
  - **[MEDIUM] malformed-link** — The link anchor text awkwardly splits mid-sentence (e.g., '[format. I greatly enjoyed the event]') suggesting the link boundaries were placed incorrectly, which breaks the natural reading flow.
    - `[SPS' own Amy Patton](https://www.linkedin.com/in/amyjpatton/) [co-hosted this event with Jennifer Tejada](https://www.linkedin.com/in/jenntejada1/) of PagerDuty, and led the Fireside Chat Q&A [format. I greatly enjoyed the event](https://www.thingelstad.com/2019/06/26/excited-to-attend.html)`
    - Fix: Rework the link anchors so they enclose only the relevant phrases rather than splitting clauses across link boundaries.
  - **[LOW] typo** — 'fo' should be 'of' in the heading title.
    - `Jennifer Tejada, CEO fo PagerDuty`
    - Fix: Correct 'fo' to 'of' in the heading.
  - **[LOW] malformed-link** — The link anchor begins mid-sentence with 'license.' making the link text read awkwardly as two merged sentences.
    - `you should consider making your content under a Creative Commons [license. Donate to Creative Commons today!](https://creativecommons.org/donate/)`
    - Fix: Split into two sentences, with only 'Donate to Creative Commons today!' as the linked text.
  - **[LOW] malformed-link** — Link anchor splits the phrase 'day to day' and includes the trailing sentence, which appears to be a misplaced link boundary.
    - `Device backgrounds is an interesting way to bring some art into your day [to day. Via Dense Discovery 42](https://www.densediscovery.com/issues/42)`
    - Fix: Move the link so only 'Dense Discovery 42' is the anchor text.
  - **[LOW] malformed-link** — Mid-sentence link boundary is awkward but readable; noting low-severity pattern consistent with other link splits in this issue.
    - `Blew away previous 45-min PR and spent 17% [of the spin in Zone 5](https://members.onepeloton.com/profile/workouts/7f6d4edc8a9c45d0955410a1df4c83fb)`
    - Fix: Consider linking a cleaner anchor like 'Zone 5' or the workout name.
  - **[LOW] typo** — 'you' should be 'your'.
    - `Download curated wallpapers for you screen`
    - Fix: Change 'you screen' to 'your screen'.
  - **[LOW] typo** — Missing 'of' — should read 'taking the month of July off'.
    - `While I’m taking the month off July`
    - Fix: Rephrase to 'While I'm taking the month of July off'.
  - **[LOW] typo** — 'of' appears to be a stray word; likely should be 'off'.
    - `since he takes July and August of you'll be waiting a bit`
    - Fix: Change 'August of you'll' to 'August off you'll'.

### #113 — Weekly Thing #113 / Aug 17, 2019

- Era: MailChimp
- Overall: Readable issue, but the 'Yet More Links' section has four markdown links whose opening brackets were placed mid-title, producing visibly truncated link text—worth fixing.
  - **[HIGH] malformed-link** — The markdown link bracket starts mid-title after 'for', so the rendered link text will be 'the Mind" - Learning By Shipping' instead of the full title.
    - `- "Bicycle for [the Mind" - Learning By Shipping](https://medium.learningbyshipping.com/bicycle-121262546097) medium.learningbyshipping.com`
    - Fix: Move the opening bracket to the start of the title: `["Bicycle for the Mind" - Learning By Shipping](...)`.
  - **[HIGH] malformed-link** — Link bracket starts mid-sentence, so link text omits the leading 'Escape rooms' words.
    - `- Escape rooms [are very big business - Vox](https://www.vox.com/the-goods/2019/8/7/20749177/escape-room-game) www.vox.com`
    - Fix: Rewrap the brackets around the full title, e.g. `[Escape rooms are very big business - Vox](...)`.
  - **[HIGH] malformed-link** — Link bracket begins mid-title, truncating the link text to 'home – A Whole Lotta Nothing'.
    - `- Tips from 16 years of working from [home – A Whole Lotta Nothing](https://a.wholelottanothing.org/2019/08/09/tips-from-16-years-of-working-from-home/) a.wholelottanothing.org`
    - Fix: Move the opening bracket to the beginning of the title.
  - **[HIGH] malformed-link** — Link bracket starts mid-title, so the rendered anchor omits 'Buying Coffee Won't'.
    - `- Buying Coffee Won't [Make You Poor - The Atlantic](https://www.theatlantic.com/health/archive/2019/07/coffee-financial-advice/594244/) www.theatlantic.com`
    - Fix: Rewrap brackets around the full title.
  - **[LOW] typo** — 'affect' should be 'effect' in this idiom ('to great effect').
    - `LinkedIn has adopted all of the addictive patterns of social media, to great affect.`
    - Fix: Change 'affect' to 'effect'.

### #114 — Weekly Thing #114 / Aug 24, 2019

- Era: MailChimp
- Overall: Readable overall, but several bracket-misplaced links in the WeWork/Apple Card paragraphs and 'Yet More Links' section visibly garble titles, and a stray micropub parameter 'mp-photo-alt[]=' leaked through the migration.
  - **[HIGH] malformed-link** — The link text starts mid-phrase ('a soap opera - The Verge') because the bracket was placed incorrectly; the linked title should include the whole article title.
    - `WeWork isn’t a tech company; it’s [a soap opera - The Verge](https://www.theverge.com/2019/8/15/20806366/we-company-wework-ipo-adam-neumann)`
    - Fix: Rewrap the link so the full article title is the link text, e.g., [WeWork isn't a tech company; it's a soap opera - The Verge](url).
  - **[HIGH] malformed-link** — Bracket placement leaves most of the article title outside the link; only 'IPO - Byrne Hobart - Medium' is actually hyperlinked.
    - `What is We!? Understanding the WeWork [IPO - Byrne Hobart - Medium](https://medium.com/@byrnehobart/what-is-we-understanding-the-wework-ipo-b74f0f1f1b46)`
    - Fix: Move the opening bracket to the start of the title so the entire title is the link text.
  - **[HIGH] malformed-link** — Bracket misplacement makes only a fragment of the article title the link; the linked text reads awkwardly mid-sentence.
    - `check out the related You should opt out of the Apple [Card’s arbitration clause — here’s how](https://www.theverge.com/2019/8/20/20813800/apple-card-pay-arbitration-clause-goldman-sachs-credit-how-to-opt-out) article`
    - Fix: Rewrap so the full title 'You should opt out of the Apple Card's arbitration clause — here's how' is the link text.
  - **[MEDIUM] malformed-link** — The link text begins mid-title because the bracket was placed after 'Now'; the full title should be the link.
    - `- Amazon Forecast – Now [Generally Available | AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-forecast-now-generally-available/) aws.amazon.com`
    - Fix: Move the opening bracket to the start of the title so the entire title is linked.
  - **[MEDIUM] malformed-link** — Bracket starts after 'Eivind', so the author's first name is outside the link text.
    - `- Eivind [Hjertnes | The “I” in Team](https://hjertnes.social/2019/08/21/092057.html) hjertnes.social`
    - Fix: Move the opening bracket to before 'Eivind' so the full title is the link.
  - **[HIGH] migration-artifact** — This is a leftover micropub photo-alt parameter from the micropost import, not prose; it appears as stray text to readers.
    - `mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' line (or convert it to a proper image alt attribute).

### #115 — Weekly Thing #115 / Aug 31, 2019

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but it has a visible migration artifact in the Microposts section and several malformed link boundaries in the 'Yet More Links' list that an editor should clean up.
  - **[HIGH] migration-artifact** — This is a leftover micropub form field artifact that was not cleaned up during migration and renders as visible junk text.
    - `mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove the stray 'mp-photo-alt[]=mp-photo-alt[]=' line from the Little Joy Coffee micropost.
  - **[MEDIUM] malformed-link** — The link text starts mid-title ('the internet') with 'You can heal' left outside the link, a consistent pattern of broken link boundaries in this 'Yet More Links' section.
    - `- You can heal [the internet - Signal v. Noise](https://m.signalvnoise.com/you-can-heal-the-internet/) m.signalvnoise.com`
    - Fix: Reformat so the full title 'You can heal the internet - Signal v. Noise' is the link text.
  - **[MEDIUM] malformed-link** — Link text begins partway through the title; 'Mario Kart Tour Coming' is outside the link anchor.
    - `- Mario Kart Tour Coming [to iOS September 25 - MacStories](https://www.macstories.net/news/mario-kart-tour-coming-to-ios-september-25/)`
    - Fix: Include the full title within the markdown link brackets.
  - **[MEDIUM] malformed-link** — The anchor text starts mid-title, leaving 'Drive A Tank - Tank' as plain text outside the link.
    - `- Drive A Tank - Tank [Driving, Car Crushing, Machine Gun Shooting](https://www.driveatank.com/)`
    - Fix: Move the opening bracket so the full title is the link text.
  - **[LOW] typo** — 'they're' (they are) is used where the possessive 'their' is required.
    - `negatively, impacts they're revenue.`
    - Fix: Change 'they're' to 'their'.
  - **[LOW] malformed-link** — The link bracket captures an unclosed parenthesis '(RFC 2109', making the rendered anchor read awkwardly with unmatched punctuation.
    - `We know this because the authors of the original cookie [technical specification said so (RFC 2109](https://tools.ietf.org/html/rfc2109) , Section 4.3.5).`
    - Fix: Restructure the link so the anchor is 'technical specification' or 'RFC 2109' with properly balanced parentheses.

### #116 — Weekly Thing #116 / Sep 7, 2019

- Era: MailChimp
- Overall: Readable overall, but the issue has several migration-related link boundary problems and literal 'mp-photo-alt[]=' artifacts in the Microposts section that should be cleaned up.
  - **[MEDIUM] malformed-link** — The link anchor text spans a sentence boundary, indicating the markdown link was incorrectly placed across a period — 'first day.' should end the prior sentence and 'I made Nordic Waffles' should be the link.
    - `[first day. I made Nordic Waffles](https://nordicwaffles.com)`
    - Fix: Rewrite as 'first day. I made [Nordic Waffles](https://nordicwaffles.com)' so the link wraps only the product name.
  - **[HIGH] migration-artifact** — Literal micropub photo-alt form field placeholders leaked into the body where images should have rendered; appears twice in the Microposts section.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove the 'mp-photo-alt[]=' artifacts and insert the actual photo(s) with alt text, or delete the stray line.
  - **[MEDIUM] malformed-link** — Two adjacent links have awkward anchor boundaries — the second opens with '[calls "the resistance' and leaves a dangling closing quote outside the link.
    - `This reminds [me a lot of what Pressfield](https://stevenpressfield.com) [calls "the resistance](https://en.wikipedia.org/wiki/Resistance_(creativity)) "`
    - Fix: Re-tokenize as 'what [Pressfield](https://stevenpressfield.com) calls ["the resistance"](https://en.wikipedia.org/wiki/Resistance_(creativity))'.
  - **[LOW] malformed-link** — The link anchor starts mid-title ('beta on the web...') rather than wrapping the full headline; same pattern repeats through the Yet More Links list.
    - `- Apple Music launches a public [beta on the web | TechCrunch](https://techcrunch.com/2019/09/05/apple-music-launches-a-public-beta-on-the-web/) techcrunch.com`
    - Fix: Have the anchor span the whole article title for each bullet in Yet More Links.
  - **[LOW] typo** — 'But the I wonder' is a clear word-order/leftover-word error; should be 'But then I wonder' or 'But I wonder'.
    - `But the I wonder if humans are just`
    - Fix: Change 'But the I wonder' to 'But then I wonder'.
  - **[LOW] typo** — 'in an everyone' should be 'in and everyone'.
    - `Four days in an everyone is doing great!`
    - Fix: Replace 'in an everyone' with 'in and everyone'.

### #117 — Weekly Thing #117 / Sep 14, 2019

- Era: MailChimp
- Overall: Issue #117 is largely clean and readable; minor typos and a list-formatting quirk in the Yet More Links section are the only notable issues.
  - **[LOW] typo** — "your" should be "you're" — a clear homophone typo.
    - `if you don't use it, your gonna lose it`
    - Fix: Change "your gonna" to "you're gonna".
  - **[LOW] typo** — "ulra-wide" is a misspelling of "ultra-wide".
    - `the ulra-wide angle lens`
    - Fix: Correct to "ultra-wide".
  - **[MEDIUM] narrative-break** — In the "Yet More Links" list, the description line after each bullet isn't indented as part of the list item, so it likely renders as a separate paragraph breaking the bullet structure.
    - `- Apple [Arcade — Let the games begin](https://www.youtube.com/watch?v=frLeePH8W9Y) www.youtube.com
100 second overview of games coming in Apple Arcade. 🎮`
    - Fix: Indent the description lines under their parent bullet (or use a sub-bullet) so each item renders as a cohesive list entry.
  - **[LOW] typo** — Missing word — likely "look up an entry".
    - `every time you look you an entry`
    - Fix: Change "look you an entry" to "look up an entry".

### #118 — Weekly Thing #118 / Sep 21, 2019

- Era: MailChimp
- Overall: Readable overall, but several 'Yet More Links' entries have the opening link bracket placed mid-title so the first words aren't linked, and two microposts contain stray 'mp-photo-alt[]=' migration tokens where images should be.
  - **[HIGH] migration-artifact** — Literal micropub form field tokens appear in the body where image alt text should have been rendered, indicating a failed micropost image migration.
    - `mp-photo-alt[]=mp-photo-alt[]=mp-photo-alt[]=`
    - Fix: Remove these tokens or replace with the intended image(s) and alt text.
  - **[HIGH] migration-artifact** — Another stray micropub photo alt field token appears as visible text in the Saturday 11:18 PM micropost.
    - `mp-photo-alt[]=`
    - Fix: Remove the stray token or restore the missing photo with proper alt text.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-title (only 'Guide, iOS 13 Edition — MacSparky' is linked) so 'Announcing the Shortcuts Field' is orphaned plain text outside the link.
    - `- Announcing the Shortcuts Field [Guide, iOS 13 Edition — MacSparky](https://www.macsparky.com/blog/2019/9/announcing-the-shortcuts-field-guide-ios-13-edition) www.macsparky.com`
    - Fix: Move the opening bracket to the start of the title so the entire title is the link text.
  - **[MEDIUM] malformed-link** — The link bracket begins partway through the title, leaving the first half of the headline as unlinked prose.
    - `- PCalc 3.9 Adds Dark Mode and the Latest Shortcuts Features, Expanding [the App's Automation Capabilities - MacStories](https://www.macstories.net/reviews/pcalc-3-9-adds-dark-mode-and-the-latest-shortcuts-features-expanding-the-apps-automation-capabilities/)`
    - Fix: Move the opening bracket to the beginning of the title so the full headline is linked.
  - **[MEDIUM] malformed-link** — Link brackets start mid-title; 'ICONSVG - Quick' is left as plain text instead of being part of the link.
    - `- ICONSVG - Quick [customizable SVG icons for your project](https://iconsvg.xyz/) iconsvg.xyz`
    - Fix: Expand the link text to cover the full title.
  - **[MEDIUM] malformed-link** — Opening bracket begins mid-title, leaving 'Camera Drone Follows' as unlinked prose.
    - `- Camera Drone Follows [Rollercoaster to Capture Dizzying Cinematic Footage](https://petapixel.com/2019/09/11/camera-drone-follows-rollercoaster-to-capture-dizzying-cinematic-footage/?fbclid=IwAR2jzExjYhUplr5LZPr6EpE_qbTRc_XQczovUbBDDHojtW4WzslaYCiAH3E) petapixel.com`
    - Fix: Shift the opening bracket to the start of the title.
  - **[MEDIUM] malformed-link** — The link text begins partway through the title so 'Your Attention Is Sovereign' is not part of the hyperlink.
    - `- Your Attention Is Sovereign [- Start Select Reset Zine 001](https://hwcdn.libsyn.com/p/0/5/7/0573858d24462354/SSRZ_-_001_-_Your_Attention_Is_Sovereign.pdf?c_id=51790010&cs_id=51790010&expiration=1568567308&hwt=851b021d6312de9b14af65da12e2beaf) hwcdn.libsyn.com`
    - Fix: Extend the link text to cover the entire title.

### #119 — Weekly Thing #119 / Sep 28, 2019

- Era: MailChimp
- Overall: Issue is in good shape overall; only a couple of minor typos noted.
  - **[LOW] typo** — Duplicated 'the the' and likely should be 'but the headline'.
    - `This is actually HCL employees unionizing, not Google employees, the the headline including Google gets more clicks.`
    - Fix: Change 'the the headline' to 'but the headline'.
  - **[LOW] typo** — 'too' should be 'to' (as in 'doesn't seem to').
    - `Does it make the game better? Doesn’t seem too.`
    - Fix: Change 'too' to 'to'.

### #120 — Weekly Thing #120 / Oct 5, 2019

- Era: MailChimp
- Overall: Readable issue with era-normal structure, but several Yet More Links / Microposts entries have awkward mid-sentence link anchors from migration and one URL slug appears to be a typo worth verifying.
  - **[HIGH] malformed-link** — The markdown link text contains an unbalanced parenthesis causing awkward rendering with a stray ' ).' after the link.
    - `[52nd birthday, or version 52.0.0 (what?](https://www.thingelstad.com/2018/your-version-number) ).`
    - Fix: Rewrite as '[52nd birthday, or version 52.0.0 (what?)](https://www.thingelstad.com/2018/your-version-number).' with balanced parentheses.
  - **[MEDIUM] malformed-link** — The link text starts mid-sentence ('make it happen') rather than wrapping the title, a migration artifact from the bare-URL bullet format.
    - `- Where to find the hours to [make it happen | Derek Sivers](https://sivers.org/uncomf) sivers.org`
    - Fix: Restructure so the title is the link text, e.g., '[How to find the hours to make it happen – Derek Sivers](https://sivers.org/uncomf)'.
  - **[MEDIUM] malformed-link** — Only part of the sentence is hyperlinked and the domain is appended as bare text, a migration artifact.
    - `- Bike crash left Spokane man unconscious, so his Apple Watch [called 911 | The Seattle Times](https://www.seattletimes.com/seattle-news/bike-crash-left-spokane-man-unconscious-but-his-apple-watch-called-911/) www.seattletimes.com`
    - Fix: Make the full article title the link text and remove the trailing bare domain.
  - **[MEDIUM] malformed-link** — Link text awkwardly spans mid-sentence, likely due to migration of inline link placement.
    - `Did the first Jess King Live workout [on Peloton tonight. Wiped me out!](https://members.onepeloton.com/profile/workouts/147077cd91f84a05a54194d125fc0d56)`
    - Fix: Restructure so a cleaner phrase like '[Jess King Live workout on Peloton](…)' is the linked text.
  - **[LOW] typo** — 'asynchronies' is a typo for 'asynchronous' given the parallel construction with 'synchronous v.'
    - `along synchronous v. asynchronies`
    - Fix: Change 'asynchronies' to 'asynchronous'.
  - **[LOW] typo** — URL slug says '52-thinks' but the post title is '52 Things I Know At 52'; likely a broken/typo URL.
    - `https://www.patrickrhone.net/52-thinks-i-know-at-52/`
    - Fix: Verify and correct the URL slug to '52-things-i-know-at-52' if that is the actual post.

### #121 — Weekly Thing #121 / Oct 12, 2019

- Era: MailChimp
- Overall: Issue is readable but has a missing `##` on the 'My Blog Posts' section header and a consistent pattern of malformed link brackets in the 'Yet More Links' section that truncate link titles.
  - **[HIGH] header-error** — This is a section header styled as plain paragraph text — it's missing the `##` markdown prefix, so it won't render as an H2 like the other section headers.
    - `My Blog Posts ✍️`
    - Fix: Prefix with `## ` to make it a proper H2 heading consistent with other sections.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-title (after 'The Joy'), so only part of the title is linked — this is a migration artifact from a pattern where the full title should be the link text.
    - `- JOMO - The Joy [of Missing Out - Feld Thoughts](https://feld.com/archives/2019/10/jomo-the-joy-of-missing-out.html) feld.com`
    - Fix: Move the opening bracket to the start of the title so the full title 'JOMO - The Joy of Missing Out - Feld Thoughts' is the link text.
  - **[MEDIUM] malformed-link** — The link bracket begins mid-title, splitting the title between plain text and linked text.
    - `- macOS 10.15 Catalina: The [Ars Technica review | Ars Technica](https://arstechnica.com/gadgets/2019/10/macos-10-15-catalina-the-ars-technica-review/) arstechnica.com`
    - Fix: Reposition the opening bracket so the entire title is the link text.
  - **[MEDIUM] malformed-link** — Link text starts mid-title, leaving 'macOS' outside the link in plain text.
    - `- macOS [Catalina: The MacStories Review - MacStories](https://www.macstories.net/news/macos-catalina-the-macstories-review/) www.macstories.net`
    - Fix: Move the opening bracket to include 'macOS' in the link text.
  - **[MEDIUM] malformed-link** — The link bracket begins mid-title, so only part of the product title is linked.
    - `- Different Types of Wine 18" [x 24" Poster - Wine Folly](https://shop.winefolly.com/products/different-types-of-wine) shop.winefolly.com`
    - Fix: Move the opening bracket to the beginning of the title text.
  - **[MEDIUM] malformed-link** — Part of the title is outside the link text; the full title should be linked consistently.
    - `- TikTok owner ByteDance's [first-half books $7 billion in revenue](https://www.cnbc.com/2019/09/30/tiktok-owner-bytedances-first-half-revenue-better-than-expected-at-over-7-billion-sources.html) www.cnbc.com`
    - Fix: Move the bracket to include the full title as the link text.

### #122 — Weekly Thing #122 / Oct 19, 2019

- Era: MailChimp
- Overall: Readable and well-structured issue, but the 'Yet More Links' section has a recurring malformed-link pattern where anchor brackets begin mid-title, which is worth cleaning up.
  - **[MEDIUM] malformed-link** — The link text is split awkwardly — 'MakePass: Create Your Own Apple Wallet' is outside the link and only 'Passes on the Mac - MacStories' is linked, suggesting the link markup was misplaced.
    - `- MakePass: Create Your Own Apple Wallet [Passes on the Mac - MacStories](https://www.macstories.net/reviews/makepass-create-your-own-apple-wallet-passes-on-the-mac/) www.macstories.net`
    - Fix: Rewrite as a single link wrapping the full title: [MakePass: Create Your Own Apple Wallet Passes on the Mac - MacStories](...).
  - **[MEDIUM] malformed-link** — Link text is split; 'Cool New Features' is outside the linked portion, an apparent migration/formatting artifact.
    - `- Cool New Features [in Python 3.8 – Real Python](https://realpython.com/python38-new-features/) realpython.com`
    - Fix: Move the opening bracket so the entire title is the linked anchor text.
  - **[MEDIUM] malformed-link** — Link anchor starts mid-title leaving 'Fish' as bare text outside the link.
    - `- Fish [(shell) fun: event handlers - BrettTerpstra.com](https://brettterpstra.com/2019/10/15/fish-shell-fun-event-handlers/) brettterpstra.com`
    - Fix: Include 'Fish' inside the link brackets so the full title is the anchor.
  - **[MEDIUM] malformed-link** — The title is split so only the tail is linked; consistent with other misplaced brackets in this section.
    - `- Disgraced Google Exec Andy Rubin Quietly Left [His Venture Firm Earlier This Year](https://www.buzzfeednews.com/article/ryanmac/andy-rubin-playground-global-google-quiet-departure) www.buzzfeednews.com`
    - Fix: Wrap the full headline in the link brackets.
  - **[MEDIUM] malformed-link** — Anchor text starts mid-title, leaving 'Brainstorming techniques,' as unlinked prose.
    - `- Brainstorming techniques, [ideas & rules for group brainstorming](https://miro.com/blog/brainstorming-techniques-ideas-rules/) miro.com`
    - Fix: Move the opening bracket to the beginning of the title.
  - **[MEDIUM] malformed-link** — Link anchor begins mid-title, leaving the headline awkwardly split.
    - `- Eliud Kipchoge Breaks Two-Hour Marathon [Barrier - The New York Times](https://www.nytimes.com/2019/10/12/sports/eliud-kipchoge-marathon-record.html) www.nytimes.com`
    - Fix: Include the full headline inside the anchor text.
  - **[LOW] malformed-link** — Anchor text incorrectly spans a sentence boundary; only 'dygraph' should be linked.
    - `This looks like a great time-series [charting package. It’s inspired from dygraph](https://github.com/danvk/dygraphs)`
    - Fix: Limit the link anchor to 'dygraph' rather than including the preceding sentence fragment.
  - **[LOW] typo** — Subject-verb agreement error: plural 'Governments' takes 'have', not 'has'.
    - `Governments, particularly the US Government, has been fighting encryption for years.`
    - Fix: Change 'has been' to 'have been' (or rephrase to singular).

### #123 — Weekly Thing #123 / Oct 26, 2019

- Era: MailChimp
- Overall: Issue is mostly in good shape, but the Richard Stallman H3 link is visibly malformed and should be fixed; a couple of other minor link/typo issues are worth cleaning up.
  - **[HIGH] malformed-link** — The H3 link is malformed — it has two bracket pairs with the first bracket group missing its URL, causing the heading to render incorrectly with visible brackets/pipe.
    - `### [Why Richard Stallman doesn’t matter | ][ Stefano Maffulli](https://maffulli.net/2019/10/17/why-richard-stallman-doesnt-matter/)`
    - Fix: Combine into a single link: `### [Why Richard Stallman doesn't matter | Stefano Maffulli](https://maffulli.net/2019/10/17/why-richard-stallman-doesnt-matter/)`.
  - **[MEDIUM] malformed-link** — The link bracket starts mid-sentence after 'architecturally', so the linked text spans a sentence boundary ('significant. An Architecturally...') indicating a misplaced opening bracket.
    - `architecturally [significant. An Architecturally Significant Requirement (ASR)](https://en.wikipedia.org/wiki/Architecturally_significant_requirements)`
    - Fix: Move the opening bracket so only 'Architecturally Significant Requirement (ASR)' is the link text.
  - **[LOW] typo** — 'their' should be 'there'.
    - `I don't want to think that their is a KPI being incremented.`
    - Fix: Replace 'their' with 'there'.
  - **[LOW] narrative-break** — The word 'article' is duplicated — once inside the link text and once after it — a minor migration/editing artifact.
    - `[Read more in this Nature article](https://www.nature.com/articles/s41586-019-1666-5) article.`
    - Fix: Remove the trailing ' article.' after the link.

### #124 — Weekly Thing #124 / Nov 2, 2019

- Era: MailChimp
- Overall: Issue is in good shape overall; the main concern is a clear grammatical glitch ("as a retires from Dropbox") in the Guido van Rossum entry.
  - **[MEDIUM] typo** — "as a retires" is a clear typo/grammatical error — likely should be "as he retires".
    - `(BDFL) of Python, Guido van Rossum](https://en.wikipedia.org/wiki/Guido_van_Rossum) , as a retires from Dropbox.`
    - Fix: Change "as a retires from Dropbox" to "as he retires from Dropbox".
  - **[LOW] typo** — "wether" should be "whether".
    - `A good read for all men to consider, wether you are a father or not.`
    - Fix: Change "wether" to "whether".
  - **[LOW] typo** — "time what you" should be "time that you" (and "any where" should be "anywhere"), though this is quoted material.
    - `It's valuable, sacred time what you truly won't get any where else.`
    - Fix: If quoted verbatim, leave; otherwise correct to "time that you truly won't get anywhere else."

### #125 — Weekly Thing #125 / Nov 9, 2019

- Era: MailChimp
- Overall: Readable and well-structured issue; main concerns are several markdown links with misplaced brackets that produce awkward anchor text, plus a couple of minor typos.
  - **[MEDIUM] malformed-link** — The link text starts mid-sentence, indicating the link bracket was misplaced and should wrap only 'Doodle'.
    - `Emails trying to find dates to get together with a group [drive me bonkers. I've used Doodle](https://doodle.com/) for years`
    - Fix: Rewrite as 'I've used [Doodle](https://doodle.com/) for years' so the link anchors on the product name.
  - **[MEDIUM] malformed-link** — The link text awkwardly includes the sentence rather than anchoring just on 'Tom'; the URL points to Tom's profile.
    - `I feel the urge to [consider getting one. Link from Tom](https://www.linkedin.com/in/tomkeekley/)`
    - Fix: Change to 'consider getting one. Link from [Tom](https://www.linkedin.com/in/tomkeekley/).'
  - **[MEDIUM] malformed-link** — Link phrasing is split awkwardly across two anchors, resulting in confusing link text.
    - `[setup recurring donations to both Wikipedia](https://donate.wikimedia.org/w/index.php?title=Special:LandingPage&country=US) [and Internet Archive](https://archive.org/donate)`
    - Fix: Restructure to 'setup recurring donations to both [Wikipedia](...) and [Internet Archive](...)'.
  - **[LOW] malformed-link** — Link text starts mid-title, suggesting the opening bracket is misplaced relative to the intended title.
    - `- RSS Feed [Generator, Create RSS feeds from URL](https://rss.app/) rss.app`
    - Fix: Move the bracket to wrap the full title: '[RSS Feed Generator, Create RSS feeds from URL](https://rss.app/)'.
  - **[LOW] malformed-link** — The link text begins mid-sentence ('big deal...'), which is likely a bracket placement error.
    - `- The SpaceX Starship is a very [big deal – Casey Handmer's blog](https://caseyhandmer.wordpress.com/2019/10/29/the-spacex-starship-is-a-very-big-deal/)`
    - Fix: Wrap the full title in the link: '[The SpaceX Starship is a very big deal – Casey Handmer's blog](...)'.
  - **[LOW] typo** — 'wether' should be 'whether'.
    - `But, wether I do it well or not`
    - Fix: Change 'wether' to 'whether'.
  - **[LOW] typo** — 'know' should be 'known' given the context.
    - `I feel the answer to this is very much know.`
    - Fix: Change 'know' to 'known'.

### #126 — Weekly Thing #126 / Nov 16, 2019

- Era: MailChimp
- Overall: Issue #126 is in good shape overall; the main concern is one noticeably fragmented link in the Microposts section and a likely typo ('describers').
  - **[LOW] narrative-break** — Likely typo: 'describers' should be 'describes'.
    - `I haven't been intentional about it, but I think I've been doing something similar to what he describers here.`
    - Fix: Change 'describers' to 'describes'.
  - **[MEDIUM] malformed-link** — The link markdown is fragmented across multiple bracketed segments with stray parentheses and an unclosed quote, producing awkward rendering with orphaned punctuation.
    - `[Missing James Whatley’s (@Whatleydude](https://twitter.com/Whatleydude) [) Five Things on Friday](https://us8.campaign-archive.com/home/?u=a84512488c22cce34b03cbcaa&id=77143865ef) [during its “odd hiatus`
    - Fix: Restructure the sentence so each linked phrase is a clean [text](url) without split parentheses and close the quotation mark properly.
  - **[LOW] malformed-link** — The link wraps only the tail of the phrase, leaving 'Sketchviz - Create and publish Graphviz' unlinked and a trailing bare domain; a common pattern in this era but visibly awkward.
    - `- Sketchviz - Create and publish Graphviz [graphs on the web for free](https://sketchviz.com/new) sketchviz.com`
    - Fix: Consider linking the full title and removing the trailing bare domain, or accept as era-normal.

### #127 — Weekly Thing #127 / Nov 23, 2019

- Era: MailChimp
- Overall: The issue reads well overall, but the My Weekly Photo caption is duplicated and the embedded-tweet conversions in Microposts produced several malformed hashtag links and stray H3 attribution headings that should be cleaned up.
  - **[MEDIUM] narrative-break** — The photo caption is duplicated — the same descriptive sentence appears twice, once with a link and once as plain text, likely a migration artifact.
    - `[The People's Friendship Arch](https://en.wikipedia.org/wiki/People%27s_Friendship_Arch) in Kyiv, Ukraine. Under the arch are two figures, a Ukrainian and Russian worker standing together. Note the crack that has been painted on the arch.

The People's Friendship Arch in Kyiv, Ukraine. Under the arch are two figures, a Ukrainian and Russian worker standing together. Note the crack that has been painted on the arch.`
    - Fix: Remove the duplicated plain-text caption paragraph beginning 'The People's Friendship Arch in Kyiv, Ukraine.'
  - **[MEDIUM] malformed-link** — Twitter embed conversion mis-grouped the link text so the link anchors include arbitrary sentence fragments like 'mesh. I recommend the video! #KubeCon' instead of just the hashtag.
    - `Packed house listening to [AuthN and AuthZ from the @Yelp](https://twitter.com/Yelp?ref_src=twsrc%5Etfw) team sharing their ServiceMesh security story. This is a great talk to think through security requirements you’re trying to solve for with your [mesh. I recommend the video! #KubeCon](https://twitter.com/hashtag/KubeCon?src=hash&ref_src=twsrc%5Etfw)`
    - Fix: Re-link only the @Yelp handle and the #KubeCon hashtag, leaving the surrounding prose as plain text.
  - **[MEDIUM] malformed-link** — Same embed issue — sentence text is wrapped inside hashtag links, breaking the micropost quote's readability.
    - `[It’s incredibly hard to leave #KubeCon](https://twitter.com/hashtag/KubeCon?src=hash&ref_src=twsrc%5Etfw) in sunny San Diego. I wish [it was here every year! #TeamSPS](https://twitter.com/hashtag/TeamSPS?src=hash&ref_src=twsrc%5Etfw)`
    - Fix: Restrict link text to the actual #KubeCon and #TeamSPS hashtags.
  - **[MEDIUM] malformed-link** — Prose is absorbed into hashtag anchor text, producing nonsensical clickable phrases like '" They are even running #kubernetes'.
    - `“We don’t run huge clusters, we run many little clusters, weapon systems, business systems, etc… [“ They are even running #kubernetes](https://twitter.com/hashtag/kubernetes?src=hash&ref_src=twsrc%5Etfw) [& #istio](https://twitter.com/hashtag/istio?src=hash&ref_src=twsrc%5Etfw) [on jets! pic.twitter.com/HwmTFi0Qrt](https://t.co/HwmTFi0Qrt)`
    - Fix: Limit the links to the hashtags (#kubernetes, #istio) and the pic.twitter.com URL only.
  - **[MEDIUM] header-error** — Twitter attribution lines were rendered as H3 section headings, which breaks the Microposts TOC by injecting citation entries at the same level as micropost titles.
    - `### [— Andy Domeier (@AndyJD_) November 21, 2019](https://twitter.com/AndyJD_/status/1197594117695406080?ref_src=twsrc%5Etfw)`
    - Fix: Convert these attribution lines into plain italic text (or blockquote captions) rather than H3 headings; applies to the three embedded tweet citations.
  - **[LOW] typo** — 'Emporor' is a misspelling of 'Emperor' (the URL correctly uses 'Emperors').
    - `At the Old Log [Theatre for The Emporor’s New Clothes](http://oldlog.com/Shows/The-Emperors-New-Clothes)`
    - Fix: Change 'Emporor’s' to 'Emperor’s'.

### #128 — Weekly Thing #128 / Nov 30, 2019

- Era: MailChimp
- Overall: Issue is generally readable but has a missing H2 header for the 'My Blog Posts' section, a malformed Amnesty link, and a couple of minor typos worth fixing.
  - **[MEDIUM] header-error** — The 'My Blog Posts ✍️' section label is plain text, not an H2 heading, so the following H3 appears as an orphan subheading under no section.
    - `My Blog Posts ✍️

### [Kyiv Photowalk](https://www.thingelstad.com/2019/kyiv-photowalk)`
    - Fix: Prefix 'My Blog Posts ✍️' with '## ' to make it a proper H2 section header consistent with other sections.
  - **[LOW] typo** — 'dawned on my' should be 'dawned on me'.
    - `Well, it dawned on my that a Replies 📬 section might be fun`
    - Fix: Change 'my' to 'me'.
  - **[LOW] typo** — 'meeting at John Sweeney gave the keynote' is ungrammatical; 'at' should be 'where' or similar.
    - `We just had our all-company meeting [at John Sweeney gave the keynote](https://www.thingelstad.com/2019/11/12/john-sweeney-gave.html)`
    - Fix: Replace 'at' with 'where' so the sentence reads 'meeting where John Sweeney gave the keynote'.
  - **[MEDIUM] malformed-link** — The URL is in bare parentheses without a preceding bracketed link text, indicating a broken markdown link where 'Surveillance Giants' should be the link text.
    - `Surveillance Giants  (https://www.amnesty.org/en/documents/pol30/1404/2019/en/) lays out how`
    - Fix: Rewrite as '[Surveillance Giants](https://www.amnesty.org/en/documents/pol30/1404/2019/en/) lays out...'.

### #129 — Weekly Thing #129 / Dec 7, 2019

- Era: MailChimp
- Overall: Issue is readable and well-structured, but several links in the Notable/Yet More Links sections have misplaced brackets that produce awkward anchor text, plus a few minor typos.
  - **[MEDIUM] malformed-link** — The link brackets are placed around odd phrases, suggesting the link anchors were split awkwardly during composition — 'shared this Fenwick High School' is the anchor text for the school site, which is confusing prose.
    - `[My colleague Dan Juckniess](https://www.linkedin.com/in/dan-juckniess-68920a10/) [shared this Fenwick High School](https://www.fenwickfriars.com/) commencement speech`
    - Fix: Rewrite so the linked anchor text matches the target (e.g., link 'Fenwick High School' to the school site and leave the verb 'shared' outside the link).
  - **[MEDIUM] malformed-link** — The link bracket spans an unnatural phrase boundary, producing anchor text 'forwarding service. I've been using Maskmail' — likely a misplaced bracket.
    - `This looks like a very well done anonymous email [forwarding service. I've been using Maskmail](https://www.maskmail.net)`
    - Fix: Move the opening bracket so only 'Maskmail' (or similar) is the linked anchor text.
  - **[MEDIUM] malformed-link** — In the 'Yet More Links' list, several items have the link bracket starting mid-title rather than wrapping the whole title, making the titles read oddly.
    - `Two malicious Python libraries caught stealing [SSH and GPG keys | ZDNet](https://www.zdnet.com/article/two-malicious-python-libraries-removed-from-pypi/)`
    - Fix: Wrap the full article title in the link markdown rather than only a trailing fragment.
  - **[LOW] typo** — 'loose' should be 'lose'.
    - `By using a unique email address per service organizations loose the ability to track you`
    - Fix: Change 'loose' to 'lose'.
  - **[LOW] typo** — Missing possessive apostrophe — should be 'people's'.
    - `Violating other peoples privacy`
    - Fix: Change 'peoples' to 'people's'.
  - **[LOW] typo** — 'it's' (contraction) used where possessive 'its' is required.
    - `praising Thanksgiving for it’s decided lack of presents`
    - Fix: Change 'it's' to 'its'.

### #130 — Weekly Thing #130 / Dec 14, 2019

- Era: MailChimp
- Overall: Readable overall, but several misaligned auto-generated link boundaries and two H2 section-break headings ('And…', 'What a mess…') that disrupt the TOC structure; a few small typos as well.
  - **[MEDIUM] header-error** — This H2 appears inside the 'Featured Links' section as a continuation of the Galloway article commentary, but as an H2 it breaks out of that section in the TOC and looks like a top-level section.
    - `## And…`
    - Fix: Change to an H4 or remove the heading and integrate as a prose transition within the Galloway entry.
  - **[MEDIUM] header-error** — This H2 appears between Notable Links entries as commentary on the Guardian article, but as H2 it breaks out of the Notable Links section and creates an orphan top-level heading in the TOC.
    - `## What a mess…`
    - Fix: Demote to regular prose under the Guardian link or use a lower-level heading.
  - **[MEDIUM] malformed-link** — Link boundaries are misaligned across the sentence (e.g., '[teens (research by colleague Jonathan Haidt]' includes an unmatched paren and awkwardly anchors mid-phrase), a common migration artifact of automated link extraction.
    - `Teen [suicide has skyrocketed — up 77%](https://www.thecoddling.com/better-mental-health) for [older teen girls and up 151%](https://www.thecoddling.com/better-mental-health) for younger [teens (research by colleague Jonathan Haidt](http://thecoddling.com/) ).`
    - Fix: Rewrite so link text matches natural phrases, e.g., '[suicide has skyrocketed — up 77% for older teen girls and up 151% for younger teens](…) (research by colleague Jonathan Haidt).'
  - **[LOW] malformed-link** — Link anchor text starts mid-sentence ('ears! Inspired by…') and splits awkwardly across phrases, a migration artifact from auto-linkification.
    - `in your [ears! Inspired by MacSparky's Yule Playlist](https://www.macsparky.com/blog/2018/11/the-yule-apple-music-playlist?rq=yule) I put together our family Christmas favorites and shared it via an Apple [Music Playlist playfully called Christmas Thing](https://music.apple.com/us/playlist/christmas-thing/pl.u-vxVpMsgJqDJ)`
    - Fix: Re-anchor links on natural phrases like 'MacSparky's Yule Playlist' and 'Christmas Thing'.
  - **[LOW] narrative-break** — Photo caption metadata lines are duplicated (caption already appears as image alt text and preceding sentence) and rendered as bare lines without formatting, likely a migration artifact.
    - `Little KLM houses filled with booze.
Nov 17, 2019 at 1:48 AM
Amsterdam Airport Schiphol, Netherlands`
    - Fix: Format as italic caption or a blockquote, or remove the duplicated caption line.
  - **[LOW] typo** — 'your' should be 'you're' — a clear grammatical error, not stylistic.
    - `As your sharing all the great insights you've gleaned`
    - Fix: Change 'As your sharing' to 'As you're sharing'.
  - **[LOW] typo** — 'thing' should be 'think' — obvious typo.
    - `I love this and thing all engineers should try to embody`
    - Fix: Change 'thing' to 'think'.
  - **[LOW] typo** — 'there' should be 'their' — obvious homophone error.
    - `privacy of anyone walking in the public spaces around there house`
    - Fix: Change 'there house' to 'their house'.

### #131 — Weekly Thing #131 / GoatCounter, Hobbies, AR, Leadership, Ring

- Era: Buttondown
- Overall: Issue is in good shape overall; the main concern is the 404 Photograph image confirmed by the static audit, plus a minor capitalization typo.
  - **[MEDIUM] image-problem** — Static audit confirmed this image returns HTTP 404, so the Photograph section renders with a broken image.
    - `![Snow and Pine Trees](https://blotcdn.com/blog_9b22fef1ce9945619fd5d5ec617b3deb/_image_cache/b0d97f7e-05b6-42d9-9d1e-4c26d1e0b656.jpg)`
    - Fix: Replace with a working URL or remove the Photograph section.
  - **[LOW] typo** — Clear capitalization typo ('TInyLetter' instead of 'TinyLetter').
    - `You may think that would be good for TInyLetter`
    - Fix: Change 'TInyLetter' to 'TinyLetter'.

### #133 — Weekly Thing #133 / Clayton Christensen, iPad at 10, Ukraine, Nintendo Switch, Apple Map Expansion

- Era: Buttondown
- Overall: The issue is in good shape overall; main concern is a 404 image in the Photog section plus a few minor typos.
  - **[MEDIUM] image-problem** — Static audit confirmed this image URL returns HTTP 404, leaving the Photog section with a broken image.
    - `![Melting Ice](https://blotcdn.com/blog_9b22fef1ce9945619fd5d5ec617b3deb/_image_cache/d96f4887-7edb-4901-86b8-a149309998de.jpeg)`
    - Fix: Re-host the 'Melting Ice' photo or update the URL to a working source.
  - **[LOW] typo** — 'is music' should be 'his music' — a clear word-level typo.
    - `I couldn't find is music on any of the online services`
    - Fix: Change 'is music' to 'his music'.
  - **[LOW] typo** — 'too' should be 'to' in this context.
    - `some of the areas he contributed too for so many`
    - Fix: Change 'contributed too' to 'contributed to'.
  - **[LOW] typo** — Garbled phrasing; should read 'I continue to like what Manton is doing' — 'like with Reece is' is ungrammatical.
    - `I continue to like with Reece is doing with`
    - Fix: Rewrite as 'I continue to like what Manton is doing with micro.blog'.

### #134 — Weekly Thing #134 / Platform & Product, Corporate Athlete, Mindfulness

- Era: Buttondown
- Overall: Issue is largely clean and readable; main concern is a broken bold span ('** accurately**') that will render visibly wrong, plus a couple of minor grammatical slips.
  - **[MEDIUM] narrative-break** — Stray space inside the bold markers prevents the markdown from rendering as bold, so the asterisks will likely appear as literal characters.
    - `The video will show me ** accurately** what happened`
    - Fix: Remove the spaces inside the bold delimiters: `**accurately**`.
  - **[LOW] narrative-break** — The phrase 'To sum up,' followed by 'some segment...' is ungrammatical — likely meant 'To sum up some segment...' without the comma.
    - `To sum up, some segment of the human experience into a few lines of poetry is an art form to be sure, a kind of compression.`
    - Fix: Remove the comma after 'To sum up' so the sentence reads as intended.
  - **[LOW] narrative-break** — Missing word (likely 'in' or 'to') between 'here' and 'the book' makes the sentence ungrammatical.
    - `There are similar concepts here the book I read recently`
    - Fix: Insert 'in' so it reads 'similar concepts here to the book I read recently' or 'similar concepts here in the book I read recently'.

### #135 — Weekly Thing #135 / Spy Emails, Engineering Strategy, True Fans

- Era: Buttondown
- Overall: Issue is in good shape; only one minor word-order typo noticed.
  - **[LOW] typo** — The phrase 'to I link' is a word-order error; likely should be 'why when linking to something do I link to a store?'
    - `I don't do that, and why when linking to something to I link to a _store_?`
    - Fix: Change 'to I link' to 'do I link'.

### #136 — Weekly Thing #136 / Wikipedia, Side Quest, Latency, Signal

- Era: Buttondown
- Overall: The issue is in good shape overall; only minor typos and a non-canonical section heading were noted.
  - **[LOW] other** — `Photog` is not in the canonical section list for the Buttondown era, but it's a minor stylistic deviation rather than an error.
    - `## Photog`
    - Fix: Consider whether this should be a canonical section name; otherwise leave as is.
  - **[LOW] typo** — 'it's' (contraction of 'it is') should be the possessive 'its'.
    - `since it’s inception`
    - Fix: Change 'it’s inception' to 'its inception'.
  - **[LOW] typo** — The word 'just' is duplicated in the sentence.
    - `just from just not eating`
    - Fix: Remove the redundant 'just'.
  - **[LOW] typo** — 'to sources' should read 'of sources'.
    - `compiled from a variety to sources`
    - Fix: Change 'variety to sources' to 'variety of sources'.

### #138 — Weekly Thing #138 / Covid-19, Credibility, Clearview AI, Hair Freezing

- Era: Buttondown
- Overall: Issue is structurally clean and era-normal; only a handful of minor typos detract from the reading experience.
  - **[LOW] typo** — The word 'novel' is duplicated/misplaced, making the clause read awkwardly.
    - `hence the novel name novel,`
    - Fix: Rewrite as 'hence the name novel,' or similar to remove the duplication.
  - **[LOW] typo** — 'Lookin' is missing the trailing 'g' (likely unintentional given the surrounding formal prose).
    - `Lookin for an extra hour in your day?`
    - Fix: Change to 'Looking for an extra hour in your day?'
  - **[LOW] typo** — 'hav' is missing the trailing 'e'.
    - `I honestly don't hav the background`
    - Fix: Change to 'I honestly don't have the background'.
  - **[LOW] typo** — 'stoping' should be 'stopping'.
    - `in addition to stoping all business travel`
    - Fix: Change 'stoping' to 'stopping'.
  - **[LOW] typo** — 'shred's' is a clear typo; likely intended 'share' or 'shares'.
    - `when companies like Google shred's with the public`
    - Fix: Change to 'when companies like Google share with the public'.

### #139 — Weekly Thing #139 / Control, Energy

- Era: Buttondown
- Overall: Issue is in good shape overall with only two minor typos in the intro and FYI sections.
  - **[LOW] typo** — "drout" is a misspelling of "drought."
    - `allowed mankind to defeat the effects of drout and famine.`
    - Fix: Change "drout" to "drought."
  - **[LOW] typo** — "fine" should be "find" — clear typo in context.
    - `I find, and I’m guessing a lot of people fine, very difficult.`
    - Fix: Change "fine" to "find."

### #140 — Weekly Thing #140 / Conversations, Leadership, Remote, iPad

- Era: Buttondown
- Overall: Issue reads cleanly with only two minor typos; no migration artifacts, broken links, or structural issues.
  - **[LOW] typo** — Duplicated word 'take take'.
    - `**So… let's take take some action!**`
    - Fix: Remove the duplicate 'take'.
  - **[LOW] typo** — 'to' should be 'too'.
    - `and he wanted to get in on it to, and is going`
    - Fix: Change 'it to' to 'it too'.

### #141 — Weekly Thing #141 / We provided 147,360 meals for those in need!

- Era: Buttondown
- Overall: Issue is in good shape overall with only minor typos; no migration artifacts or structural issues detected.
  - **[LOW] typo** — Garbled sentence with duplicated 'was' — likely an editing slip that reads awkwardly.
    - `But, there was that additional amount was out there.`
    - Fix: Rewrite to something like 'But there was an additional amount out there.'
  - **[LOW] typo** — The linked article and section are about iOS 13.4, not 14.4 — a clear factual typo.
    - `There are a lot of new things in iOS 14.4.`
    - Fix: Change '14.4' to '13.4'.
  - **[LOW] typo** — 'breath' should be 'breathe' (verb form).
    - `Mostly this comes down to you can eat the virus, but you cannot breath it.`
    - Fix: Change 'breath' to 'breathe'.

### #142 — Weekly Thing #142 / Signaling, Zoom, Bill Gates, Decision Journal

- Era: Buttondown
- Overall: The issue is in good shape overall with consistent Buttondown-era structure; only a couple of minor homophone typos in the prose.
  - **[MEDIUM] typo** — "your" should be "you're" — a clear grammatical error.
    - `before you realize what's going on your going to get paper towels`
    - Fix: Change "your going" to "you're going".
  - **[LOW] typo** — Two errors: "your" should be "you're" and "here" should be "hear".
    - `If your curious to see and here a bit from a Dr. perspective`
    - Fix: Change to "If you're curious to see and hear a bit from a Dr. perspective".

### #143 — Weekly Thing #143 / Archetypes, Wear a Mask, Zoom

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos worth noting.
  - **[LOW] typo** — 'very say' should be 'very easy' — clear typo.
    - `I believe it is very say to have logical inconsistencies in bullets`
    - Fix: Change 'very say' to 'very easy'.
  - **[LOW] typo** — 'pursuit' should be 'pursue' (verb) — clear grammatical typo.
    - `the mission-driven approach that the best in that craft pursuit`
    - Fix: Change 'pursuit' to 'pursue'.
  - **[LOW] typo** — Anne Frank's name is misspelled as 'Franke'.
    - `We all did the Apollo 11 experience as well as an Anne Franke thing.`
    - Fix: Change 'Anne Franke' to 'Anne Frank'.

### #144 — Weekly Thing #144 / Contact Tracing, Stockdale Paradox, John Prine, Goat 2 Meeting

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos noted, no structural or migration problems.
  - **[LOW] typo** — "site" should be "sight" in this idiom.
    - `Over 6 inches of snowfall in mid-April is never a welcome site.`
    - Fix: Change "welcome site" to "welcome sight".
  - **[LOW] typo** — "jntervals" is a clear typo for "intervals".
    - `The climbing jntervals in`
    - Fix: Correct "jntervals" to "intervals" (note this also appears in the linked post slug).
  - **[LOW] typo** — "bee" should be "be".
    - `This kind of technology could bee used`
    - Fix: Change "bee used" to "be used".
  - **[LOW] typo** — "fo" should be "of".
    - `would cover a huge percentage fo the population`
    - Fix: Change "fo" to "of".

### #145 — Weekly Thing #145 / Permanent, Coronavirus, Zoom Fatigue

- Era: Buttondown
- Overall: Issue #145 is in good shape; the only static-audit finding is a false positive caused by nested brackets in a valid markdown link title.
  - **[LOW] other** — The static audit flagged this as bracketed text with no link, but it is actually inside the H3 link title `[How to Declutter Your Digital Life & Reclaim Your Attention [Guide]](https://doist.com/blog/digital-declutter/)` and renders correctly as part of the title.
    - `[Guide]`
    - Fix: No fix needed; this is a false positive from the static audit due to nested brackets inside the link text.

### #147 — Weekly Thing #147 / Do The Work, Good Writing, Bye Amazon

- Era: Buttondown
- Overall: Issue #147 is in good shape overall; the main concern is the H2 subsection headings nested inside an H3 stream post, which disrupts the document outline.
  - **[LOW] other** — The static audit flagged this as bracketed text with no link, but it's actually inline code (Python dict key access) inside backticks in a code example, so it's valid content, not a malformed link.
    - `['content_html']`
    - Fix: No fix needed; this is a false positive from the static audit.
  - **[LOW] typo** — Inconsistent capitalization of 'Times' (capital I in 'TImes').
    - `including the NY TImes`
    - Fix: Change 'NY TImes' to 'NY Times'.
  - **[MEDIUM] header-error** — Inside the 'The Importance, Accessibility, and Inclusivity of Connecting Online' stream post (H3), the subsections use H2 ('## Work', '## mini minnebar', '## A New Way to Mourn'), which outranks the post's H3 heading and breaks the document outline.
    - `## Work`
    - Fix: Demote these subsection headers to H4 (or at least H3) so they nest properly under the parent H3 post title.
  - **[LOW] typo** — Likely 'and so what' should be 'and so what' — actually reads as 'it filled my day with energy to connect and so what if...' where 'so' appears to be a typo for 'who cares' construction; more clearly, preceding 'connect and so what' seems to be missing a word or should be 'connect, and so what'.
    - `and so what if we couldn't do it`
    - Fix: Consider rephrasing for clarity, though this may be stylistic.

### #148 — Weekly Thing #148 / What Day Is It?, Written Communication, Lisp

- Era: Buttondown
- Overall: Issue is in generally good shape; a handful of minor typos ('angle'/'ankle', 'their'/'there', 'inentional', 'mover') and one truncated-feeling sentence in the Tim Bray intro are worth a quick editorial pass.
  - **[LOW] typo** — 'angle' should be 'ankle' given the context of physical pain when waking.
    - `"Why does your foot and angle hurt for an hour in the morning?"`
    - Fix: Change 'angle' to 'ankle'.
  - **[LOW] typo** — 'their' should be 'there' — a clear homophone error.
    - `I've now gotten to feeling the benefits, and their are now days`
    - Fix: Change 'their are now days' to 'there are now days'.
  - **[LOW] typo** — 'inentional' is a misspelling of 'intentional'.
    - `The only explanation I can offer is that this is inentional`
    - Fix: Change 'inentional' to 'intentional'.
  - **[LOW] typo** — 'lawn mover' should be 'lawn mower'.
    - `We made the jump to an electric lawn mover tonight.`
    - Fix: Change 'lawn mover' to 'lawn mower'.
  - **[LOW] narrative-break** — Sentence is ungrammatical — likely missing a word (e.g., 'On an evening walk I noticed that these trees...').
    - `On an evening walk that these trees with their flowers caught my attention.`
    - Fix: Rewrite to 'On an evening walk, these trees with their flowers caught my attention.'
  - **[LOW] typo** — Missing space after the em dash between 'Blog' and 'Tim' — minor formatting inconsistency.
    - `### [Meta Blog —Tim Bray](https://www.tbray.org/ongoing/When/202x/2020/05/13/Meta-Blog)`
    - Fix: Add a space: 'Meta Blog — Tim Bray'.
  - **[LOW] narrative-break** — Sentence trails off — 'from his.' appears to be missing a word (likely 'from his stats' or similar).
    - `Here he reflects on what he saw on his blog from his.`
    - Fix: Complete the sentence, e.g., 'from his blog stats' or similar.

### #150 — Weekly Thing #150 / Speed, Insane Videoconferencing, OmniFocus, LaTeX

- Era: Buttondown
- Overall: Issue is largely in good shape with typical Buttondown-era structure; a few small typos and one truncated sentence in the Stream section are worth fixing.
  - **[MEDIUM] typo** — "meditating" should be "mediating" — clear word-confusion typo in a bolded sentence.
    - `you should seek to **not have algorithms meditating your content!**`
    - Fix: Change "meditating" to "mediating".
  - **[LOW] typo** — "front he" should be "from the" — obvious typo.
    - `Great retrospective front he outgoing CTO of The New York Times.`
    - Fix: Change "front he" to "from the".
  - **[MEDIUM] narrative-break** — The sentence ends with a stray "&" character, suggesting an HTML entity (&amp;) was truncated or the sentence was cut off mid-word.
    - `Going to stick to traditional burgers&`
    - Fix: Replace the trailing "&" with a period or complete the sentence.
  - **[LOW] typo** — The sentence ends with a dangling "for." suggesting a truncated clause.
    - `I've automated OmniFocus for years with Shortcuts and x-callback-urls for.`
    - Fix: Remove the trailing "for" or complete the intended phrase.

### #151 — Weekly Thing #151 / George Floyd, I Can’t Breathe, Black Lives Matter

- Era: Buttondown
- Overall: Issue #151 is in good shape overall; only two minor typos noted within a guest-authored essay.
  - **[LOW] typo** — Missing space between 'OK?' and 'Because' causing the words to run together.
    - `Do they look OK?Because, [we know](https://www.patrickrhone.net/we-know/).`
    - Fix: Add a space: 'Do they look OK? Because, [we know]...'
  - **[LOW] typo** — 'were' should be 'we're' (contraction of 'we are').
    - `Elbows were bumped (were still in a pandemic).`
    - Fix: Change 'were still in a pandemic' to 'we're still in a pandemic'.

### #152 — Weekly Thing #152 / Juneteenth, Uncomfortable Conversations, Facebook

- Era: Buttondown
- Overall: The issue reads cleanly and renders well; only a few minor word-level typos were spotted.
  - **[LOW] typo** — 'is was' should be 'it was' — clear word-level typo.
    - `I came to the conclusion is was bigger than I thought.`
    - Fix: Change 'is was' to 'it was'.
  - **[LOW] typo** — 'on OmniFocus power user' should be 'an OmniFocus power user'.
    - `I'm on OmniFocus power user`
    - Fix: Change 'on' to 'an'.
  - **[LOW] typo** — 'joines' is a clear misspelling of 'joins'.
    - `This time Matthew McConaughey joines Emmanuel Acho.`
    - Fix: Change 'joines' to 'joins'.
  - **[LOW] typo** — 'it's' (it is) should be possessive 'its'.
    - `when it’s quality is really barely at entertainment level`
    - Fix: Change 'it’s' to 'its'.
  - **[LOW] typo** — 'Wether' should be 'Whether'.
    - `Wether you adopt OKR's formally or informally`
    - Fix: Correct 'Wether' to 'Whether'.

### #153 — Weekly Thing #153 / Values Oasis, Bison, Masks

- Era: Buttondown
- Overall: Issue is in generally good shape; only minor typos noted, no structural or migration problems.
  - **[LOW] typo** — Opening word uses a stray double-quote instead of an apostrophe in "I'm".
    - `I"m writing this on Friday night`
    - Fix: Change `I"m` to `I'm`.
  - **[LOW] typo** — Missing word — should be "this is right".
    - `sure hope that this right.`
    - Fix: Change to "sure hope that this is right."
  - **[LOW] typo** — Wrong homophone — should be "their" not "there".
    - `Often there mane would be layered thick`
    - Fix: Change `there mane` to `their mane`.
  - **[LOW] typo** — Adjective used where adverb is needed — should be "incredibly hard".
    - `sometimes they are incredible hard to see`
    - Fix: Change `incredible` to `incredibly`.
  - **[LOW] typo** — Verb agreement error — should be "will announce".
    - `that Apple will announced at WWDC`
    - Fix: Change `will announced` to `will announce`.

### #154 — Weekly Thing #154 / Giving Feedback, Apple WWDC, Anti-Encryption

- Era: Buttondown
- Overall: Issue renders cleanly with only minor typos; no migration artifacts or structural problems.
  - **[LOW] typo** — The original Macintosh used the Motorola 68000 CPU, not the 6500; this appears to be a clear factual typo.
    - `Motorola 6500 CPU`
    - Fix: Change '6500' to '68000'.
  - **[LOW] typo** — 'does't' is a misspelling of 'doesn't'.
    - `it does't work for teams`
    - Fix: Correct 'does't' to 'doesn't'.
  - **[LOW] narrative-break** — Stray space inside the bold markers before 'with' may cause the bold to render awkwardly or leave a visible extra space.
    - `**Saturday, September 5th **with issue #155`
    - Fix: Remove the trailing space inside the bold markers: '**Saturday, September 5th** with'.
  - **[LOW] typo** — Double period at end of sentence (also repeated in the iOS/iPadOS entry) is an obvious typo.
    - `their take on the new things coming in tvOS..`
    - Fix: Replace '..' with a single '.'.

### #155 — Weekly Thing #155 / Menu Engineers, Halo, RFC8890

- Era: Buttondown
- Overall: The issue is in good shape overall; only a few minor typos were found.
  - **[LOW] typo** — 'Timber' should be 'timbre' when referring to voice quality.
    - `Information about the timber of my voice?`
    - Fix: Change 'timber' to 'timbre'.
  - **[LOW] typo** — Duplicated phrase 'the start of the start of'.
    - `Then we went to the start of the start of the [Dakota Rail Regional Trail]`
    - Fix: Remove one 'the start of'.
  - **[LOW] typo** — Duplicated word 'the the'.
    - `a gorgeous 15 mile ride around the the chain of lakes.`
    - Fix: Remove one 'the'.

### #156 — Weekly Thing #156 / Identity, AI, Peloton, UPSERT

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor its/it's typos and a duplicated site name in one headline.
  - **[LOW] typo** — "it's" should be "its" (possessive), not the contraction.
    - `ask yourself if it’s use is informing your identity?`
    - Fix: Change "it's use" to "its use".
  - **[LOW] typo** — "it's" should be "its" (possessive).
    - `I found this rose bush with it’s message to the dogs funny.`
    - Fix: Change "it's message" to "its message".
  - **[LOW] other** — Duplicated site name "zen habits zen habits" in the title, likely from the source <title> tag.
    - `### [The Subtle Power of Changing Your Identity - zen habits zen habits](https://zenhabits.net/identity/)`
    - Fix: De-duplicate to "zen habits".

### #157 — Weekly Thing #157 / Superpower, Dune, Three Year Rule

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor typos noticed, no structural or migration issues.
  - **[LOW] typo** — 'out-and=back' contains an equals sign where a hyphen should be, an obvious typo.
    - `Tammy and I had a great 28 mile out-and=back ride`
    - Fix: Change 'out-and=back' to 'out-and-back'.
  - **[LOW] typo** — 'what as up' should be 'what was up' — clear typo.
    - `Tammy found out via NextDoor what as up`
    - Fix: Replace 'what as up' with 'what was up'.

### #158 — Weekly Thing #158 / Blacklight, Whistleblower, Fly Fishing

- Era: Buttondown
- Overall: Issue is clean and well-structured; only a minor typo ("out" for "our") noted.
  - **[LOW] typo** — "out plan" should be "our plan" — clear word-level typo.
    - `**Installing:** **Netflix** because out plan to cancel our subscription`
    - Fix: Change "out plan" to "our plan".

### #159 — Weekly Thing #159 / 911 Outage, Small Tech, Workflows

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos/grammar slips worth noting.
  - **[MEDIUM] typo** — "Your" should be "You're" — clear homophone typo.
    - `Your in control, not some algorithm.`
    - Fix: Change "Your" to "You're".
  - **[LOW] typo** — Reads as a negation error — should be "do not" / "don't" rather than "do I" (also ends with a period rather than a question mark).
    - `Also, do I subscribe to any event driven breaking news bulletins.`
    - Fix: Change to "Also, I don't subscribe to any event driven breaking news bulletins."
  - **[LOW] typo** — "Effectivenss" is misspelled (missing an 'e').
    - `keys to achieving and maintaining Effectivenss.`
    - Fix: Change to "Effectiveness".

### #160 — Weekly Thing #160 / Unlived Life, Disinformation, Snowflake ❄️

- Era: Buttondown
- Overall: Issue is in good shape overall with only minor typos and one lost special character in a name; no structural or migration issues.
  - **[LOW] typo** — The literal '?' appears where Maciej Cegłowski's surname should be — likely a character encoding/migration artifact where a special character was lost.
    - `Maciej ? was in Hong Kong`
    - Fix: Replace '?' with 'Cegłowski' (or remove the placeholder).
  - **[LOW] typo** — 'explaining her why' is ungrammatical; should be 'explaining why' (Kent Beck is male, but the issue is the stray 'her').
    - `Beck doesn't really answer the how, but does a great job explaining her why this is so hard.`
    - Fix: Remove 'her' so it reads 'explaining why this is so hard'.
  - **[LOW] typo** — 'there' should be 'their'.
    - `Citizens should not be forced to send there data all over the globe`
    - Fix: Change 'there' to 'their'.
  - **[LOW] typo** — Missing subject 'I' — should read 'I told Tammy that I was going to have to say something nice'.
    - `I told Tammy that was going to have to say something nice`
    - Fix: Insert 'I' after 'that'.

### #161 — Weekly Thing #161 / Letter, Asterisk, You Should Write ✍️

- Era: Buttondown
- Overall: Issue is largely clean and readable, but contains an un-substituted `{{email_link}}` template tag in the LinkedIn share link that should be fixed.
  - **[HIGH] migration-artifact** — The `{{email_link}}` template placeholder was not substituted and will render as literal text in the share URL.
    - `Help others learn by [sharing on LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url={{email_link}}).`
    - Fix: Replace `{{email_link}}` with the actual archive URL or the Buttondown merge variable that renders properly.
  - **[MEDIUM] narrative-break** — The blockquote closes without a closing quotation mark, leaving the quoted dialogue unterminated.
    - `> “He's in England,” she said, “and there's only so much you can do on Zoom.`
    - Fix: Add a closing curly quote after 'Zoom.' to match the opening quote.
  - **[LOW] typo** — 'to' should be 'too' in this context.
    - `Hopefully a few of you have enjoyed it to.`
    - Fix: Change 'to' to 'too'.

### #162 — Weekly Thing #162 / iPhone 12, Lidar, Quibi

- Era: Buttondown
- Overall: Issue reads well overall; main concerns are an unsubstituted `{{email_link}}` template tag in the Facebook share link and a malformed URL in the FYI section, plus a few small typos.
  - **[MEDIUM] typo** — 'inks' should be 'links' — clear typo in the intro.
    - `Let's jump right into the inks this week.`
    - Fix: Change 'inks' to 'links'.
  - **[HIGH] migration-artifact** — The `{{email_link}}` template tag was not substituted, so the Facebook share link is broken in the archive.
    - `[sharing the Weekly Thing](https://www.facebook.com/sharer/sharer.php?u={{email_link}})`
    - Fix: Replace `{{email_link}}` with the actual archive URL for this issue.
  - **[MEDIUM] malformed-link** — The URL has a stray encoded quote (%22) at the end, which will break or redirect the link.
    - `[Global coronavirus rise by one-day record of 400,000](https://news.trust.org/item/20201017151359-xc8gp/%22)`
    - Fix: Remove the trailing %22 from the URL.
  - **[LOW] typo** — Stray comma before the period — minor punctuation error.
    - `most likely lower than yours,.`
    - Fix: Remove the comma before the period.
  - **[LOW] typo** — Author's name is Seth Godin; 'Goden' is a misspelling.
    - `Goden is typically short`
    - Fix: Change 'Goden' to 'Godin'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `Most likely your not writing these systems`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — Inconsistent capitalization — should be 'Lidar' as used elsewhere in the paragraph.
    - `and **not** using LIdar`
    - Fix: Change 'LIdar' to 'Lidar'.

### #163 — Weekly Thing #163 / BeOS, Management Track, Writing is Thinking

- Era: Buttondown
- Overall: Generally clean issue; the main concerns are two unrendered `{{email_link}}` template placeholders and a URL with a stray `%22` that break links in the archive.
  - **[MEDIUM] migration-artifact** — The `{{email_link}}` template placeholder appears unrendered in the archive, leaving a broken share URL.
    - `[sharing on LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url={{email_link}})`
    - Fix: Replace `{{email_link}}` with the canonical archive URL or remove the share link for the static archive.
  - **[MEDIUM] migration-artifact** — Second occurrence of the unrendered `{{email_link}}` template placeholder in the archive page.
    - `[sharing this on LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url={{email_link}})`
    - Fix: Replace with the canonical archive URL or remove the share link.
  - **[MEDIUM] malformed-link** — The URL ends with a stray `%22` (encoded quote), which will produce a 404 when the link is followed.
    - `[including scraping](https://www.eff.org/deeplinks/2018/04/scraping-just-automated-access-and-everyone-does-it%22)`
    - Fix: Remove the trailing `%22` from the URL.
  - **[LOW] malformed-link** — The mailto link has `jamie@` with no domain, making it a malformed email address.
    - `[email them](mailto:jamie@?subject=`
    - Fix: Complete the address to `jamie@thingelstad.com` or similar.
  - **[LOW] typo** — 'coding spent points' appears to be a typo for 'coding sprint points' given the earlier reference to sprint points.
    - `And yes, while you are not coding spent points you absolutely must be up-to-speed`
    - Fix: Change 'spent points' to 'sprint points'.

### #164 — Weekly Thing #164 / Raspberry Pi 400, Time Blocking, Platform

- Era: Buttondown
- Overall: The issue is largely in good shape; the main concern is the unrendered `{{email_link}}` template placeholder in the LinkedIn share link.
  - **[HIGH] malformed-link** — The LinkedIn share link contains an unresolved template placeholder `{{email_link}}` instead of the actual URL, producing a broken share link.
    - `[sharing this on LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url={{email_link}})`
    - Fix: Replace `{{email_link}}` with the archive URL of this issue (or the appropriate Buttondown merge variable) so the share link resolves correctly.
  - **[LOW] other** — The prior static audit flagged `[Event Title]` as bracketed text with no link, but this is legitimate prose describing the author's calendar convention, not a malformed link — the static finding is a false positive.
    - `---

## Stream`
    - Fix: Ignore the static finding; no change needed.

### #165 — Weekly Thing #165 / Sessions, Friluftsliv, Everlong

- Era: Buttondown
- Overall: The issue is in good shape overall; the main concern is the unresolved `{{email_link}}` template placeholder appearing twice in the LinkedIn share links.
  - **[MEDIUM] migration-artifact** — The `{{email_link}}` template placeholder appears unreplaced in the rendered URL, producing a broken share link.
    - `[sharing on LinkedIn](https://www.linkedin.com/shareArticle?mini=true&url={{email_link}})`
    - Fix: Replace `{{email_link}}` with the Buttondown-appropriate merge tag (e.g., the archive URL) or a static URL to the issue.

### #166 — Weekly Thing #166 / Chess, Disruption, M1 Macs, Five Hindrances

- Era: Buttondown
- Overall: Issue is in good shape overall; only a couple of minor typos in the M1 Macs section.
  - **[LOW] typo** — "The there" appears to be a typo for "The other" or similar.
    - `The there notable thing here is stuff that the M1 does in the chip`
    - Fix: Change "The there notable thing" to "The other notable thing".
  - **[LOW] typo** — "fo" is a typo for "of".
    - `I can’t wait to get my hands on one fo these.`
    - Fix: Change "one fo these" to "one of these".

### #167 — Weekly Thing #167 / Production Oriented Development, Fathom

- Era: Buttondown
- Overall: Issue is otherwise clean and readable; the main concern is one unsubstituted template tag in the Facebook share link.
  - **[HIGH] migration-artifact** — The Facebook share link contains an unrendered template tag `{{email_link}}` that was never substituted, so the share URL is broken.
    - `[sharing the Weekly Thing](https://www.facebook.com/sharer/sharer.php?u={{email_link}})`
    - Fix: Replace `{{email_link}}` with the actual archive URL for this issue or remove the share link.

### #168 — Weekly Thing #168 / Buy Gifts, Gratitude, DeepMind

- Era: Buttondown
- Overall: The issue is in good shape overall with no migration artifacts, broken links, or narrative breaks; only a minor section-name deviation ('Recommended' vs. canonical 'Recommended Links').
  - **[LOW] other** — The canonical section name in this era is 'Recommended Links'; this issue uses 'Recommended' instead, which deviates slightly from the standard section naming but is still readable.
    - `## Recommended`
    - Fix: Consider changing to '## Recommended Links' for consistency with other issues.

### #169 — Weekly Thing #169 / Ted Lasso, Think for Yourself, Range

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos noted.
  - **[LOW] typo** — 'Ted lasso' should be capitalized as 'Ted Lasso' consistent with the rest of the issue.
    - `I greatly enjoyed Ted lasso.`
    - Fix: Capitalize to 'Ted Lasso'.
  - **[LOW] typo** — Two trailing periods instead of an ellipsis or single period.
    - `This dives deeper into the characters.. `
    - Fix: Change to a single period or a proper ellipsis.
  - **[LOW] typo** — 'event' is a typo for 'even'.
    - `most workers don’t event want to think about their tools`
    - Fix: Change 'event' to 'even'.

### #170 — Weekly Thing #170 / MeetingBar, Platforms, Wikipedia

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and one awkward sentence in the FYI section.
  - **[LOW] typo** — 'retun' is a clear typo for 'return'.
    - `We definitely want to retun in the summer.`
    - Fix: Change 'retun' to 'return'.
  - **[LOW] typo** — 'int' is a typo for 'in'.
    - `A list of 25 very solid recommendations for engineers to adopt and consider int their career.`
    - Fix: Change 'int' to 'in'.
  - **[LOW] typo** — 'bit fan' should be 'big fan'.
    - `I am a bit fan of [Streaks](https://streaksapp.com)`
    - Fix: Change 'bit fan' to 'big fan'.
  - **[LOW] narrative-break** — The second 'doesn't' appears to be a wrong-word error; likely should be 'does'.
    - `This article doesn't have answers, but it doesn't a good job of illustrating`
    - Fix: Change 'it doesn't a good job' to 'it does a good job'.
  - **[LOW] narrative-break** — The phrase 'and on we noted' reads like a missing word (e.g., a date) in the sentence.
    - `My brother Isaiah and his family visited this last weekend and on we noted the 5th year since`
    - Fix: Rephrase, e.g., 'and we noted the 5th year since' or insert the missing date.

### #171 — Weekly Thing #171 / Earthrise, Firecracker, Rivian

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor typos noted.
  - **[LOW] typo** — Mismatched quotation marks — opens with straight double quote and closes with single quote/apostrophe.
    - `I think it is best described as "betters'.`
    - Fix: Change the closing `'` to `"` so it reads `"betters".`
  - **[LOW] typo** — 'paranthesis' is a misspelling of 'parenthesis'.
    - `The first number is minutes and the kcal is in paranthesis.`
    - Fix: Correct to 'parentheses'.

### #173 — Weekly Thing #173 / Minot, Unicorn, Bunch

- Era: Buttondown
- Overall: The issue is in good shape overall with consistent structure; only a couple of minor typos noted.
  - **[LOW] typo** — "light" appears to be a typo for "lot" — "Sounds an awful lot like news" is the intended phrase.
    - `Sounds an awful light like news doesn't it?`
    - Fix: Change "light" to "lot".
  - **[LOW] typo** — "Mudy" is a typo for "Muddy".
    - `Day 9 of the [February Photoblogging Challenge](https://micro.welltempered.net/2021/01/30/february-photoblogging-challenge.html): **Mudy.**`
    - Fix: Correct "Mudy" to "Muddy" (if that was the intended challenge word).

### #175 — Weekly Thing #175 / Crontab, Fry''s, Daft Punk

- Era: Buttondown
- Overall: The issue is in good shape overall; only a minor advise/advice word-choice typo was noted.
  - **[LOW] typo** — "advise" (verb) should be "advice" (noun) in this context.
    - `This advise captures how I tend to deal with information online.`
    - Fix: Change "advise" to "advice".

### #176 — Weekly Thing #176 / Brave Search, Speed, Finger.Farm

- Era: Buttondown
- Overall: Issue is well-structured and readable; main concern is a truncated sentence in the intro about renting mountain bikes, plus a couple of minor typos.
  - **[MEDIUM] narrative-break** — Sentence truncates mid-clause — 'at least on' has no object/completion before the emoji.
    - `We've got some hiking and I think we are going to rent mountain bikes at least on 😎`
    - Fix: Complete the sentence (e.g., 'at least one day') or revise to close the thought.
  - **[LOW] typo** — 'aware' should be 'award' — clear typo.
    - `This system is winning some kind of aware for referencing keywords.`
    - Fix: Change 'aware' to 'award'.
  - **[LOW] typo** — 'affect' should be 'effect' here (noun usage).
    - `There has been a drop in writing about Zoom fatigue but the affect is still real.`
    - Fix: Change 'affect' to 'effect'.

### #178 — Weekly Thing #178 / Reverse Meetings, OODA Loop, Hockey Goalies

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor typo ('way o drive') and a small markdown bold-spacing quirk noted.
  - **[LOW] typo** — 'way o drive' should be 'way to drive' — missing letter.
    - `It could just be a different way o drive consensus`
    - Fix: Change 'way o drive' to 'way to drive'.
  - **[LOW] other** — The bold markdown has a leading space after the opening `**`, which can prevent proper bold rendering in some parsers.
    - `** Observe → Orient → Decide → Act ↩**`
    - Fix: Remove the space after the opening `**` so it renders as bold.

### #179 — Weekly Thing #179 / Nemawashi, Transformation, Geldingadalur

- Era: Buttondown
- Overall: Issue is in good shape overall with only minor typos and a duplicated list number; nothing that breaks the archive reading experience.
  - **[LOW] other** — Duplicated word 'and and' — minor typo.
    - `I'm enjoying an early arrival of spring and and looking forward to longer and warmer days`
    - Fix: Remove the duplicate 'and'.
  - **[LOW] typo** — 'fo' should be 'of'.
    - `fabulous writeup from [Tom Sparks](https://www.linkedin.com/in/thomas-sparks-8296172b/) about our adoption fo Essential`
    - Fix: Change 'fo' to 'of'.
  - **[LOW] other** — Two list items are both numbered '2' — numbering skips from 2 to 2 to 3.
    - `2. It is interesting to hear the dialogue between Sven and`
    - Fix: Renumber the list items sequentially.

### #180 — Weekly Thing #180 / Tetris, Ever Given, Backstory

- Era: Buttondown
- Overall: The issue is in good shape overall with no migration artifacts or structural problems; only minor its/it's typos and one slightly awkward sentence.
  - **[LOW] typo** — 'your' should be 'you're' — a clear grammatical error.
    - `If your looking for a high-quality family show`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — 'it's' (contraction) is used where possessive 'its' is required.
    - `intimidated by it’s depth and length`
    - Fix: Change 'it's' to 'its'.
  - **[LOW] typo** — 'it's' should be possessive 'its'.
    - `Darkroom continues to impress me with it’s native approach`
    - Fix: Change 'it's' to 'its'.
  - **[LOW] typo** — 'it's' should be possessive 'its'.
    - `very intrigued by the Ever Given and it’s situation`
    - Fix: Change 'it's' to 'its'.
  - **[LOW] typo** — 'it's' should be possessive 'its'.
    - `found this read on it’s leadership`
    - Fix: Change 'it's' to 'its'.
  - **[LOW] narrative-break** — Sentence appears to be missing a noun after 'profound' (e.g., 'a profound statement'), making it read oddly.
    - `That is a profound, and I suspect, true.`
    - Fix: Insert the missing noun, e.g., 'That is a profound statement, and I suspect, true.'

### #181 — Weekly Thing #181 / Grit, Collectible, Crypto

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor prose issues noted.
  - **[LOW] typo** — Sentence appears truncated — 'faster than light and physics can possibly' lacks a verb (e.g., 'keep up').
    - `Computational photography is marching forward faster than light and physics can possibly.`
    - Fix: Complete the sentence, e.g., '...faster than light and physics can possibly keep up.'
  - **[LOW] typo** — 'your' should be 'you're'.
    - `If your someone like Seth Godin`
    - Fix: Change 'your' to 'you're'.

### #183 — Weekly Thing #183 / Visidata, FTP, Amazon

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos/grammar slips noted.
  - **[LOW] typo** — Likely typo — should be 'late one' → 'late one night' or 'late tonight'; the phrase doesn't parse.
    - `It is late one tonight.`
    - Fix: Change to 'It is late tonight.' or 'It is late one night.'
  - **[LOW] typo** — Grammatical error — should be 'I've gone back to'.
    - `I've went back to my`
    - Fix: Replace 'went' with 'gone'.
  - **[LOW] typo** — 'and I isn't' is ungrammatical; likely meant 'and it isn't'.
    - `This same structure is probably good for more than just technical books, and I isn't the way that a lot of people might do it.`
    - Fix: Change 'and I isn't' to 'and it isn't'.
  - **[LOW] typo** — Link text spells 'Cayuna' while the URL and proper name is 'Cuyuna'.
    - `[Cayuna Lakes MTB](https://www.cuyunalakesmtb.com)`
    - Fix: Correct link text to 'Cuyuna Lakes MTB'.

### #184 — Weekly Thing #184 / UML, Vizy, Markdown

- Era: Buttondown
- Overall: Issue is in good shape overall with valid structure and links; only minor typos noted.
  - **[LOW] typo** — Appears to be an extraneous 'the' before the author's surname — reads awkwardly.
    - `but the Garbarino correctly pivots right away`
    - Fix: Remove 'the' so it reads 'but Garbarino correctly pivots right away'.
  - **[LOW] typo** — 'thought' appears to be a typo for 'though'.
    - `It is interesting to poke at new ones thought to see what else they may offer.`
    - Fix: Change 'thought' to 'though'.
  - **[LOW] typo** — 'let's' (let us) is used where 'lets' (allows) is intended.
    - `Micro.blog let's me pull out my phone`
    - Fix: Change 'let's' to 'lets'.
  - **[LOW] typo** — 'fo' is a typo for 'of'.
    - `share a video fo the drawing being created`
    - Fix: Change 'fo' to 'of'.
  - **[LOW] typo** — Reads as a grammatical slip — likely intended 'so the teams work in unison' (this is inside a blockquote so may be source quote; low confidence).
    - `aligning this structure between engineering, product, and design as much as possible to the teams work in unison`
    - Fix: Verify against source; if quoting verbatim, consider adding [sic], otherwise correct to 'so the teams work in unison'.

### #185 — Weekly Thing #185 / Signal, Peloton, Meebits

- Era: Buttondown
- Overall: Issue is in generally good shape; a couple of minor typos and one broken JAXJOX URL are the only notable issues.
  - **[LOW] typo** — "do with" should be "do wish" — clear word substitution typo.
    - `I do with the company was committing to more than just software fixes.`
    - Fix: Change "I do with the company" to "I do wish the company".
  - **[MEDIUM] malformed-link** — The URL has a trailing "a" making the domain `jaxjox.coma` which is a broken link.
    - `[JAXJOX](https://jaxjox.coma)`
    - Fix: Change the URL to https://jaxjox.com.
  - **[LOW] typo** — Missing apostrophe in possessive "Facebook's".
    - `Signal went ahead and used Facebooks targeting system`
    - Fix: Change "Facebooks" to "Facebook's".

### #186 — Weekly Thing #186 / Blockchain, Pairing, Sharding

- Era: Buttondown
- Overall: The issue is in good shape overall with only minor wording issues; content and structure render correctly.
  - **[LOW] narrative-break** — The bullet reads awkwardly with a duplicated 'with' — likely should be 'Share the Weekly Thing with your networks.'
    - `- **Share** with the [Weekly Thing](https://weekly.thingelstad.com/?tag=share) with your networks.`
    - Fix: Remove the first 'with' so it reads 'Share the [Weekly Thing] with your networks.'
  - **[LOW] typo** — 'do do' is a typo for 'to do'.
    - `I've been using Pinata do do some playing with`
    - Fix: Change 'do do' to 'to do'.

### #187 — Weekly Thing #187 / AirTags, M1 iPad Pro, Flamingo

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and a missing space after a link noted.
  - **[LOW] typo** — 'heal' should be 'heel' — this is a clear homophone typo in reference to shoe soles.
    - `As I looked closer I noticed the **entire heal was crumbling into pieces**`
    - Fix: Change 'heal' to 'heel'.
  - **[LOW] typo** — 'Where or where' should be the idiom 'Where oh where'.
    - `Where or where will the iPad platform go?`
    - Fix: Change 'Where or where' to 'Where oh where'.
  - **[LOW] other** — Missing space between the closing link parenthesis and the word 'was', causing the words to render joined.
    - `[Bill Atkinson](https://en.wikipedia.org/wiki/Bill_Atkinson)was doing`
    - Fix: Add a space: '[Bill Atkinson](...) was doing'.

### #188 — Weekly Thing #188 / Ethereum, Emulator, Ephemerality

- Era: Buttondown
- Overall: Issue is in good shape overall with only one minor typo noted.
  - **[LOW] typo** — "wan't" is a clear typo for "want".
    - `This is so incredibly awesome. I wan't to sail the Firmware Sea.`
    - Fix: Change "wan't" to "want".

### #189 — Weekly Thing #189 / TiddlyWiki, JsonLogic, Smiling

- Era: Buttondown
- Overall: Issue is in good shape overall; only a few minor typos noted.
  - **[LOW] typo** — The period after 'Javascript' should be a comma to match the list structure.
    - `Has parsing libraries for Javascript. Python, PHP, and Ruby.`
    - Fix: Change the period to a comma: 'Javascript, Python, PHP, and Ruby.'
  - **[LOW] typo** — 'recongized' is a misspelling of 'recognized'.
    - `Whoever I pick will be recongized in a cool way!`
    - Fix: Correct to 'recognized'.
  - **[LOW] typo** — 'EUFA' is a misspelling of 'UEFA'.
    - `EUFA Champions League final!`
    - Fix: Correct to 'UEFA Champions League final!'

### #190 — Weekly Thing #190 / WWDC, Passport, Roll

- Era: Buttondown
- Overall: Issue #190 is in good shape overall; only a minor typo and a small caption/location inconsistency were noted.
  - **[LOW] typo** — "fo" should be "of".
    - `A lot fo things in this that will make you think.`
    - Fix: Change "fo" to "of".
  - **[LOW] other** — The caption says "Cannon Lake" but the location is given as "Wells Lake, MN" — one is likely incorrect.
    - `Pretty sunset colors on Cannon Lake tonight.

Jun 4, 2021 at 9:03 PM  
Wells Lake, MN`
    - Fix: Reconcile the lake name in the caption with the location line.

### #191 — Weekly Thing #191 / Decentralizing, Coffee, Future

- Era: Buttondown
- Overall: The issue is in good shape overall; only a few minor typos noted.
  - **[LOW] typo** — Missing verb — should read 'I see a great use' or 'and a great use'.
    - `This is a great step and I a great use for Filecoin`
    - Fix: Change 'and I a great use' to 'and a great use' or 'and I see a great use'.
  - **[LOW] typo** — 'as short at two years' should be 'as short as two years'.
    - `the return on investment of building your own infrastructure was as short at two years`
    - Fix: Change 'at two years' to 'as two years'.
  - **[LOW] typo** — 'role out' should be 'roll out'.
    - `trying to role out a brand new way of tracking`
    - Fix: Replace 'role out' with 'roll out'.

### #192 — Weekly Thing #192 / Endemic, Solidify, Zsync

- Era: Buttondown
- Overall: Issue is in good shape overall; only a handful of minor typos noted. The static audit's odd '**' count appears to be a false positive — bold markers balance correctly.
  - **[LOW] typo** — 'fo' is an obvious typo for 'of'.
    - `I've read four fo the five scenarios`
    - Fix: Change 'fo' to 'of'.
  - **[LOW] typo** — 'have' should be 'half' in this context.
    - `Send the other have a message that Team B will win`
    - Fix: Change 'have' to 'half'.
  - **[LOW] typo** — 'overs' appears to be a typo for 'offers'.
    - `Zcash is one of the few that overs private transfers`
    - Fix: Change 'overs' to 'offers'.
  - **[LOW] typo** — 'walled' should be 'wallet'.
    - `setup a walled on [Kukai]`
    - Fix: Change 'walled' to 'wallet'.

### #193 — Weekly Thing #193 / POAPs, DAOs, NFTs

- Era: Buttondown
- Overall: Issue is in good shape overall; only a single minor typo noted.
  - **[LOW] typo** — 'doin't' is a clear typo for 'don't'.
    - `many DNS providers doin't support the specific requirements`
    - Fix: Change 'doin't' to 'don't'.

### #194 — Weekly Thing #194 / Writing, Playdate, OpenMoji

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor grammar issues noted.
  - **[LOW] typo** — "it's" should be "its" (possessive, not contraction).
    - `allowed the country to strengthen it’s independence`
    - Fix: Change "it's" to "its".
  - **[LOW] typo** — Stray word "my" breaks the sentence grammatically.
    - `but either way I found my it invigorating`
    - Fix: Remove "my" so it reads "I found it invigorating".

### #195 — Weekly Thing #195 / Privacy, Loot, Minus

- Era: Buttondown
- Overall: Issue is in good shape overall; only a few minor typos were found.
  - **[LOW] typo** — "notable" should be "notably" — a clear grammatical typo.
    - `I don't agree with all of Cagan's viewpoints on agile delivery, notable his negative view on SaFE`
    - Fix: Change "notable" to "notably".
  - **[LOW] typo** — "Grand Maria's" is an autocorrect typo for "Grand Marais" (the town referenced throughout the issue).
    - `We walked out to the lighthouse on the pier in Grand Maria's today.`
    - Fix: Change "Grand Maria's" to "Grand Marais".
  - **[LOW] typo** — "fraught" should be "drought" — referenced later as "extreme draught conditions"; clear word-substitution typo.
    - `see how the fraught has impacted it`
    - Fix: Change "fraught" to "drought".

### #196 — Weekly Thing #196 / iPhone 13, iOS 15, watchOS 8

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor duplicated word and a small grammatical slip in the intro.
  - **[LOW] typo** — Duplicated word 'to to' is an obvious typo.
    - `Good idea to to switch to Duck Duck Go`
    - Fix: Remove the duplicated 'to'.
  - **[LOW] narrative-break** — The phrasing 'the [I first shared the setup]' reads as a grammatical slip — likely should be 'since I first shared the setup' without the leading 'the'.
    - `the [I first shared the setup](https://www.thingelstad.com/2017/06/23/assembling-the-weekly.html)`
    - Fix: Remove the stray leading 'the' before the link so it reads 'since I first shared the setup'.

### #197 — Weekly Thing #197 / Cloudflare, Bunches, Float

- Era: Buttondown
- Overall: Issue is clean overall with only one minor verb-form typo; no migration artifacts, broken links, or structural problems.
  - **[LOW] typo** — "pursuits" should be "pursues" — clear grammatical error (noun vs verb).
    - `the flavor that that particular group or individual pursuits`
    - Fix: Change "pursuits" to "pursues".

### #198 — Weekly Thing #198 / Facebook, News, Kyiv

- Era: Buttondown
- Overall: Issue is clean and well-structured; only a minor capitalization slip noted.
  - **[LOW] typo** — Sentence starts with lowercase 'it' after a period, a clear capitalization error.
    - `I love the new 77mm focal length on the 3x. it is a much bigger difference than some may think.`
    - Fix: Capitalize to 'It is a much bigger difference...'

### #201 — Weekly Thing #201 / Collecting, Smart, Stupid

- Era: Buttondown
- Overall: Issue is in good shape overall; the main visible problem is the nested-bracket malformed link in the Briefly section flagged by the static audit.
  - **[LOW] malformed-link** — The nested double brackets `[[WM:TECHBLOG]]` inside the link text create malformed markdown that will render with stray brackets in the link label.
    - `[Iterating on how we do NFS at Wikimedia Cloud Services – [[WM:TECHBLOG]]](https://techblog.wikimedia.org/2021/10/19/iterating-on-how-we-do-nfs-at-wikimedia-cloud-services/)`
    - Fix: Remove the inner brackets so the link text reads `Iterating on how we do NFS at Wikimedia Cloud Services – WM:TECHBLOG`.
  - **[LOW] typo** — `seem` should be `seen`.
    - `I've seem it happen many times.`
    - Fix: Change `seem` to `seen`.
  - **[LOW] typo** — `iff` appears to be a typo for `if` (though `iff` means 'if and only if' in math, context here is casual prose).
    - `assume iff everyone else thinks you are wrong`
    - Fix: Change `iff` to `if`.

### #202 — Weekly Thing #202 / Goalies, Curves, Spiders

- Era: Buttondown
- Overall: Issue is in good shape overall; the most visible problem is the duplicated 'Let'sLet's' at the start of the MacBook Pro review blockquote, plus a couple of minor typos.
  - **[MEDIUM] typo** — The quoted review text begins with a duplicated 'Let's Let's' — clearly a copy-paste error in the blockquote.
    - `> Let’sLet’s start simply:`
    - Fix: Remove the duplicated 'Let's' so it reads 'Let's start simply:'.
  - **[LOW] typo** — Obvious typo: 'Call my cynical' should be 'Call me cynical'.
    - `Call my cynical,`
    - Fix: Change 'my' to 'me'.
  - **[LOW] typo** — Capitalization typo: 'GIants' should be 'Giants'.
    - `[Sleeping GIants](https://en.wikipedia.org/wiki/Sleeping_Giants)`
    - Fix: Fix capitalization to 'Sleeping Giants'.
  - **[LOW] other** — This appears to be a garbled tagline from the linked site, but it's the link title as displayed — may confuse readers but reflects source.
    - `All of yours get back to stored in one place`
    - Fix: Verify the link title and correct to the site's actual tagline if desired.

### #203 — Weekly Thing #203 / Discord, Family, Names

- Era: Buttondown
- Overall: The issue is in good shape overall with coherent structure and working links; only a handful of minor typos warrant correction.
  - **[MEDIUM] typo** — 'Your' should be 'You're' — a clear grammatical error (contraction of 'you are').
    - `**Your in a metal box!**`
    - Fix: Change 'Your' to 'You're'.
  - **[LOW] typo** — 'pursuits' (noun) is used where the verb 'pursues' is intended.
    - `It will be very curious to see how Discord pursuits this web3 area`
    - Fix: Change 'pursuits' to 'pursues'.
  - **[LOW] typo** — Stray capitalization of 'It' mid-sentence appears to be a typo.
    - `turn It into telemetry`
    - Fix: Lowercase to 'it'.
  - **[LOW] typo** — 'expereinces' is a misspelling of 'experiences'.
    - `creating a number of different expereinces`
    - Fix: Correct spelling to 'experiences'.

### #204 — Weekly Thing #204 / Containers, Constitution, Cancel

- Era: Buttondown
- Overall: The issue is structurally clean and renders properly; the only issues are a cluster of minor typos and misspellings (notably in the ConstitutionDAO journal entry heading).
  - **[LOW] typo** — 'your' should be 'you're' (you are).
    - `part of helping others handle your digital footprint after your gone.`
    - Fix: Change 'after your gone' to 'after you're gone'.
  - **[LOW] typo** — 'it's' should be the possessive 'its'.
    - `Creating game environments using the bike and it’s various sensors`
    - Fix: Change 'it’s various sensors' to 'its various sensors'.
  - **[LOW] typo** — 'registerd' is a misspelling of 'registered'.
    - `because I had ENS names registerd.`
    - Fix: Change 'registerd' to 'registered'.
  - **[LOW] typo** — 'ratifcation' is a misspelling of 'ratification'.
    - `Part of that event was the ratifcation of a constitution`
    - Fix: Change 'ratifcation' to 'ratification'.
  - **[LOW] typo** — 'artcile' is a misspelling of 'article'.
    - `Each artcile was 92.5 to 93.8% approved.`
    - Fix: Change 'artcile' to 'article'.
  - **[LOW] typo** — 'demistify' should be 'demystify' (this appears within a quote, but is an obvious misspelling worth noting).
    - `I will try to demistify concepts`
    - Fix: Consider [sic] or a correction; 'demystify' is the correct spelling.
  - **[LOW] typo** — 'ConstituionDAO' is misspelled in the H3 heading (should be 'ConstitutionDAO').
    - `### ConstituionDAO`
    - Fix: Change 'ConstituionDAO' to 'ConstitutionDAO'.
  - **[LOW] typo** — 'PIzza' has an inadvertent capital I (should be 'Pizza').
    - `Punch PIzza, Eden Prairie, Minnesota`
    - Fix: Change 'PIzza' to 'Pizza'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `when your recognized in that way`
    - Fix: Change 'when your recognized' to 'when you're recognized'.

### #205 — Weekly Thing #205 / Hurl, Faster, Web3

- Era: Buttondown
- Overall: Issue #205 is in good shape overall with only a few minor typos worth correcting.
  - **[LOW] typo** — 'damn' should be 'dam' (the water-retaining structure).
    - `Fisherman looking for fish on a cold fall day in Slevin Park, at the damn by the`
    - Fix: Change 'damn' to 'dam'.
  - **[LOW] typo** — 'a think' should be 'a thing'.
    - `remember that when Web 2.0 was a think and O'Reilly`
    - Fix: Replace 'a think' with 'a thing'.
  - **[LOW] typo** — 'applis' is a clear misspelling of 'applies'.
    - `David Allen applis in this video`
    - Fix: Change 'applis' to 'applies'.

### #206 — Weekly Thing #206 / Omicron, Overengineering, Endaoment

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor grammatical slips noted.
  - **[LOW] typo** — Grammatical error: 'I often doesn't' should likely be 'often doesn't' (stray 'I').
    - `Good article and a topic that I often doesn't get enough attention.`
    - Fix: Remove 'I' so it reads 'a topic that often doesn't get enough attention.'
  - **[LOW] typo** — Grammatical slip: should be 'have also been attempting' or 'have also attempted'.
    - `Retailers have also been attempted to "flatten the curve" for years`
    - Fix: Change 'been attempted' to 'attempting' or 'attempted'.

### #207 — Weekly Thing #207 / Architecture, Contrarian, Storytelling

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and one stray-character artifact to clean up.
  - **[LOW] typo** — 'beuaracracy' is a clear misspelling of 'bureaucracy'.
    - `I think many would see the above as a sign of beuaracracy`
    - Fix: Change 'beuaracracy' to 'bureaucracy'.
  - **[LOW] typo** — 'your' should be 'you're' (you are) in this context.
    - `If your curious to know how the Domain Name System`
    - Fix: Replace 'your' with 'you're'.
  - **[LOW] typo** — 'Userful' is a typo for 'Useful'.
    - `Userful directory of quick links`
    - Fix: Change 'Userful' to 'Useful'.
  - **[LOW] typo** — 'reccomendations' is misspelled; should be 'recommendations'.
    - `Reddit Reads: Book reccomendations from reddit`
    - Fix: Correct spelling to 'recommendations' (note this appears in the link title as it is on the source site, so optional).
  - **[LOW] narrative-break** — A stray '&' appears where an ellipsis or other punctuation likely was intended, suggesting a migration/encoding artifact.
    - `So close& and the [POAP is a fun way to remember`
    - Fix: Replace '&' with the intended punctuation (likely '…').
  - **[LOW] typo** — Missing possessive apostrophe in 'last years'.
    - `After last years hiatus`
    - Fix: Change to "last year's hiatus".

### #208 — Weekly Thing #208 / GPS, Intel, Omicron

- Era: Buttondown
- Overall: Issue is in good shape overall; only a few minor typos worth noting.
  - **[LOW] typo** — "how we went to move forward" appears to be a typo for "how we want to move forward".
    - `we must continuously re-evaluate and assess how we went to move forward.`
    - Fix: Change "went" to "want".
  - **[LOW] typo** — "On" should be "One".
    - `On of the benefits I hope to get from publishing the Weekly Thing`
    - Fix: Change "On" to "One".
  - **[LOW] typo** — "may have move" should be "may have moved".
    - `and how manipulation may have move the market.`
    - Fix: Change "move" to "moved".
  - **[LOW] typo** — Missing article — should be "in a statement" (though this is inside a blockquote, so may reflect source).
    - `Opera EVP Jorgen Arnensen said in statement.`
    - Fix: Leave as-is if quoted verbatim; otherwise add "a".

### #210 — Weekly Thing #210 / Wyoming, WebAssembly, Wordle

- Era: Buttondown
- Overall: The issue is in good shape structurally with no migration artifacts or broken links; only minor typos were found.
  - **[LOW] typo** — Missing apostrophe in possessive 'Wyoming's'.
    - `What I think is so good about Wyomings approach`
    - Fix: Change 'Wyomings' to 'Wyoming's'.
  - **[LOW] typo** — 'he approach' should be 'the approach'.
    - `Overall I think he approach framed up here`
    - Fix: Change 'he approach' to 'the approach'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `so you play it once a day and then your done`
    - Fix: Change 'your done' to 'you're done'.
  - **[LOW] typo** — Two typos: 'suprrising' and 'Shoppify'.
    - `The only part suprrising is that Shoppify`
    - Fix: Correct to 'surprising' and 'Shopify'.
  - **[LOW] typo** — 'lose site' should be 'lose sight' and 'your building' should be 'you're building'.
    - `you sometimes lose site of what the thing is your building`
    - Fix: Change to 'lose sight of what the thing is you're building'.
  - **[LOW] typo** — Likely should be 'featured' rather than 'features' in this bullet list context.
    - `Governor of Wyoming heavily features`
    - Fix: Change 'features' to 'featured'.

### #211 — Weekly Thing #211 / Polar Bears, Delegating, Capes

- Era: Buttondown
- Overall: Issue is clean and well-structured aside from one confirmed broken image in the Journal section.
  - **[MEDIUM] image-problem** — Static audit confirmed this image returns HTTP 404, leaving a broken image in the Neeva NFT journal entry.
    - `![](https://www.thingelstad.com/uploads/2022/7a51035a83.jpg)`
    - Fix: Restore the image at that URL or replace the link with a working archive of the NFT image.

### #212 — Weekly Thing #212 / Words, Mermaid, Beats

- Era: Buttondown
- Overall: The issue is in good shape overall with only a few minor typos; formatting, links, and structure are all clean.
  - **[LOW] typo** — 'find' should be 'fine' — clear typo in context.
    - `Inside a project or service team I think the shorthand of technical debt is find.`
    - Fix: Change 'is find' to 'is fine'.
  - **[LOW] typo** — 'still makers' appears to be a typo for 'still matters' given the surrounding sentence about manager relationships.
    - `Guess what still makers?`
    - Fix: Change 'still makers' to 'still matters'.
  - **[LOW] typo** — Should be 'latter' (opposite of 'former'), not 'later'.
    - `you must believe the later`
    - Fix: Change 'the later' to 'the latter'.

### #213 — Weekly Thing #213 / Ukraine

- Era: Buttondown
- Overall: Issue is in good shape overall — a heartfelt Ukraine essay with many images and Journal entries; only minor typos noted.
  - **[LOW] narrative-break** — The editor-mode HTML comment is immediately followed by the opening italic paragraph with no blank line; while the comment is stripped at render, having no line break between it and the italic can cause the leading underscore to not initiate italics in some markdown renderers.
    - `<!-- buttondown-editor-mode: plaintext -->_This is a special Weekly Thing on Ukraine, there are no links this week… and there are a lot of photos!_`
    - Fix: Insert a blank line between the <!-- buttondown-editor-mode: plaintext --> comment and the opening paragraph to ensure reliable rendering.
  - **[LOW] typo** — 'quite minute' should be 'quiet minute' — a clear typo repeated in both the link slug and the body text.
    - `[Monday @ 8:00 PM](https://www.thingelstad.com/2022/02/21/a-quite-minute.html)

A quite minute on the dogsled trails`
    - Fix: Correct 'quite' to 'quiet' in the body text (the URL slug cannot be changed but the prose can).
  - **[LOW] typo** — 'todays' is missing the possessive apostrophe; should be 'today's'.
    - `Frozen head shots at the end of todays dogsledding adventure!`
    - Fix: Change 'todays' to 'today's'.

### #214 — Weekly Thing #214 / Support Ukraine

- Era: Buttondown
- Overall: Issue is in good shape overall; one Journal sentence has a noticeable grammar break that readers will stumble on.
  - **[MEDIUM] typo** — The sentence is ungrammatical — 'they are unable the available talent pool isn't growing' appears to have words missing or a merged clause.
    - `Companies need to solve this problem or it will limit their growth as they are unable the available talent pool isn't growing fast enough.`
    - Fix: Rewrite the sentence for clarity, e.g., 'Companies need to solve this problem or it will limit their growth, as the available talent pool isn't growing fast enough.'
  - **[LOW] typo** — The article 'the' before 'Russia's War' is grammatically incorrect (double determiner).
    - `But big events like the Russia's War on Ukraine throw that out the window.`
    - Fix: Remove 'the' so it reads 'But big events like Russia's War on Ukraine throw that out the window.'

### #215 — Weekly Thing #215 / Queues, Tor, Venting

- Era: Buttondown
- Overall: The issue is in good shape overall; only a couple of minor typos were noted.
  - **[LOW] typo** — 'a broad an challenging' should be 'a broad and challenging'.
    - `Srinivasan is a broad an challenging thinker.`
    - Fix: Change 'an' to 'and'.
  - **[LOW] typo** — Stray apostrophe after 'Jarvis' where a simple possessive/subject form is intended.
    - `Jarvis' clearly articulates the reason`
    - Fix: Remove the apostrophe: 'Jarvis clearly articulates'.

### #216 — Weekly Thing #216 / NFT, DST, PDP

- Era: Buttondown
- Overall: Issue is generally clean and readable; only notable issue is the 'Support Ukraine' section using H3 instead of H2, which may affect TOC structure.
  - **[MEDIUM] header-error** — The 'Support Ukraine' section uses an H3 heading but it is a top-level section (not a link title), so it should be H2 like other canonical sections to avoid appearing nested under the preceding Notable link list.
    - `### Support Ukraine`
    - Fix: Change `### Support Ukraine` to `## Support Ukraine`.

### #217 — Weekly Thing #217 / Ukraine, Coaching, Population

- Era: Buttondown
- Overall: Issue is in good shape overall with standard Buttondown-era structure; only a few minor typos noted.
  - **[LOW] typo** — "A good leadership to do" reads as a dropped word (likely intended "A good leadership to-do" or "A good leadership thing to do").
    - `A good leadership to do: Read the facilitating factors`
    - Fix: Change to "A good leadership to-do:" or "A good thing for leaders to do:".
  - **[LOW] typo** — "continual" appears to be a typo for "continually" (adverb needed to modify "tip").
    - `the rest of the world needs to do everything it possibly can to help tip the odds continual in its favor`
    - Fix: Replace "continual" with "continually".
  - **[LOW] typo** — Inconsistent with the earlier correct term "Multi Axis Trainer" used in the Space Camp entry — "Multi Access" is a typo.
    - `[Mazie did the Multi Access Trainer]`
    - Fix: Change "Multi Access Trainer" to "Multi Axis Trainer".

### #218 — Weekly Thing #218 / An unscheduled break

- Era: Buttondown
- Overall: The issue is clean and reads well; only a minor structural inconsistency within the Journal section was noted.
  - **[LOW] header-error** — This Journal entry lacks an H3 title heading, unlike sibling entries (e.g., 'Support Ukraine', 'Market Value up 12.4%'), making the structure inconsistent within the Journal section.
    - `[Thursday @ 4:48 PM](https://www.thingelstad.com/2022/03/31/i-could-pass.html)

I could pass on any additional **nasopharyngeal** COVID tests.`
    - Fix: Either add an H3 title for this entry or accept as a short untitled journal note — but note the inconsistency with other entries that do have H3 titles.

### #220 — Weekly Thing #220 / Ukraine DAO, Nouns, Icebergs

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor typos noted.
  - **[LOW] typo** — Missing 'to' — should read 'continue to support'.
    - `We must continue support the people of Ukraine.`
    - Fix: Change to 'We must continue to support the people of Ukraine.'
  - **[LOW] typo** — The acronym is POAP (Proof of Attendance Protocol), not PAOP — a clear typo given the link text and article context.
    - `[PAOP](https://poap.xyz)s in Vogue.`
    - Fix: Change 'PAOP' to 'POAP'.

### #221 — Weekly Thing #221 / Rebooting, Incidents, Risk

- Era: Buttondown
- Overall: Issue is generally in good shape; main concern is an orphaned Briefly entry with no lead-in text and a few minor typos.
  - **[MEDIUM] narrative-break** — This Briefly item has no commentary/intro text before the arrow, unlike every other item in the section — likely a missing sentence.
    - ` → **[List of school shootings in the United States - Wikipedia](https://en.wikipedia.org/wiki/List_of_school_shootings_in_the_United_States)**`
    - Fix: Add the intended lead-in sentence before the arrow, or remove the orphaned entry.
  - **[LOW] typo** — Missing period (or sentence break) between 'garden' and 'She'.
    - `Mazie is planting the garden She loves to garden`
    - Fix: Insert a period after 'garden': 'Mazie is planting the garden. She loves to garden...'
  - **[LOW] typo** — Missing verb 'be' — should read 'This may be the most Minnesotan picture of me.'
    - `2. This may the most Minnesotan picture of me.`
    - Fix: Change to 'This may be the most Minnesotan picture of me.'
  - **[LOW] typo** — Missing article — should be 'in an unnoticed way' (quoted from source but clearly a typo worth noting).
    - `3. Serve in unnoticed way`
    - Fix: If preserving the quote, leave as-is; otherwise correct to 'Serve in an unnoticed way'.
  - **[LOW] typo** — 'run my' appears to be a typo for 'from my' or 'run by my' — doesn't parse grammatically.
    - `run my [Minnesota Technology Association](https://mntech.org)`
    - Fix: Change 'run my' to 'from my' or similar.

### #222 — Weekly Thing #222 / Smalltalk, Friendships, Automata

- Era: Buttondown
- Overall: Issue is in good shape overall; the main concern is the dangling '[proposals]' bracket that lost its URL, plus two minor typos.
  - **[MEDIUM] malformed-link** — The bracketed text '[proposals]' appears to have lost its URL, rendering as literal brackets instead of a link.
    - `There are already 13 [proposals] the DAO is considering, mostly early formation stuff.`
    - Fix: Either add the intended URL (likely the Lil Nouns DAO proposals page) or remove the brackets.
  - **[LOW] typo** — 'Franker' is a misspelling of 'Franken' (Al Franken, referenced in the Star Tribune link).
    - `This reminded me of [Al Franker's comment]`
    - Fix: Change 'Franker' to 'Franken'.
  - **[LOW] typo** — 'tresury' is a misspelling of 'treasury'.
    - `Noun DAO has a tresury of over 24,000 ETH`
    - Fix: Change 'tresury' to 'treasury'.

### #223 — Weekly Thing #223 / Digital Identity, Finding a Mode, WWDC

- Era: Buttondown
- Overall: The issue is in good shape structurally; the static audit's `[People]` flag is a false positive (editorial bracket in a quote), but there are several minor typos worth a light copy-edit.
  - **[LOW] malformed-link** — The static audit flagged `[People]` as bracketed text without a link, but this is a quoted passage where `[People]` is a standard editorial bracket indicating a word substitution in the original quote — not a broken link.
    - `> [People] judge the quality of the decisions based on the outcomes.`
    - Fix: No fix needed; this is valid editorial bracketing in a blockquote.
  - **[LOW] typo** — "are note linear" should be "are not linear".
    - `however they start, are note linear?`
    - Fix: Change "note" to "not".
  - **[LOW] typo** — "Swith" is a misspelling of "Switch".
    - `Nintendo Swith Pro Controller`
    - Fix: Change "Swith" to "Switch".
  - **[LOW] typo** — Missing word — should be "my first exposure to SunOS".
    - `my first exposure SunOS`
    - Fix: Insert "to" between "exposure" and "SunOS".
  - **[LOW] typo** — "adderess" is a misspelling of "address".
    - `Check out my Tezos adderess`
    - Fix: Change "adderess" to "address".
  - **[LOW] typo** — "chnage" is a misspelling of "change".
    - `may evolve and chnage as a result`
    - Fix: Change "chnage" to "change".

### #224 — Weekly Thing #224 / Self, Learning, Identity

- Era: Buttondown
- Overall: The issue is in good shape overall; only minor typos and a false-positive static audit finding were noted.
  - **[LOW] typo** — 'stoping' should be 'stopping' — clear typo.
    - `that was stoping the Weekly Thing`
    - Fix: Change 'stoping' to 'stopping'.
  - **[LOW] typo** — 'Wether' should be 'Whether' — clear typo at the start of a sentence.
    - `Wether it is the pandemic`
    - Fix: Change 'Wether' to 'Whether'.
  - **[LOW] typo** — Clear typos: 'sure with' should be 'wish' (or 'sure wish'), and the stray period before 'Twitter' breaks the sentence.
    - `I sure with this was a blog post instead of a. Twitter thread.`
    - Fix: Rewrite as 'I sure wish this was a blog post instead of a Twitter thread.'
  - **[LOW] typo** — 'use' should be 'we' — clear word substitution typo.
    - `how much use will have to do`
    - Fix: Change 'how much use will have to do' to 'how much we will have to do'.
  - **[LOW] other** — Static audit flagged this as bracketed text with no link, but it's intentional regex-like notation inside a quoted phrase ('web[0-9]+') and renders correctly as prose.
    - `[0-9]`
    - Fix: No fix needed; the static audit finding is a false positive.

### #225 — Weekly Thing #225 / Prestige, WebAssembly, PhizFans

- Era: Buttondown
- Overall: The issue is in good shape; the static audit's `[beep]` flag is a false positive (intentional censor in a quote), and the only real issue is a minor typo of 'Footloose'.
  - **[LOW] other** — The static audit flagged `[beep]` as bracketed text without a link, but it is intentional prose (a censored word in a Chris Rock quote), not a malformed link.
    - `"You can drive a car with your feet if you want to; it don't mean it's a good [beep] idea!"`
    - Fix: No fix needed; this is valid prose and the static audit finding should be dismissed.
  - **[LOW] typo** — The musical is spelled 'Footloose' with two o's.
    - `for **Footlose**!`
    - Fix: Change 'Footlose' to 'Footloose'.

### #226 — Weekly Thing #226 / Patagonia, Merge, Walrus

- Era: Buttondown
- Overall: The issue is in good shape overall; the static audit's flag is a false positive (editorial brackets in a quotation), and only a couple of minor typos were found.
  - **[LOW] malformed-link** — The static audit flagged this, but it appears inside a blockquote where the brackets are an editorial insertion (substituting for a pronoun like 'it') rather than a broken link, which is a valid prose convention similar to [sic].
    - `As of today [Let's Encrypt] has issued over a billion certificates to over 280 million websites.`
    - Fix: No fix needed; this is a conventional editorial bracket insertion in a quotation, not a malformed link.
  - **[LOW] typo** — 'with' should be 'win' — clear typo in context of describing tournament results.
    - `Final results of the #LeadTheWay bracket gave the overall with to **Rubiks Kubb**!`
    - Fix: Change 'overall with' to 'overall win'.
  - **[LOW] typo** — 'Your' should be 'You're' (you are doing it wrong).
    - `inevitably the purist will refute all your arguments to the contrary with "Your doing it wrong"`
    - Fix: Change 'Your doing it wrong' to "You're doing it wrong".

### #227 — Weekly Thing #227 / Attention, Minnedemo, Learning

- Era: Buttondown
- Overall: Issue is in good shape overall; just a handful of minor typos and two Journal H3 headings that are inconsistent with the era's H3-for-link-titles convention.
  - **[LOW] typo** — Missing apostrophe in 'let's'.
    - `Now lets get to WIL!`
    - Fix: Change 'lets' to 'let's'.
  - **[LOW] typo** — Misspelling of 'Riverview Theater' (the image caption earlier correctly uses 'Riverview').
    - `Reverview Theater`
    - Fix: Change 'Reverview' to 'Riverview'.
  - **[LOW] typo** — Capitalization typo — 'HIs' should be 'His'.
    - `HIs review of the Apple Watch Ultra`
    - Fix: Change 'HIs' to 'His'.
  - **[LOW] typo** — Wrong homophone — 'there' should be 'their'.
    - `[Oleg Ryaboy](https://www.linkedin.com/in/olegryaboy/) there new CTO`
    - Fix: Change 'there' to 'their'.
  - **[LOW] typo** — Company name is 'Compute North' (as used in the next sentence and the linked headline), not 'Computer North'.
    - `Computer North is a Minneapolis company.`
    - Fix: Change 'Computer North' to 'Compute North'.
  - **[LOW] header-error** — H3 heading appears inside a Journal entry that is otherwise introduced by a bracketed timestamp link, inconsistent with sibling Journal entries and potentially confusing the TOC structure (H3 is reserved for link titles in this era).
    - `### Minnedemo 37`
    - Fix: Consider bolding 'Minnedemo 37' instead of using H3, or reconcile heading style across Journal entries.
  - **[LOW] header-error** — H3 used inside a Journal entry where the convention is H3 for link titles; creates a TOC entry inconsistent with other Journal items.
    - `### Roadmap by Dariush`
    - Fix: Convert to bold text or align with Journal entry styling.

### #228 — Weekly Thing #228 / Technical, Adversarial, Overcomplicating

- Era: Buttondown
- Overall: The issue is in good shape overall with normal structure and working links; only a handful of minor typos were found.
  - **[LOW] typo** — 'Hurrican' is missing the final 'e' in Hurricane.
    - `we got Hurrican Ian this week`
    - Fix: Change 'Hurrican' to 'Hurricane'.
  - **[LOW] typo** — 'wether' should be 'whether'.
    - `Yet there is active debate on wether technology leaders`
    - Fix: Change 'wether' to 'whether'.
  - **[LOW] typo** — 'vide' is a typo for 'video'.
    - `His [I AM BLKBOK](https://www.youtube.com/watch?v=VVHaAZn9NGs) vide is a good intro.`
    - Fix: Change 'vide' to 'video'.
  - **[LOW] typo** — 'by' should be 'buy'.
    - `You only by 1% voting rights`
    - Fix: Change 'by' to 'buy'.
  - **[LOW] typo** — Stray 'g.' at end of sentence appears to be a leftover artifact.
    - `facing off on the pitch this morning g.`
    - Fix: Remove the trailing ' g.'

### #229 — Weekly Thing #229 / Time, Zolatron, Maigret

- Era: Buttondown
- Overall: The issue is in good shape overall; the static audit's `[+]` finding is a false positive (code-block CLI output), and only a couple of minor typos are present.
  - **[LOW] malformed-link** — The static audit flagged `[+]` as bracketed text with no link, but these occurrences are inside a fenced code block showing maigret tool output — they are intentional CLI formatting, not malformed markdown.
    - `[+] Disqus: https://disqus.com/thingles`
    - Fix: No fix needed; the `[+]` markers are legitimate command-line output within code blocks.
  - **[LOW] typo** — The `&` appears to be a stray character where an ellipsis or period was intended (likely a migration artifact from `…` or similar).
    - `Wish we could have kept going for a few more hours& 🥰`
    - Fix: Replace `hours&` with `hours…` or `hours.`
  - **[LOW] typo** — Should be 'incredible' not 'incredibly' — adjective needed to modify 'mission'.
    - `how this incredibly mission should be represented`
    - Fix: Change 'incredibly mission' to 'incredible mission'.

### #230 — Weekly Thing #230 / Calendar, Fractal, Reminiscing

- Era: Buttondown
- Overall: Issue #230 is in good shape overall; only a minor duplicated sentence and a small typo were noted.
  - **[LOW] narrative-break** — The sentence '28 seems like it would be just right.' is repeated verbatim two paragraphs apart, which appears to be an unintentional duplication from editing.
    - `28 seems like it would be just right. I would flex those four additional hours into a lot of interesting things, and not forego sleep. 

28 seems like it would be just right.`
    - Fix: Remove the duplicate standalone line '28 seems like it would be just right.'
  - **[LOW] typo** — 'On my opinion' should be 'In my opinion' — clear typo.
    - `On my opinion our calendars have a tremendous amount of value to still unlock.`
    - Fix: Change 'On my opinion' to 'In my opinion'.

### #231 — Weekly Thing #231 / UNIX Pipe, Slow Roads, Personal Brand

- Era: Buttondown
- Overall: Issue is in good shape overall with just a few minor typos worth correcting.
  - **[LOW] typo** — 'Spring points' should be 'Story points' — clear typo given the surrounding context about story points.
    - `Spring points should be an estimate of complexity.`
    - Fix: Change 'Spring points' to 'Story points'.
  - **[LOW] typo** — 'PAOP' is a transposition of 'POAP' used consistently elsewhere in the same paragraph.
    - `I want one of these IYK PAOP Cards so bad now!`
    - Fix: Change 'PAOP' to 'POAP'.
  - **[LOW] typo** — 'wea re' is a clear typo for 'we are'.
    - `This interview frames a view that wea re shifting to a very different economic environment`
    - Fix: Change 'wea re' to 'we are'.
  - **[LOW] narrative-break** — The clause appears to be missing a word (likely 'that' between 'avoid' and 'he states'), making the sentence read awkwardly.
    - `There is some potential to avoid he states, if we can figure out a way to drive real productivity up faster.`
    - Fix: Insert 'that' or restructure: 'There is some potential to avoid that, he states, if...'.

### #232 — Weekly Thing #232 / Fiber, Decker, Privacy

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor orphan H3 header (already flagged by static audit) and one obvious homophone typo.
  - **[LOW] header-error** — H3 subheading appears before the first H2 section, making it an orphan subheading (confirming the static audit finding).
    - `### Weekly Thing on Reddit?`
    - Fix: Either promote to H2 or place under an appropriate H2 section like ## Notable.
  - **[LOW] typo** — 'ready to role' should be 'ready to roll' — a clear homophone typo.
    - `basic Reddit features are ready to role`
    - Fix: Change 'role' to 'roll'.

### #233 — Weekly Thing #233 / Versepad, "Just", Mastadon

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos in prose and a quoted passage, no structural or migration problems.
  - **[LOW] typo** — Mismatched quotation marks — opens with a curly left-double quote and closes with a straight double quote.
    - `“Success is the enemy of curiosity." — Jony Ive`
    - Fix: Change the closing straight quote to a curly right-double quote for consistency.
  - **[LOW] typo** — Obvious typo: 'tlmeline' should be 'timeline'.
    - `This article has a good tlmeline.`
    - Fix: Change 'tlmeline' to 'timeline'.
  - **[LOW] typo** — Sentence is grammatically broken — likely 'validates it' or missing words, reads as a narrative break.
    - `This site collects data and validates is a database of tech related layoffs.`
    - Fix: Rewrite, e.g., 'This site collects and validates data in a database of tech-related layoffs.'
  - **[LOW] typo** — Typo in quoted text: 'delete is' should likely be 'delete it' (though this is from source, the surrounding context suggests a transcription error).
    - `will delete is as soon as it is received`
    - Fix: Verify the source; if it's a transcription error, change 'is' to 'it'.

### #234 — Weekly Thing #234 / Distributed, Principles, Drivers

- Era: Buttondown
- Overall: Issue is in good shape overall with only a few minor typos; structure, links, and images all render correctly.
  - **[LOW] typo** — Sentence after question mark begins with lowercase 'it' where a capital 'I' is expected.
    - `Also part of the premise is how can you even lose that much money? it seems you would have to try really hard.`
    - Fix: Capitalize to 'It seems you would have to try really hard.'
  - **[LOW] typo** — Article error: should be 'an animated' before a vowel sound.
    - `a animated zoom`
    - Fix: Change 'a animated' to 'an animated'.
  - **[LOW] typo** — Word should be 'possibly' (adverb), not 'possible'.
    - `but possible has some additional capabilities`
    - Fix: Change 'possible' to 'possibly'.

### #235 — Weekly Thing #235 / TikTok, Busy, Stories

- Era: Buttondown
- Overall: Issue is in good shape overall; only a couple of minor typos worth noting.
  - **[LOW] typo** — "nee" is a clear typo for "need".
    - `Payment is one of those foundational capabilities that we nee for the web`
    - Fix: Change "we nee for" to "we need for".
  - **[LOW] typo** — "of faster" should be "or faster".
    - `if you grow at a rate much slower of faster than I am`
    - Fix: Change "slower of faster" to "slower or faster".

### #236 — Weekly Thing #236 / ChatGPT, Reading, Legitimacy

- Era: Buttondown
- Overall: Issue is readable and well-structured overall; main concerns are a handful of minor typos and two H3 headings inside the Journal section that break the era's entry formatting.
  - **[LOW] typo** — "thing" should be "think" — clear typo in context of a sentence about thinking.
    - `Larson reflecting that you must thing about the humans in mix`
    - Fix: Change "must thing about" to "must think about".
  - **[LOW] typo** — "implmentation" is a misspelling of "implementation".
    - `the specific implmentation of Facebook or Twitter`
    - Fix: Correct to "implementation".
  - **[LOW] typo** — "aherence" is a misspelling of "adherence".
    - `because of a close aherence to that principle`
    - Fix: Correct to "adherence".
  - **[LOW] typo** — "Shoppify" misspells "Shopify" (the linked headline uses the correct spelling).
    - `Tons of new records set for 2022 holiday season at Shoppify.`
    - Fix: Change "Shoppify" to "Shopify".
  - **[MEDIUM] header-error** — This H3 appears inside the Journal section where entries are styled as bold links/paragraphs, not H3s; it breaks the Journal formatting pattern and will appear in the TOC alongside article titles in Notable.
    - `### Things 4 Good Fall Fundraiser Notes`
    - Fix: Demote to bold text or remove the heading so Journal entries render consistently.
  - **[MEDIUM] header-error** — Same issue — an H3 inside the Journal section that mixes with the Notable article-title H3s in the rendered outline.
    - `### Things 4 Good Fall Fundraiser Distributed`
    - Fix: Demote to bold text to match the rest of the Journal entries.

### #237 — Weekly Thing #237 / Ethereum, Zelensky, Fadell + Erratic Narratives

- Era: Buttondown
- Overall: The issue is largely clean and reads well; only minor typos and a couple of low-severity formatting quirks (the '[# -1]' marker and escaped asterisks divider) were noted.
  - **[LOW] dangling-reference** — The bracketed '[# -1]' appears to be a preview/issue-numbering marker that reads as dangling reference text to readers without context.
    - `**Sickness is Volatility; Volatility is not a Sickness [\# -1]**`
    - Fix: Either remove the '[# -1]' marker or clarify it (e.g., 'Preview Issue #-1') so it reads as intentional numbering.
  - **[LOW] typo** — 'ben' is a clear typo for 'been'.
    - `and have ben part of 258 loans so far`
    - Fix: Change 'ben' to 'been'.
  - **[LOW] typo** — 'indepdently' is a misspelling of 'independently'.
    - `one of very few indepdently owned cross-platform messaging services`
    - Fix: Correct 'indepdently' to 'independently'.
  - **[LOW] other** — Escaped asterisks render as literal '***' rather than an intended horizontal rule/separator, which is likely a migration/escaping artifact.
    - `\*\*\*`
    - Fix: Replace with an unescaped '---' horizontal rule or three unescaped asterisks if a divider was intended.

### #239 — Weekly Thing #239 / Helmets, Bear, Smile

- Era: Buttondown
- Overall: The issue is in good shape overall; only one minor punctuation/wording slip noted.
  - **[LOW] typo** — Likely missing punctuation/word — reads as if a comma or word is missing between 'me' and 'Twitter' (should probably be 'The problem is me, Twitter, not you.').
    - `The problem is me Twitter, not you.`
    - Fix: Add comma: 'The problem is me, Twitter, not you.'

### #240 — Weekly Thing #240 / Shapes, Tags, Ubiquity

- Era: Buttondown
- Overall: Issue is generally in good shape; main concern is a garbled sentence in the Featured section ('As I read this I the screaming remnants...') plus two minor typos.
  - **[MEDIUM] narrative-break** — Missing verb — reads as 'As I read this I the screaming remnants', likely should be 'I heard' or 'I could hear'.
    - `As I read this I the screaming remnants of the [Semantic Web](https://www.w3.org/standards/semanticweb/)`
    - Fix: Insert the missing verb, e.g., 'As I read this I heard the screaming remnants...'
  - **[LOW] typo** — Likely typo for 'Mystic Lake Event Center' (a real venue near Minneapolis).
    - `Mystica Lake Event Center`
    - Fix: Change 'Mystica Lake' to 'Mystic Lake'.
  - **[LOW] typo** — Clear typo of 'sense'.
    - `the sesne of accomplishment`
    - Fix: Change 'sesne' to 'sense'.

### #241 — Weekly Thing #241 / Wildebeest, Reputation, Zero

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and one small wording glitch in the Journal section.
  - **[LOW] typo** — 'Mastadon' is a misspelling of 'Mastodon', which is used correctly elsewhere in the issue.
    - `Searls takes a look at these and tests them with Mastadon.`
    - Fix: Change 'Mastadon' to 'Mastodon'.
  - **[LOW] typo** — Another misspelling of 'Mastodon'.
    - `This new open-source Mastadon server is another great example of that.`
    - Fix: Change 'Mastadon' to 'Mastodon'.
  - **[LOW] typo** — 'mount' should be 'amount' and 'powerfull' should be 'powerful'.
    - `Incredible mount of functionality in there, and a powerfull add to the Fediverse stack.`
    - Fix: Fix to 'Incredible amount of functionality in there, and a powerful add to the Fediverse stack.'
  - **[LOW] typo** — 'improtance' is a misspelling of 'importance'.
    - `gave a good overview of the improtance of downtown`
    - Fix: Change 'improtance' to 'importance'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `If your looking for a delightful and fun story`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] narrative-break** — Sentence appears to be missing a word — likely 'telling you [that] you don't have a problem.'
    - `**Listening to Win:** Let me make the problem go away, by telling you don't have a problem.`
    - Fix: Insert the missing word, e.g., 'by telling you that you don't have a problem.'

### #243 — Weekly Thing #243 / Montaigne, Ordinals, Salsa + Ukraine Fundraiser!

- Era: Buttondown
- Overall: Issue is in good shape overall with only minor typos; no migration artifacts, broken links, or structural problems detected.
  - **[LOW] typo** — The title 'Global CIO' is duplicated, clearly a copy-paste error.
    - `Global CIOGlobal CIO, Donaldson`
    - Fix: Remove the duplicated 'Global CIO' so it reads 'Global CIO, Donaldson'.
  - **[LOW] typo** — Stray 'the,' repeated — likely an editing artifact.
    - `Good movie about growing up and the, the relationship between parents and their kids`
    - Fix: Remove the extra 'the,' so it reads 'Good movie about growing up and the relationship between parents and their kids'.
  - **[LOW] typo** — Possessive apostrophe appears misplaced; likely should be plural 'Centers' (no apostrophe) at end of a title.
    - `Microsoft Technology Center's`
    - Fix: Change to 'Microsoft Technology Centers' (no apostrophe).

### #244 — Weekly Thing #244 / Fans, Sameness, Fediverse + Ukraine Fundraiser!

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor typos noted.
  - **[LOW] typo** — 'Eluded' should be 'alluded'; this is a clear word-confusion error.
    - `something I eluded to earlier`
    - Fix: Change 'eluded' to 'alluded'.
  - **[LOW] typo** — 'think' should be 'thing' — obvious typo.
    - `That banana is an organic think that we can approximate`
    - Fix: Change 'think' to 'thing'.

### #245 — Weekly Thing #245 / Curation, Outcomes, Disturbed

- Era: Buttondown
- Overall: The issue is in good shape overall; only a minor word-omission typo in the SimCity paragraph was found.
  - **[LOW] typo** — "Then the went downhill" appears to be missing a word — likely "Then they went downhill" or "Then it went downhill".
    - `Then the went downhill as EA shifted it more online`
    - Fix: Change "Then the went downhill" to "Then it went downhill".

### #246 — Weekly Thing #246 / Banks, Stablecoin, Trust

- Era: Buttondown
- Overall: The issue is in good shape overall; only two minor duplicated-word typos were spotted.
  - **[LOW] typo** — Duplicated 'it it' and missing conjunction/punctuation between clauses.
    - `I first ran into RAI several months ago it it made my head hurt a bit.`
    - Fix: Change to 'several months ago and it made my head hurt a bit.'
  - **[LOW] typo** — Duplicated word 'the the'.
    - `the the utterances of social media completely lose.`
    - Fix: Remove the duplicate 'the'.

### #247 — Weekly Thing #247 / New York, Fingerprints, Snitch

- Era: Buttondown
- Overall: The issue is in good shape overall; only minor typos and one ambiguous bracketed term in a pull-quote stand out.
  - **[LOW] malformed-link** — The bracketed '[Twitter]' in the pull-quote has no link and looks like a lost markdown link; however, in context it reads as an editorial insertion/clarification within the quote, so this is low severity.
    - `It became very clear to me that [Twitter] was an unrewarding use of my attention.`
    - Fix: Either attach a URL to [Twitter] or remove the brackets so it renders as plain text 'Twitter'.
  - **[LOW] typo** — 'interviw' is a clear misspelling of 'interview'.
    - `Next up is the interviw with`
    - Fix: Change 'interviw' to 'interview'.
  - **[LOW] typo** — In the itinerary list 'Fairy' should be 'Ferry' (other entries in the same list use 'Ferry').
    - `Fairy to Manhattan.`
    - Fix: Change 'Fairy to Manhattan.' to 'Ferry to Manhattan.'

### #248 — Weekly Thing #248 / Bicycle, Attention, Shapella

- Era: Buttondown
- Overall: The issue is in good shape overall; the static audit's flagged '[were]' is a false positive (valid editorial bracket in a quote), and only a couple of minor typos were found.
  - **[LOW] malformed-link** — The static audit flagged '[were]' as bracketed text without a link, but this is a standard editorial bracket insertion in a quotation to adjust tense/grammar, not a missing link.
    - `"six former interns or associates of Cooper & Kirk [were] serving as U.S. Supreme Court clerks."`
    - Fix: No fix needed; this is a valid editorial bracket in a quotation and should not be flagged.
  - **[LOW] typo** — 'poluting' is a misspelling of 'polluting'.
    - `without likes and retweets poluting it.`
    - Fix: Change 'poluting' to 'polluting'.
  - **[LOW] typo** — 'transfered' is a misspelling of 'transferred'.
    - `each item will be transfered to the respective winners`
    - Fix: Change 'transfered' to 'transferred'.

### #249 — Weekly Thing #249 / GPT, Privacy, Crypto

- Era: Buttondown
- Overall: Issue is in good shape overall; only a few minor typos noted.
  - **[LOW] typo** — 'from their' should be 'from there'.
    - `how quickly that "calculator" turns into a spreadsheet, and from their into something even more`
    - Fix: Change 'from their' to 'from there'.
  - **[LOW] typo** — 'It is isn't' is a duplicated verb typo; should be 'It isn't'.
    - `The interview highlights the incongruity of the CEO of Apple focusing on privacy and device addiction. It is isn't incongruous`
    - Fix: Replace 'It is isn't' with 'It isn't'.
  - **[LOW] typo** — Word order typo; should be 'I want them to explore with it'.
    - `I want to them to explore with it`
    - Fix: Remove the stray 'to' so it reads 'I want them to explore with it'.

### #250 — Weekly Thing #250 / LLM, Shanghai, Wing

- Era: Buttondown
- Overall: Issue #250 is generally in good shape with strong content; main concerns are a couple of minor typos and heading-level inconsistencies (Fortune as H3, an orphan H3 inside Journal).
  - **[MEDIUM] header-error** — An H3 appears mid-Journal entry under a plain paragraph link, inconsistent with the other Journal entries which use no H3s and would appear as an orphan heading in the TOC structure.
    - `### 2022 Minnesota Aspirations in Computing Award Ceremony`
    - Fix: Convert to bold text or remove the H3 level to match the other Journal entries' formatting.
  - **[MEDIUM] header-error** — The Fortune section uses H3 instead of the canonical H2 (## Fortune), breaking section-level consistency and TOC hierarchy.
    - `### Fortune`
    - Fix: Change `### Fortune` to `## Fortune`.
  - **[LOW] typo** — 'authenticate' (verb) is used where 'authentic' (adjective) is clearly intended.
    - `particularly authenticate and genuine leadership`
    - Fix: Change 'authenticate' to 'authentic'.
  - **[LOW] typo** — Missing 'be' — should read 'might be better at'.
    - `An AI Doctor might better at getting all the right information.`
    - Fix: Insert 'be' to read 'An AI Doctor might be better at getting all the right information.'

### #251 — Weekly Thing #251 / Moloch, Chess, Protocol

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor header-level quirk with the Fortune subsection nested under Signature.
  - **[LOW] header-error** — The Signature section uses H2 but the Fortune subsection within it uses H3 (### Fortune), whereas Fortune is typically its own canonical H2 section; minor structural inconsistency but readable.
    - `## Signature`
    - Fix: Consider promoting ### Fortune to ## Fortune to match canonical section naming.

### #252 — Weekly Thing #252 / Elevator, Evidence, Everything

- Era: Buttondown
- Overall: Issue is in generally good shape; main concerns are the Fortune heading being H3 instead of the canonical H2 and a couple of minor typos.
  - **[MEDIUM] header-error** — This H3 appears inside the Journal section where other entries use plain bold/date links, not H3s, and it's nested under the 'Friday @ 5:29 PM' date link rather than being the link title itself — inconsistent with Buttondown-era H3 link-title convention.
    - `### Ringing the Closing Bell on Nasdaq`
    - Fix: Either remove the H3 (use bold) or restructure so the H3 is the link title consistent with other sections.
  - **[LOW] header-error** — The canonical Fortune section should be an H2 (`## Fortune`) like other top-level sections; using H3 places it under the Signature H2, breaking the TOC.
    - `### Fortune`
    - Fix: Change `### Fortune` to `## Fortune`.
  - **[LOW] typo** — 'was well' should be 'as well'.
    - `I could have done it was well as Brander!`
    - Fix: Replace 'was well' with 'as well'.
  - **[LOW] typo** — 'Wether' should be 'Whether'.
    - `Wether Coinbase and Brian Armstrong`
    - Fix: Change 'Wether' to 'Whether'.

### #253 — Weekly Thing #253 / Domains, Anybox, Currl

- Era: Buttondown
- Overall: The issue is in good overall shape with intact structure and links; the main concerns are several small typos in the Journal bullet lists (likely due to the author's note that automation failed and some parts were hand-assembled).
  - **[MEDIUM] header-error** — Within the Journal section, H3 is used for link titles elsewhere in the newsletter; this H3 appears inside a Journal entry and creates inconsistent heading structure (similar H3s appear for 'Tammy's NYC Birthday Trip Day N').
    - `### MnTech Tech Connect 2023`
    - Fix: Consider demoting these Journal sub-headings to bold text or H4 for consistency — though this may be era-normal Journal style; low-priority.
  - **[LOW] typo** — 'wtih' is a clear typo for 'with'.
    - `The Art of Personalization wtih AI/ML`
    - Fix: Change 'wtih' to 'with'.
  - **[LOW] typo** — 'jnlccluding' and 'cheeseburfer' are obvious typos (should be 'including' and 'cheeseburger').
    - `Explored Chelsea Market, jnlccluding cheeseburfer and book store.`
    - Fix: Fix to 'including cheeseburger'.
  - **[LOW] typo** — 'Anniqu' appears to be a truncated name (likely 'Annique' or similar).
    - `Brunch with Greg and Anniqu at Frankies`
    - Fix: Verify and complete the name.
  - **[LOW] typo** — 'needed up' should be 'ended up'.
    - `accidentally needed up at Moma Store`
    - Fix: Change 'needed up' to 'ended up'.
  - **[LOW] typo** — 'clithes' is a typo for 'clothes'.
    - `Return to Hotel to change into dry clithes`
    - Fix: Change 'clithes' to 'clothes'.
  - **[LOW] typo** — 'inimate' is a typo for 'intimate'.
    - `powerful and inimate performances`
    - Fix: Change 'inimate' to 'intimate'.

### #254 — Weekly Thing #254 / Redis, Dooce, Batteries

- Era: Buttondown
- Overall: The issue is in good shape overall; the only notable concern is the `### Fortune` heading being H3 instead of the canonical H2.
  - **[LOW] header-error** — The Fortune section uses H3 but per era conventions canonical sections like Fortune should be H2 (## Fortune); other sections in this issue use H2 correctly.
    - `### Fortune`
    - Fix: Change `### Fortune` to `## Fortune` for consistency with other section headers.
  - **[LOW] header-error** — Signature is not in the list of canonical section names and uses H2 while similar metadata-like sections are typically not H2; however this is likely era-normal — low confidence.
    - `## Signature`
    - Fix: Verify whether Signature should be a canonical H2 section or demoted; leave as-is if intentional.

### #255 — Weekly Thing #255 / Lassie, Vore, Alby

- Era: Buttondown
- Overall: Issue is in good shape overall; minor typos and one section-heading level mismatch for the Fortune section.
  - **[LOW] typo** — 'your' should be 'you're' — clear grammatical typo.
    - `make you think you are confirming when your really hitting a button`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — 'Copiliot' is a misspelling of 'Copilot'.
    - `Google answer to GitHub Copiliot?`
    - Fix: Change 'Copiliot' to 'Copilot'.
  - **[MEDIUM] header-error** — Canonical section heading 'Fortune' should be H2 (## Fortune) like other sections; using H3 here breaks the TOC structure.
    - `### Fortune`
    - Fix: Change '### Fortune' to '## Fortune'.

### #256 — Weekly Thing #2^8 / Bitcoin, Kagi, Brink

- Era: Buttondown
- Overall: The issue is largely in good shape; only minor typos and one header-level inconsistency (Fortune as H3) stand out.
  - **[MEDIUM] narrative-break** — Missing verb — likely should read 'You could send Satoshis to an address' — the sentence is ungrammatical as written.
    - `You could Satoshis to an address and then reference the receipt in an SMTP header`
    - Fix: Insert the missing verb, e.g., 'You could send Satoshis to an address…'
  - **[LOW] header-error** — The Fortune section uses an H3 while other canonical section headings (Featured, Notable, Journal, Briefly, Signature) are H2; this breaks the section hierarchy/TOC.
    - `### Fortune`
    - Fix: Change `### Fortune` to `## Fortune` to match other top-level sections.
  - **[LOW] typo** — 'takers' appears to be a typo for 'stakers' given the context about Ethereum staking withdrawals.
    - `When Ethereum enabled withdrawals for takers there was some hand wringing`
    - Fix: Change 'takers' to 'stakers'.
  - **[LOW] typo** — 'walked be through' should be 'walked me through' — a clear typo.
    - `it walked be through getting my Nostr public and private keys setup`
    - Fix: Replace 'be' with 'me'.

### #257 — Weekly Thing #257 / Nostr, Time, Bcrypt

- Era: Buttondown
- Overall: The issue is in good shape overall; only a minor punctuation oddity in a pull quote was noted.
  - **[LOW] typo** — The block quote has an odd trailing comma followed by a period, likely a punctuation error from the source.
    - `> **They go beyond the light,**.`
    - Fix: Change to '**They go beyond the light.**' removing the stray comma.

### #258 — Weekly Thing #258 / Vision, Strike, Reputation

- Era: Buttondown
- Overall: The issue is largely clean and readable, but contains an unrendered template tag ({{ survey.buyvisionpro }}) and a duplicated blockquote in the Privacy section that should be addressed.
  - **[MEDIUM] migration-artifact** — This looks like an unrendered Buttondown template/merge tag that was never replaced with the actual poll content.
    - `{{ survey.buyvisionpro }}`
    - Fix: Replace with the intended poll embed or remove the placeholder if the poll is no longer available.
  - **[LOW] narrative-break** — This identical blockquote is duplicated verbatim in the Privacy section, which appears to be a copy-paste error rather than intentional emphasis.
    - `> The importance of privacy as a human right is underscored by its role as a prerequisite for the exercise and enjoyment of other rights. The interdependence of human rights makes privacy crucial to freedom of speech, the right to a fair trial, freedom of thought and conscience, and freedom of association.`
    - Fix: Replace the second instance with the intended different quote about Smart TVs, or remove the duplicate.
  - **[LOW] typo** — "your" should be "you're" (you are).
    - `If you always focus on getting better, you do, and your likely going to win.`
    - Fix: Change "your" to "you're".
  - **[LOW] typo** — "becuase" is a misspelling of "because".
    - `I had to pull this out becuase I had the same thought.`
    - Fix: Correct to "because".

### #259 — Weekly Thing #259 / Vision Pro, Tiny Awards, Mental Liquidity

- Era: Buttondown
- Overall: The issue is largely clean and well-formed; the only notable concerns are a suspicious placeholder image filename and a minor punctuation oddity inside a blockquote.
  - **[LOW] narrative-break** — The quoted text has an odd trailing comma inside the bold followed by a period, suggesting a small formatting/punctuation glitch in the quoted passage.
    - `**They go beyond the light,**.`
    - Fix: Review the quote — likely should be '**They go beyond the light.**' without the stray comma.
  - **[MEDIUM] image-problem** — The image URL uses the generic placeholder filename 'image.jpg' which is inconsistent with all other uploads (hashed filenames) and likely a broken/placeholder asset.
    - `![](https://www.thingelstad.com/uploads/2023/image.jpg)`
    - Fix: Replace with the correct hashed image URL from the original journal post.

### #260 — Weekly Thing #260 / Rash, Hashing, Arguably

- Era: Buttondown
- Overall: Issue #260 is in good shape overall; the only confirmed issue is the one broken journal image already caught by the static audit.
  - **[LOW] image-problem** — Static audit flagged this image URL as returning HTTP 404, so the image in the 'Bike ride to Lake Harriet' journal entry will not render.
    - `![](https://www.thingelstad.com/uploads/2023/media.jpg)`
    - Fix: Replace with the correct image filename on thingelstad.com or remove the broken image reference.
  - **[LOW] header-error** — H3 headings inside the Journal section are normally used for link titles in this era; these inline H3s for journal entries render as section-level headings that may appear in the TOC alongside the Notable link titles.
    - `### 28 min 39 sec`
    - Fix: Consider converting journal-entry subheadings to bold text or a different level to avoid polluting the page heading hierarchy (or confirm this is intentional).

### #261 — Weekly Thing 261 / Bloomfield Bridge, Critical Ignoring, Subscription Era

- Era: Buttondown
- Overall: Issue is in good shape overall; only a couple of minor typos and one possibly-placeholder image URL worth a quick check.
  - **[LOW] typo** — "your" should be "you're" — a clear grammatical error.
    - `If your looking for interesting beers without alcohol`
    - Fix: Change "your" to "you're".
  - **[MEDIUM] image-problem** — The image filename "media.png" looks like a generic placeholder rather than a specific uploaded image, and is positioned oddly between two unrelated journal entries; may be a broken/misreferenced image.
    - `![](https://www.thingelstad.com/uploads/2023/media.png)`
    - Fix: Verify the image URL resolves to the intended image, or remove/replace if it's a placeholder artifact.
  - **[LOW] typo** — "datacenter" should be plural "datacenters" given "many of the largest cloud providers".
    - `host datacenter. Hello AWS US-East-1!`
    - Fix: Change "datacenter" to "datacenters".

### #262 — Weekly Thing 262 / Simulator, System, Snoopy

- Era: Buttondown
- Overall: Issue is in generally good shape; a few minor typos and one malformed bold/link combination around 'Minnedemo 39' are the notable concerns.
  - **[LOW] typo** — Duplicate word: 'my my his brother' — 'my' appears accidentally before 'his'.
    - `with my his brother, my Uncle Tim`
    - Fix: Change to 'with his brother, my Uncle Tim' or 'with my step-dad Bruce and his brother, my Uncle Tim'.
  - **[LOW] typo** — 'git' is a typo for 'get'.
    - `the folks that really git into the spirit of Kubb`
    - Fix: Change 'git' to 'get'.
  - **[MEDIUM] malformed-link** — Markdown link and bold formatting are tangled — the opening '**' is inside the link text but the closing '**' is outside, producing broken bold rendering.
    - `[**Minnedemo](https://minnestar.org/minnedemo/) 39**`
    - Fix: Rewrite as **[Minnedemo](https://minnestar.org/minnedemo/) 39** so bold wraps the entire phrase cleanly.
  - **[LOW] typo** — 'All in thought' appears to be a typo for 'All in though' (or 'All in all though').
    - `All in thought, since I have the iPhone 14 Pro no upgrade for me.`
    - Fix: Change 'All in thought' to 'All in all though' or similar.

### #263 — Weekly Thing 263 / Copilot, Del.icio.us, Pancake

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and a missing space adjacent to a link were noted.
  - **[LOW] typo** — Missing apostrophe in possessive 'week's'.
    - `Enjoy this weeks links! 👍`
    - Fix: Change to 'this week's links'.
  - **[LOW] typo** — Sentence begins with lowercase 'the' and 'Microsofts' is missing a possessive apostrophe.
    - `the rollout of Copilot is starting across Microsofts various platforms.`
    - Fix: Capitalize 'The' and change 'Microsofts' to 'Microsoft's'.
  - **[LOW] typo** — 'buidling' is a clear misspelling of 'building'.
    - `insert into the software you are buidling`
    - Fix: Correct 'buidling' to 'building'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `Not good when your on deadline!`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — Missing space between the closing link parenthesis and 'called', causing the words to run together in rendered output.
    - `chatbot](https://www.economist.com/leaders/2023/02/09/the-battle-for-internet-search)called Claude`
    - Fix: Add a space between ')' and 'called'.
  - **[LOW] typo** — 'blog' should be 'block' in context of robots.txt.
    - `If you really want to blog robots`
    - Fix: Change 'blog robots' to 'block robots'.

### #264 — Weekly Thing 264 / Dazed, Zany, Llama

- Era: Buttondown
- Overall: The issue is in good shape overall; only two minor typos noted.
  - **[LOW] typo** — Unclosed parenthesis — the phrase opens with `(` but never closes before the period.
    - `Gothelf shares twelve areas to focus your organization to improve at being customer centric (or obsessed as he says.`
    - Fix: Add a closing parenthesis: `(or obsessed as he says).`
  - **[LOW] typo** — Clear typo — should be 'crowd' not 'crowed'.
    - `addressed the crowed.`
    - Fix: Change 'crowed' to 'crowd'.

### #265 — Weekly Thing 265 / Magic, Copilot, Shortery

- Era: Buttondown
- Overall: The issue is clean and well-structured; the only notable issue is a mislabeled link where 'Feedbin' appears as link text for a Pinboard Popular URL.
  - **[MEDIUM] dangling-reference** — The link text says 'Feedbin' but the URL points to Pinboard Popular; the sentence context ('Since I also use Pinboard...') makes clear the link label should be 'Pinboard Popular', not 'Feedbin'.
    - `One of my favorites like this is the **[Feedbin](https://pinboard.in/popular/)** feed.`
    - Fix: Change the link text from 'Feedbin' to 'Pinboard Popular' to match the URL and surrounding context.

### #266 — Weekly Thing 266 / Obsessed, DiceRight, Omnivore

- Era: Buttondown
- Overall: Issue reads cleanly overall; only minor issues — a malformed markdown link around '(DSR', a duplicated 'have have', and two H3 section headers that lack a parent H2.
  - **[LOW] typo** — The markdown link syntax appears malformed — the opening paren is inside the bracket text and there is no closing paren before the URL, producing broken rendering like '(DSR' as link text with no closing ')'.
    - `The DAI Savings Rate [(DSR](https://blog.makerdao.com/dai-savings-rate/) is an addition`
    - Fix: Rewrite as '([DSR](https://blog.makerdao.com/dai-savings-rate/))' so the parentheses wrap the link properly.
  - **[LOW] typo** — Duplicated word 'have have'.
    - `and now have have [Agave sDai]`
    - Fix: Remove the duplicate 'have'.
  - **[LOW] header-error** — This H3 sits outside any canonical H2 section (between Notable items and Journal), making it an orphan heading in the TOC structure; other issues use '## Recommended Links' as an H2 section.
    - `### Recommend`
    - Fix: Promote to '## Recommended' (H2) or place under an appropriate H2 section.
  - **[LOW] header-error** — This H3 appears after the Journal section's H3 entries with no parent H2, making it an orphan heading.
    - `### Weekly Thing Forum 🆕`
    - Fix: Promote to an H2 (e.g., '## Weekly Thing Forum') so it registers as its own section.

### #267 — Weekly Thing 267 / Generative, Ghibli, Mermaid

- Era: Buttondown
- Overall: The issue is in good shape overall with era-normal structure; only a handful of minor typos are worth a quick pass.
  - **[LOW] typo** — This should be 'I love boat cruises' — 'live' is an obvious typo in context.
    - `I live boat cruises.`
    - Fix: Change 'live' to 'love'.
  - **[LOW] typo** — 'your' should be 'you're' (you are focused).
    - `If your focused on minimizing distractions`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — 'you content' should be 'your content'.
    - `to make sure you content is on your own domain`
    - Fix: Change 'you' to 'your'.
  - **[LOW] typo** — Appears to be a garbled phrase in the Briefly blurb about Nota — likely meant 'and variables' with an extraneous 'on'.
    - `on and variables`
    - Fix: Remove the stray 'on' or reword to 'and variables'.

### #268 — Weekly Thing 268 / Schema, Achtung, Gamification

- Era: Buttondown
- Overall: The issue is in good shape overall; only a few minor prose typos were found.
  - **[LOW] typo** — Duplicated word 'how how' and 'are view' appears to be a typo for 'our view'.
    - `Wolfram later reflecting how how that affects are view of time…`
    - Fix: Change to 'Wolfram later reflecting how that affects our view of time…'
  - **[LOW] typo** — Missing verb; likely 'I like that' or 'I appreciate that'.
    - `This is pretty straightforward, and I that it stays pretty simple`
    - Fix: Change to 'I like that it stays pretty simple'.

### #269 — Weekly Thing 269 / Phind, Textcasting, Tailspin

- Era: Buttondown
- Overall: Issue is generally in good shape and reads cleanly; only minor typos and a couple of orphan H3 headings that slightly affect TOC consistency.
  - **[LOW] typo** — The number formatting is ambiguous (European-style decimal vs thousands separator); in context of a $13.5B overhang this should likely be 389,197 Bitcoin.
    - `governments hold 389.197 Bitcoin they have seized`
    - Fix: Verify and change to '389,197 Bitcoin' if that's the intended figure.
  - **[LOW] typo** — 'not such thing' should be 'no such thing'.
    - `there is not such thing as a worthwhile social network`
    - Fix: Change 'not such thing' to 'no such thing'.
  - **[LOW] header-error** — This H3 appears outside any canonical section and acts as a standalone section heading; other issues use '## Recommended Links' at H2, making this an inconsistent/orphan heading.
    - `### Recommend`
    - Fix: Promote to '## Recommended Links' (or place under an appropriate H2) to match canonical section structure.
  - **[LOW] header-error** — Orphan H3 not nested under an H2 section, breaking the TOC hierarchy.
    - `### Weekly Thing Forum 🆕`
    - Fix: Either promote to H2 or place under an appropriate H2 parent.

### #271 — Weekly Thing 271 / Imperfectionist, Zeitgeisty, Inko

- Era: Buttondown
- Overall: The issue is in good shape overall with only minor typos and one minor heading-hierarchy quirk; nothing breaks rendering.
  - **[LOW] typo** — Missing possessive apostrophe in 'Signal's'.
    - `I respect Signals mission`
    - Fix: Change to 'Signal's mission'.
  - **[LOW] typo** — Grammatical error: 'this ads' should be 'these ads'.
    - `I’m happy to let this ads in`
    - Fix: Change to 'these ads'.
  - **[LOW] typo** — 'no where' should be one word 'nowhere'.
    - `but in my opinion no where near enough`
    - Fix: Change 'no where' to 'nowhere'.
  - **[LOW] header-error** — An H3 'Related Links' appears inside the Journal section nested under another H3 post, which creates an inconsistent sub-heading structure (likely should be H4 or bold).
    - `### Related Links`
    - Fix: Demote to H4 or reformat as bold text to preserve section hierarchy.

### #272 — Weekly Thing 272 / Escape, Fuzzy, Melodrip

- Era: Buttondown
- Overall: The issue is in good shape overall with era-normal structure; only a minor spacing artifact inside a quoted passage was noted.
  - **[LOW] typo** — Missing space between bolded word 'democracy' and the word 'and' in the blockquote.
    - `**democracy**and **differential**`
    - Fix: This is inside a blockquote from the source; if faithful to original, leave, otherwise add a space: 'democracy** and **differential**'.

### #273 — Weekly Thing 273 / Trippy, Buffalo, Bitkey

- Era: Buttondown
- Overall: The issue is in good shape overall; the only notable problem is a Ridwell invite link missing its https:// scheme, which will render as a broken relative link.
  - **[MEDIUM] malformed-link** — The markdown link URL is missing a protocol (http:// or https://), so most renderers will treat it as a relative link rather than an external one.
    - `If you want to sign up this [invite link](msp.ridwell.com/TAMARA297) will give you a month free.`
    - Fix: Change the URL to https://msp.ridwell.com/TAMARA297.

### #274 — Weekly Thing 274 / Gibberish, Happyfeed, Airshow

- Era: Buttondown
- Overall: The issue is substantive and reads well; the main concern is unrendered Buttondown template tags in the support footer, plus one minor author-name typo.
  - **[HIGH] migration-artifact** — Unrendered Buttondown template tags appear literally in the body instead of being substituted with the issue subject and URL.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Ensure the template variables are rendered by Buttondown, or replace with static text/link to the issue.
  - **[LOW] typo** — Author's first name is misspelled; should be 'Paul'.
    - `by Pual Scharre`
    - Fix: Change 'Pual' to 'Paul'.

### #275 — Weekly Thing 275 / Vision, Sense, Magic

- Era: Buttondown
- Overall: Issue is in good shape overall; only concern is the unrendered Buttondown template variables in the support section footer.
  - **[MEDIUM] migration-artifact** — Buttondown template tags `{{ email.subject }}` and `{{ email_url }}` appear unrendered in the archived web version, exposing raw template syntax to readers.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue title and archive URL, or confirm these render correctly in the archive template.

### #276 — Weekly Thing 276 / Contextual, Copilot, Collections

- Era: Buttondown
- Overall: The issue reads cleanly overall; the only notable problem is unrendered Buttondown template variables in the footer support section.
  - **[MEDIUM] migration-artifact** — Buttondown template tags appear unrendered in the archived body, showing literal `{{ email.subject }}` and `{{ email_url }}` to readers.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue subject and URL, or wrap in {% raw %} if intentionally preserved, so the archive doesn't display template placeholders.

### #277 — Weekly Thing 277 / Privacy, Scammed, OmniFocus

- Era: Buttondown
- Overall: Issue #277 is clean and well-formed; the only potential concern is the Buttondown template tags in the footer, which may render literally on the archive site.
  - **[LOW] migration-artifact** — Buttondown template tags appear in raw form; these may be intentional Buttondown variables that render at send-time but appear literally in the web archive.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify that Buttondown renders these variables in the archive view; if not, replace with a static link to this issue.

### #278 — Weekly Thing 278 / Groq, GraphRAG, Gasless

- Era: Buttondown
- Overall: Issue is in generally good shape; the main concern is the unrendered Buttondown template tags in the support footer, plus a couple of minor typos.
  - **[MEDIUM] migration-artifact** — Buttondown template tags appear to not be rendering — the literal `{{ email.subject }}` and `{{ email_url }}` placeholders are showing in the archived body instead of the actual subject and URL.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace the unrendered template tags with the actual subject and archive URL for issue 278, or wrap in Buttondown's supported syntax so they render.
  - **[LOW] typo** — 'there' should be 'their' — possessive pronoun needed.
    - `would have preferred there engagement on this incident`
    - Fix: Change 'there engagement' to 'their engagement'.
  - **[LOW] typo** — 'wiling' is a misspelling of 'willing'.
    - `tradeoff some are wiling to make`
    - Fix: Change 'wiling' to 'willing'.

### #279 — Weekly Thing 279 / Nushell, BlackCat, Daemons

- Era: Buttondown
- Overall: Issue #279 is in good shape overall; only a few minor typos ('Prett', 'hose', 'Hou') and a possible footer template-tag rendering concern.
  - **[LOW] typo** — Missing 'y' in 'Pretty' — a clear typo.
    - `Prett nifty! 🤓`
    - Fix: Change 'Prett' to 'Pretty'.
  - **[LOW] typo** — 'Hou' appears to be a typo; the referenced author is Tyler Hou, so should likely read 'Hou then writes' referring to Tyler Hou — but as written it's an orphan first name without context (earlier the author cited was Wayne).
    - `Hou then writes a great response`
    - Fix: Change to 'Tyler Hou then writes' for clarity.
  - **[LOW] typo** — 'hose' should be 'house'.
    - `Power has been shut off to the entire hose now`
    - Fix: Change 'hose' to 'house'.
  - **[LOW] migration-artifact** — Buttondown template tags are in the footer; these are era-normal for Buttondown emails but may render as literal text in the archive if not processed.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify these Buttondown merge tags are substituted or stripped in the archive render; otherwise replace with static text.

### #280 — Weekly Thing 280 / Canvas, Undersea, Documents

- Era: Buttondown
- Overall: Readable overall, but the footer leaks raw Buttondown template tags and an inline GIF host is dead, both of which visibly affect the archived page.
  - **[HIGH] migration-artifact** — Buttondown template variables `{{ email.subject }}` and `{{ email_url }}` appear unrendered in the archive body, showing raw template tags to readers.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual subject/URL or remove this line from the archived version.
  - **[MEDIUM] image-problem** — Static audit confirms this Glitch-hosted GIF is unreachable (DNS/host error), so the Dark Horse Analytics animation the text references is broken in the archive.
    - `![](https://cdn.glitch.global/d45aff89-36ba-46db-8c7c-3da7c8a93931/IMG_3448.gif)`
    - Fix: Rehost the GIF on files.thingelstad.com or link directly to the Dark Horse Analytics source.
  - **[LOW] narrative-break** — "hits frames" is a leftover word from an edit — the sentence should read "Berners-Lee frames" (or "hits on"), producing a grammatically broken clause.
    - `Ever the engineer though, Berners-Lee hits frames his two primary concerns with his own invention.`
    - Fix: Delete "hits" so it reads "Berners-Lee frames his two primary concerns."
  - **[LOW] narrative-break** — Quoted text contains "You have know" which looks like a typo inside the blockquote (likely "You have to know"); worth noting even though it's quoted.
    - `You have know how to work with others to build something together that's bigger than any of you.`
    - Fix: Verify against source and add [sic] or correct to "You have to know" if it's a transcription error.
  - **[LOW] malformed-link** — The bold markers are unbalanced — `**` opens inside the link text but the closing `**` is outside the link, which can render as a stray asterisk or mis-bolded text.
    - `[**Lead With Influence](https://www.mattnorman.com/influence/)**`
    - Fix: Balance the emphasis: `**[Lead With Influence](https://www.mattnorman.com/influence/)**`.

### #281 — Weekly Thing 281 / Fediverse, Odyssey, Echo Chess

- Era: Buttondown
- Overall: Issue is well-structured and reads cleanly; the only notable problem is unrendered Buttondown template tags in the support footer.
  - **[HIGH] migration-artifact** — Buttondown template variables {{ email.subject }} and {{ email_url }} were not interpolated, leaving literal template tags visible to readers of the archive.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the rendered subject and archive URL, or wrap in {% raw %} if intentional, or remove the line from the archived version.

### #282 — Weekly Thing 282 / Decentralized, Blobs, Rewards

- Era: Buttondown
- Overall: Issue is largely clean; only minor concerns are unrendered Buttondown template tokens in the support section and a couple of small typos.
  - **[LOW] migration-artifact** — Buttondown template variables appear in the markdown; these render as literal text in the archive rather than being interpolated.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual subject and archive URL for the static archive, or confirm the renderer substitutes these tokens.
  - **[LOW] typo** — Likely a missing digit or word — '90 Easter Egg Hunt' appears to be missing context (e.g., '90-minute' or '90-egg').
    - `**90 Easter Egg Hunt**`
    - Fix: Clarify to '90-egg Easter Egg Hunt' or similar intended phrasing.
  - **[LOW] typo** — 'attach' should be 'attack' given context about the XZ backdoor.
    - `Bray correctly framing that Open-Source software has been hugely beneficial to all but that the XZ attach shows a clear weakness.`
    - Fix: Change 'attach' to 'attack'.

### #283 — Weekly Thing 283 / Betula, Blocky, Tables

- Era: Buttondown
- Overall: Issue is in good shape overall; main concerns are a mismatched bold/link markup around 'Solo', a minor typo ('through out'), and a stray 'Katzner.' fragment.
  - **[MEDIUM] malformed-link** — The static audit flagged [Pro] as bracketed text with no link, but this is a valid label/tag in OmniFocus release notes indicating the Pro tier feature, not a broken link.
    - `**Custom Perspectives [Pro]**`
    - Fix: No fix needed — [Pro] is a legitimate OmniFocus edition tag, not a malformed link.
  - **[LOW] narrative-break** — 'to through out' should be 'to throw out' — a clear typo.
    - `AI shattering the preconceptions caused players to through out the old and reinvent their game.`
    - Fix: Change 'through out' to 'throw out'.
  - **[MEDIUM] malformed-link** — The markdown link has mismatched bold markers — the opening ** is inside the link text but the closing ** is outside, which will render incorrectly.
    - `[**Solo: A Show About Friendship](https://theparkwaytheater.com/all-events/solo-story-friendship)**`
    - Fix: Move the bold markers consistently: [**Solo: A Show About Friendship**](https://theparkwaytheater.com/all-events/solo-story-friendship).
  - **[LOW] narrative-break** — The stray sentence 'Katzner.' appears to be an editing artifact / incomplete sentence fragment.
    - `Katzner recently moved to Minneapolis from New York. Katzner. He also had dinner`
    - Fix: Remove the orphan 'Katzner.' or complete the intended sentence.
  - **[LOW] migration-artifact** — These are Buttondown template tags that are intentional and will be replaced at send, but in the archive rendering they may appear literally if not processed.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify the archive renderer substitutes these tags; if not, replace with the issue's permalink and subject.

### #284 — Weekly Thing 284 / Playdate, Tetris, Calvin

- Era: Buttondown
- Overall: The issue is generally in good shape; minor concerns are an inconsistent H3 heading within the Journal section and Buttondown template tags that may not interpolate in the archive.
  - **[LOW] migration-artifact** — Buttondown template tags appear in the archived markdown; depending on rendering, these may show as literal tags rather than being interpolated in the web archive.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify these template tags are rendered correctly in the web archive, or replace with a static link to this issue.

### #285 — Weekly Thing 285 / Voyager, ActivityPub, Trackers

- Era: Buttondown
- Overall: Issue is in good shape overall; only a few minor typos in the Minnebar journal and Featured sections. The {{ email.subject }} and {{ email_url }} tags in the footer are standard Buttondown merge tags and render correctly, so not flagged.
  - **[LOW] typo** — 'welcome' should be 'welcomed' and 'technolgies' is a misspelling of 'technologists'.
    - `Minnestar welcome over 1,000 passionate technolgies`
    - Fix: Change to 'Minnestar welcomed over 1,000 passionate technologists'.
  - **[LOW] typo** — Earlier sentence 'not acknowledged inside our outside our practice' contains 'our' where 'or' is intended.
    - `this topic into the open and discuss it`
    - Fix: Change 'inside our outside our practice' to 'inside or outside our practice'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `If your curious what I do use for search`
    - Fix: Change 'If your curious' to 'If you're curious'.

### #286 — Weekly Thing 286 / Cypherpunk, Printing music, Rabbit

- Era: Buttondown
- Overall: Readable issue with several minor typos, an unclosed parenthesis, and a mis-balanced bold/link pair in the Constellation Fund heading that an editor should clean up.
  - **[LOW] typo** — 'thing' should be 'think' — clear typo.
    - `we need to not rely on documentation, and instead thing about something more professional.`
    - Fix: Change 'thing' to 'think'.
  - **[LOW] typo** — 'shows' should be 'shoes' — clear typo.
    - `accidentally activate car alarm while putting shows on.`
    - Fix: Change 'shows' to 'shoes'.
  - **[MEDIUM] narrative-break** — The parenthetical opened with '(which' is never closed — missing closing parenthesis after the link.
    - `(which kept reminding me of a similar theme in the movie [Grand Canyon](https://en.wikipedia.org/wiki/Grand_Canyon_\(1991_film\)). I have a soft spot`
    - Fix: Add closing ')' after the Grand Canyon link.
  - **[MEDIUM] narrative-break** — Bold markers are mismatched — '**' opens inside the first link text but closes after the second link, producing broken emphasis rendering.
    - `enjoyable evening at [**Constellation Fund](https://constellationfund.org/) [Bright Night](https://constellationfund.org/events) 2024**.`
    - Fix: Rebalance the bold markers so the '**' opens and closes around clean text, outside the link markup.
  - **[LOW] typo** — 'there' should be 'their' — clear homophone typo.
    - `It is there hardest room`
    - Fix: Change 'there' to 'their'.
  - **[LOW] typo** — 'even' should be 'event'.
    - `Bright Night is their annual even to celebrate`
    - Fix: Change 'even' to 'event'.
  - **[LOW] migration-artifact** — Buttondown template tags appear in the archived body; these are intended for email rendering and may display literally on the web archive.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Confirm these tags are rendered/replaced in the web archive; if not, substitute a static link and title.
  - **[LOW] header-error** — An H3 appears outside any H2 section (between Journal and Briefly), making it an orphan subheading in the TOC.
    - `### Weekly Thing Forum 🆕`
    - Fix: Promote to H2 or move under an appropriate parent section.

### #287 — Weekly Thing 287 / Plinky, Piccolo, Privacy

- Era: Buttondown
- Overall: Issue is in good shape overall; the main concern is the unrendered Buttondown template tags in the support section that will appear literally in the web archive.
  - **[MEDIUM] migration-artifact** — These are Buttondown template tags that should be rendered by the email platform; in the web archive they will appear as literal unrendered placeholders.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue title and URL (or wrap in the appropriate template syntax the static site renders) so the archive shows a real link.
  - **[LOW] typo** — The school is referred to throughout as 'Cristo Rey'; 'Cristy Rey' is a clear misspelling.
    - `who was part of TeamSPS as a Cristy Rey student`
    - Fix: Change 'Cristy Rey' to 'Cristo Rey'.

### #288 — Weekly Thing 288 / Hackerverse, Symbolica, Curators

- Era: Buttondown
- Overall: Issue is in good shape overall; only a couple of minor typos and no migration artifacts or structural problems. The Buttondown conditional merge tags ({% if %} / {{ subscriber.metadata.poap_7yr_url }}) are era-normal for personalized content.
  - **[LOW] typo** — 'contextualize is' appears to be a typo for 'contextualize it'.
    - `I don't know how to contextualize is, much less action it.`
    - Fix: Change 'contextualize is' to 'contextualize it'.
  - **[LOW] typo** — Missing word; should read 'Even the links they do allow you to add...'
    - `Even the links do allow you to add are transformed into internal links`
    - Fix: Insert 'they' so it reads 'Even the links they do allow you to add'.
  - **[LOW] typo** — The display text 'Modovik' is misspelled; the correct spelling (matching the Wikipedia link) is 'Medovik'.
    - `[Modovik](https://en.wikipedia.org/wiki/Medovik) cake`
    - Fix: Change the link text to 'Medovik'.

### #289 — Weekly Thing 289 / Queueing, Counting, Mapping

- Era: Buttondown
- Overall: The issue is generally clean and readable; only minor typos and one malformed H3 title need attention.
  - **[MEDIUM] typo** — Stray 'y' character at end of sentence appears to be a typo.
    - `It is a cool spot.y`
    - Fix: Remove the trailing 'y' so it reads 'It is a cool spot.'
  - **[LOW] typo** — Grammatical error: 'have wore' should be 'have worn' (or 'was wearing').
    - `I was lucky enough to have wore my Chaco sandals`
    - Fix: Change 'have wore' to 'have worn'.
  - **[LOW] typo** — Double verb 'I'm was' — likely meant 'I was' or 'I'm'.
    - `I'm was very happy`
    - Fix: Change to 'I was very happy'.
  - **[MEDIUM] malformed-link** — Title appears to be missing a separator between 'Model' and 'Anthropic' (likely lost a pipe or dash during migration).
    - `### [Mapping the Mind of a Large Language Model Anthropic](https://www.anthropic.com/research/mapping-mind-language-model)`
    - Fix: Insert a separator, e.g., 'Mapping the Mind of a Large Language Model | Anthropic'.

### #290 — Weekly Thing 290 / Kino, Krebs, Kagi

- Era: Buttondown
- Overall: Clean issue overall; only minor structural/template concerns worth noting.
  - **[LOW] header-error** — This H3 appears outside any H2 section (between Journal and Briefly) with no parent link-title pattern, making it an orphan heading relative to the canonical section structure.
    - `### Weekly Thing Forum 🆕`
    - Fix: Promote to an H2 section (e.g., ## Weekly Thing Forum) or move under an appropriate parent section.
  - **[LOW] migration-artifact** — These Buttondown template tags are intentional for email but render as literal text in the web archive if not processed.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Confirm the archive renderer substitutes these tags; if not, replace with a static link to the issue.

### #291 — Weekly Thing 291 / Ireland 🇮🇪

- Era: Buttondown
- Overall: The issue is in very good shape — a well-organized special Ireland edition with no notable narrative breaks, broken links, or header issues; only the Buttondown template tags in the footer might warrant a look depending on archive rendering.
  - **[LOW] migration-artifact** — Buttondown template tags appear here; these are intentional in Buttondown delivery but may render as literal text in the web archive if not processed.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify these template variables render correctly in the archive; if not, replace with issue-specific subject and URL.

### #292 — Weekly Thing 292 / Signal, Checkboxes, Hope

- Era: Buttondown
- Overall: The issue is in good shape overall; the only concern is the unrendered Buttondown template variables in the footer share link. The static audit's flagged '[The Knowledge Project Ep. #202]' is a false positive — it is part of the H3 link title text, not a dangling bracket.
  - **[LOW] migration-artifact** — These Buttondown template variables appear unrendered in the archive body; in the web archive they likely display literally rather than as a populated link.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue title and archive URL, or confirm the archive renderer substitutes these template tags.

### #293 — Weekly Thing 293 / WHOIS, Glowtime, Place

- Era: Buttondown
- Overall: Issue is clean and well-formed overall; the only notable problem is unrendered Buttondown template tags in the support-footer share link.
  - **[MEDIUM] migration-artifact** — Buttondown template tags appear unrendered in the archived markdown, showing raw `{{ email.subject }}` and `{{ email_url }}` instead of a working share link.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace the template tags with the static issue title and archive URL, or wrap in the appropriate raw/render syntax so they resolve on the archive site.

### #294 — Weekly Thing 294 / Vaporizing, Intelligence, Contraption

- Era: Buttondown
- Overall: Issue is in good shape overall; the main concern is an unrendered Buttondown template tag in the footer support section.
  - **[LOW] migration-artifact** — Buttondown template tags appear unrendered in the archived body, showing literal `{{ email.subject }}` and `{{ email_url }}` instead of the issue title and URL.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue title and archive URL (or ensure the template variables are resolved at render time).
  - **[LOW] header-error** — The Weekly Thing Forum block uses an H3 despite not being a link-title under a canonical H2 section; it sits between Journal and Briefly as a standalone block, which is inconsistent with section header levels.
    - `### Weekly Thing Forum 🆕`
    - Fix: Consider promoting to an H2 section header or otherwise clarifying its placement in the TOC hierarchy.

### #295 — Weekly Thing 295 / Links, Surveillance, POSSE

- Era: Buttondown
- Overall: The issue reads cleanly overall; the main concern is unrendered Buttondown template tags in the closing footer that leak raw `{{ ... }}` syntax to readers.
  - **[HIGH] migration-artifact** — Buttondown template tags `{{ email.subject }}` and `{{ email_url }}` were not rendered, leaving raw template syntax visible to readers.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Replace with the actual issue title and URL, or ensure these template variables are rendered at publish time.
  - **[LOW] typo** — Duplicated word 'the the'.
    - `Let's jump into the the links…`
    - Fix: Remove the duplicate 'the'.

### #296 — Weekly Thing 296 / Awk, Fav, Alarmo

- Era: Buttondown
- Overall: Issue reads cleanly with era-normal structure; only a few minor typos and a possible unrendered Buttondown template tag in the footer.
  - **[LOW] typo** — 'their' should be 'there'.
    - `a security guard was their to promptly stop you`
    - Fix: Change 'their' to 'there'.
  - **[LOW] typo** — 'summery' should be 'summary'.
    - `Great summery from Gruber`
    - Fix: Change 'summery' to 'summary'.
  - **[LOW] typo** — 'Impresive' is missing an 's'.
    - `8:53 min/mile pace! Impresive!`
    - Fix: Change 'Impresive' to 'Impressive'.
  - **[LOW] migration-artifact** — Buttondown template tags appear in the archive body; they may render literally on the web archive rather than being substituted.
    - `**Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify these template variables are rendered/stripped for the archive, or replace with the issue title and URL.

### #297 — Weekly Thing 297 / People, Building, "Pure Blogger

- Era: Buttondown
- Overall: Issue is generally in good shape; minor issues include an orphan H3 for the Forum section, a protocol-less link to Superior Creamery, and a couple of small typos.
  - **[MEDIUM] header-error** — This H3 appears outside any parent section (it follows the North Shore Weekend Log H3 sub-items and sits between Journal and Briefly), so it is orphaned in the TOC hierarchy rather than being grouped under a canonical H2 section.
    - `### Weekly Thing Forum 🆕`
    - Fix: Promote to an H2 or group it under an appropriate section so it is not orphaned at the H3 level between major sections.
  - **[MEDIUM] malformed-link** — The link target is missing the protocol, so markdown will render it as a relative link rather than an external URL.
    - `Ice cream at [Superior Creamery](superiorcreamery.com).`
    - Fix: Change the URL to https://superiorcreamery.com.
  - **[LOW] typo** — Capitalized 'Of' mid-sentence is clearly a typo for 'of'.
    - `Check out Of Airbnb.`
    - Fix: Change 'Check out Of Airbnb' to 'Check out of Airbnb'.
  - **[LOW] typo** — Missing verb — should read 'it is truly a marvel' or 'it was truly a marvel'.
    - `I watched the replay of the Starship launch and it truly a marvel.`
    - Fix: Insert 'was' or 'is' after 'it'.

### #298 — Weekly Thing 298 / Tool, Solar, Circles

- Era: Buttondown
- Overall: Issue is in generally good shape; main concern is an unwrapped Nunjucks template block in the Straw Poll section that may render literally in the archive, plus a couple of minor typos.
  - **[MEDIUM] migration-artifact** — This is a Nunjucks template block not wrapped in {% raw %}, so on the archive website these tags may render literally or cause template errors rather than producing the intended fallback text.
    - `{% if medium == 'email' %}
{{ survey.strawpoll298 }}
{% else %}
_To respond to Straw Polls please [subscribe to the Weekly Thing]({{ subscribe_url }}) via email._
{% endif %}`
    - Fix: Wrap the template conditional in {% raw %}...{% endraw %} so it renders as intended in the archive, or ensure the archive build evaluates it to the subscribe fallback.
  - **[LOW] migration-artifact** — Buttondown merge tags {{ email.subject }} and {{ email_url }} may appear literally in the archive rendering rather than being substituted.
    - `- **Share** [{{ email.subject }}]({{ email_url }}) with others you know!`
    - Fix: Verify these merge tags are resolved at archive render time, or replace with the static issue title and URL.
  - **[LOW] typo** — 'we our busy' should be 'we are busy' — clear grammatical typo.
    - `It isn't all relaxation though as we our busy making candles`
    - Fix: Change 'we our busy' to 'we are busy'.
  - **[LOW] typo** — 'he last slice' should be 'the last slice'.
    - `the person in front of us bought he last slice`
    - Fix: Change 'he last slice' to 'the last slice'.
  - **[MEDIUM] narrative-break** — The sentence 'In 2010 Citizens United.' is incomplete — it's missing a verb (e.g., 'was decided' or 'happened'), reading as a truncated fragment.
    - `In 2010 [Citizens United](https://en.wikipedia.org/wiki/Citizens_United_v._FEC).`
    - Fix: Complete the sentence, e.g., 'In 2010 the Supreme Court decided Citizens United.'

### #299 — Weekly Thing 299 / Apples, Abundance, Australia

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor incomplete sentence in the Apple Intelligence commentary stands out.
  - **[MEDIUM] narrative-break** — The second sentence is missing a verb/object — 'be able to [do what]?' — reading as a truncated thought.
    - `My initial impression is okay, it is interesting. I don't think we will really be able to though until the whole thing has shipped.`
    - Fix: Complete the sentence, e.g., 'I don't think we will really be able to judge it until the whole thing has shipped.'
  - **[LOW] dangling-reference** — The acronym for Child Online Protection Act is COPA, but the more commonly referenced law is COPPA (Children's Online Privacy Protection Act); possible confusion but linked Wikipedia article matches the text as written — low confidence issue.
    - `Outside of the [Child Online Protection Act](https://en.wikipedia.org/wiki/Child_Online_Protection_Act) (COPA)`
    - Fix: Verify whether the intended law/acronym is correct; otherwise ignore.

### #300 — Weekly Thing 300 / Traceroute, 34x34x34, Typst

- Era: Buttondown
- Overall: Issue #300 is in good shape overall; only a minor wording slip in the Straw Poll intro was noted.
  - **[LOW] typo** — "a many articles" contains an extra article word; should be "shared many articles" or "shared a lot of articles".
    - `I've shared a many articles about all the incredible things you can do with AI tools.`
    - Fix: Remove the stray "a" so it reads "I've shared many articles".

### #301 — Weekly Thing 301 / TinyTroupe, Monarch, Leaving

- Era: Buttondown
- Overall: Issue is in good shape overall with only minor typos and one mild header-nesting concern; no migration artifacts or broken references.
  - **[LOW] typo** — Missing apostrophe — should be 'package's documentation'.
    - `The packages documentation highlights`
    - Fix: Change 'packages' to 'package's'.
  - **[LOW] typo** — Missing space between the bolded word 'proposals' and 'and'.
    - `**read project or product proposals**and`
    - Fix: Add a space: 'proposals** and'.
  - **[LOW] typo** — Two typos: 'HIs' should be 'His' and 'from' should be 'form'.
    - `HIs view of this being a different from of augmented reality`
    - Fix: Fix to 'His view of this being a different form of augmented reality'.
  - **[LOW] typo** — Should be 'researches' (verb), not 'researchers'.
    - `My non-profit researchers this condition`
    - Fix: Change 'researchers' to 'researches'.
  - **[LOW] typo** — Missing space between sentence-ending period and hashtag.
    - `the world's retail network.#TeamSPS`
    - Fix: Add a space before '#TeamSPS'.
  - **[LOW] header-error** — 'Weekly Thing Forum' is a standalone section following the Journal, but it uses H3 which nests it under Journal in the TOC rather than being a top-level section like Briefly/Fortune.
    - `### Weekly Thing Forum 🆕`
    - Fix: Consider promoting to H2 (## Weekly Thing Forum) for consistency with other top-level sections.
  - **[LOW] typo** — 'Weekly Think' appears to be a typo for 'Weekly Thing' given all surrounding context.
    - `[Weekly Think #300](https://ponder.us/group/weeklything/discussions/845)`
    - Fix: Change 'Weekly Think' to 'Weekly Thing'.

### #302 — Weekly Thing 302 / Recipe, Poetry, OnAir

- Era: Buttondown
- Overall: Issue is largely in good shape but contains one high-severity malformed link (Kieran Culkin) and several minor typos worth cleanup.
  - **[MEDIUM] typo** — Clear typo: 'and option' should be 'an option', and there's a double space.
    - `but alas it wasn't  and option.`
    - Fix: Change to 'but alas it wasn't an option.'
  - **[HIGH] malformed-link** — The markdown link's URL is the text 'Kieran Culkin' instead of an actual URL, producing a broken link.
    - `[Kieran Culkin](Kieran Culkin)’s`
    - Fix: Replace with a valid URL (e.g., the Wikipedia page) or remove the link syntax.
  - **[LOW] typo** — 'seond' is a misspelling of 'second'.
    - `This was only the **seond showing ever**!`
    - Fix: Correct 'seond' to 'second'.
  - **[LOW] typo** — Common misuse: the idiom is 'wreak havoc', not 'wreck havoc'.
    - `hackers that wreck havoc`
    - Fix: Change 'wreck havoc' to 'wreak havoc'.
  - **[LOW] typo** — Stray 'the' creates an ungrammatical phrase ('in the a couple of').
    - `There is some reminiscing in the a couple of the links`
    - Fix: Remove 'the' so it reads 'reminiscing in a couple of the links'.
  - **[LOW] typo** — 'fro' is a typo for 'for'.
    - `Dr. Carlis holding the book fro the class up`
    - Fix: Change 'fro' to 'for'.
  - **[LOW] typo** — 'your' should be 'you're' (contraction of 'you are').
    - `- What your doing now`
    - Fix: Change 'What your doing now' to 'What you're doing now'.

### #303 — Weekly Thing 303 / Petnames, Synapse, jless

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor wording/title issues noted.
  - **[LOW] typo** — Duplicated verb ('is ... is') appears to be a typo where one 'is' should be removed.
    - `So what is your price is to go social media free?`
    - Fix: Change to 'So what is your price to go social media free?'
  - **[LOW] malformed-link** — Title appears to be missing a separator (likely should be 'Introducing the Model Context Protocol \ Anthropic' or similar), reading awkwardly.
    - `### [Introducing the Model Context Protocol Anthropic](https://www.anthropic.com/news/model-context-protocol)`
    - Fix: Add a separator such as ' \ ' or '—' between 'Protocol' and 'Anthropic'.

### #304 — Weekly Thing 304 / Connections, Vince, Markwhen

- Era: Buttondown
- Overall: Issue is generally in good shape; a handful of minor typos are the only concerns.
  - **[LOW] typo** — Should be 'songwriter' not 'songwriting'.
    - `MacGowan was an amazing songwriting.`
    - Fix: Change 'songwriting' to 'songwriter'.
  - **[LOW] typo** — 'tonightt' has a double-t typo.
    - `We saw The Best Christmas Pageant Ever tonightt.`
    - Fix: Change 'tonightt' to 'tonight'.
  - **[LOW] typo** — 'wee' should be 'see'.
    - `Also wee [Gruber writeup]`
    - Fix: Change 'wee' to 'see'.
  - **[LOW] typo** — 'built' should be 'build'.
    - `to built crypto capability`
    - Fix: Change 'built' to 'build'.
  - **[LOW] typo** — 'take a the' appears to be missing 'on' — should be 'take on the'.
    - `Interesting take a the limits of expression`
    - Fix: Change 'take a the' to 'take on the'.

### #305 — Weekly Thing 305 / Lighthouse, Willow, Artemis

- Era: Buttondown
- Overall: The issue is in good shape overall; only minor inconsistencies in Journal entry formatting and a small typo were noted.
  - **[LOW] narrative-break** — Double space between 'versus' and 'patterns' suggests a minor editing artifact, though it renders fine.
    - `versus  patterns that will result in burnout.`
    - Fix: Remove the extra space.
  - **[LOW] typo** — Grammatical error — should be 'like to publish' not 'like to publishing'.
    - `or would just like to publishing on your own`
    - Fix: Change 'like to publishing' to 'like to publish'.

### #306 — Weekly Thing 306 / Spell, McLarens, Lynch

- Era: Buttondown
- Overall: The issue is in good shape overall; the static-audit orphan H3 is valid and there are a few minor typos but nothing that breaks reading.
  - **[LOW] header-error** — This H3 appears in the intro section before any H2, making it an orphan subheading (confirmed by static audit).
    - `### Introducing the Christmas Blogs`
    - Fix: Consider making this an H2 or placing it under an appropriate H2 section.
  - **[LOW] typo** — Duplicated subject: 'that we caused us' should be 'that caused us'.
    - `We had five “rookie” misses that we caused us to “face palm”.`
    - Fix: Remove 'we' so it reads 'five rookie misses that caused us to face palm'.
  - **[LOW] typo** — 'Your' should be 'You're' (contraction of 'you are').
    - `Your not just pounding codes into locks`
    - Fix: Change 'Your' to 'You're'.
  - **[LOW] typo** — Grammatical mismatch: 'a similar vibes' mixes singular article with plural noun.
    - `I hope your weekend is off to a similar vibes!`
    - Fix: Change to 'similar vibes' or 'a similar vibe'.

### #308 — Weekly Thing 308 / Tapestry, Terminal, Tab

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor typo ('even thought') and an orphan H3 for the Weekly Thing Forum section are worth noting.
  - **[LOW] typo** — 'even thought' should be 'even though'.
    - `surprisingly sent from Minneapolis, MN even thought I didn't think you would be getting this today.`
    - Fix: Change 'even thought' to 'even though'.
  - **[MEDIUM] header-error** — This H3 appears outside any canonical section (it sits between the Journal section and Briefly), making it an orphan heading rather than a link title following the era's `### [Title](url)` convention.
    - `### Weekly Thing Forum 🆕`
    - Fix: Promote to `## Weekly Thing Forum 🆕` as its own section, consistent with other top-level sections.

### #309 — Weekly Thing 309 / Programming, Silence, Drones

- Era: Buttondown
- Overall: The issue is structurally sound and reads well; main concerns are a handful of minor typos (there/their, funderal, legalize) and some header-level inconsistencies in the guest-post and Super Bowl ads sections.
  - **[LOW] typo** — 'there' should be 'their' — a clear homophone error.
    - `no idea how modern programmers do there craft.`
    - Fix: Change 'there craft' to 'their craft'.
  - **[LOW] typo** — 'funderal' is a typo for 'funeral'.
    - `a novel-like background of being a funderal director`
    - Fix: Change 'funderal' to 'funeral'.
  - **[MEDIUM] header-error** — This guest-post section uses H2, placing it at the same level as canonical sections like Featured/Notable/Journal, which may disrupt the TOC hierarchy within the issue (it appears between Featured and Notable as a non-canonical top-level section).
    - `## Introducing Eric Cohn's Blog`
    - Fix: Consider demoting to H3 under Featured, or otherwise integrating consistently with the issue's section hierarchy.
  - **[MEDIUM] header-error** — Inside the 'Super Bowl LIX Ads' Journal entry (itself H3), the individual ad subheads are also H3, which flattens the hierarchy and makes the ad list siblings of the journal entry rather than children.
    - `### So Win -- Nike`
    - Fix: Demote the per-ad headings to H4 so they nest under the Super Bowl LIX Ads entry.
  - **[LOW] typo** — 'legalize' should be 'legalese' (legal jargon).
    - `This is filled with a lot of legalize`
    - Fix: Change 'legalize' to 'legalese'.
  - **[LOW] typo** — Missing article — should read 'answered in the latest issue of'.
    - `answered in latest issue of`
    - Fix: Insert 'the' before 'latest'.

### #311 — Weekly Thing 311 / WikiTok, Bookmarklets, Tapestry

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and a missing space after a markdown link.
  - **[LOW] typo** — Missing space between the closing parenthesis of the markdown link and the word 'of', which will render as 'canary statementof sorts'.
    - `a [canary statement](https://en.wikipedia.org/wiki/Warrant_canary)of sorts`
    - Fix: Add a space: '[canary statement](...) of sorts'.
  - **[LOW] typo** — Sentence starts with lowercase 'it' after a period.
    - `Stop calling any of this stuff "technology". it doesn't deserve the credit.`
    - Fix: Capitalize to 'It doesn't deserve the credit.'
  - **[LOW] typo** — Missing word 'to' — should read 'I decided to use the Shortcut'.
    - `I decided use the Shortcut I wrote`
    - Fix: Insert 'to': 'I decided to use the Shortcut I wrote'.

### #312 — Weekly Thing 312 / Tangled, Graphing, Starlink

- Era: Buttondown
- Overall: Issue reads cleanly overall; main concern is a missing space joining a markdown link to following text in the Wegovy section, plus minor typos.
  - **[LOW] typo** — 'affects' should be 'effects' (noun form).
    - `This article goes deeper on the affects of GLP-1 drugs`
    - Fix: Change 'affects' to 'effects'.
  - **[LOW] typo** — 'your' should be 'you're'.
    - `make sure your not resorting to coding`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] typo** — 'That fact' should be 'The fact' at the start of the sentence.
    - `That fact that code has to be structured right`
    - Fix: Change 'That fact' to 'The fact'.
  - **[MEDIUM] malformed-link** — Missing space between the closing parenthesis of the markdown link and the following word, causing 'is heating up' to run into the link.
    - `[Competition between weight-loss drugmakers](https://www.economist.com/business/2024/10/24/competition-will-make-weight-loss-drugs-better-cheaper-and-bigger)is heating up`
    - Fix: Add a space between ')' and 'is'.
  - **[LOW] narrative-break** — 'What else.' ends with a period where a question mark is expected, reading like a truncated thought.
    - `what is the outcome? People eat less sure. People buy less? Maybe. What else.`
    - Fix: Change 'What else.' to 'What else?'

### #314 — Weekly Thing 314 / Interfaces, π, Bubbles

- Era: Buttondown
- Overall: The issue reads cleanly with era-normal structure; the only minor issue is a pair of stray object-replacement characters in one Journal entry.
  - **[LOW] migration-artifact** — Two U+FFFC object-replacement characters appear before the emoji, likely leftover from a copy/paste of an inline image or attachment.
    - `As Tammy reflected, some things never change! ￼￼😁`
    - Fix: Remove the stray ￼￼ placeholder characters before the emoji.

### #315 — Weekly Thing 315 / Innovation, Yak, Calligraphr

- Era: Buttondown
- Overall: The issue is in good shape overall with era-normal Buttondown formatting; only one low-confidence potential off-by-one reference in the guestbook URL.
  - **[LOW] dangling-reference** — Issue #315 links to guestbook path /316, which may be an off-by-one reference, though it could be intentional; worth verifying.
    - `Sign the [Weekly Thing Guestbook](https://guestbooks.meadow.cafe/guestbook/316) ✍️`
    - Fix: Verify the guestbook URL points to the correct issue identifier (likely /315) or confirm the numbering scheme is intentional.

### #317 — Weekly Thing 317 / Assembly, Blogging, Cyberpunk

- Era: Buttondown
- Overall: The issue is in good shape overall; only a stale guestbook reference and a minor 'to/too' typo were noted.
  - **[LOW] dangling-reference** — The guestbook link references issue 316 but this is issue 317; likely a stale reference from the previous issue, though readers can still use the guestbook.
    - `Sign the [Weekly Thing Guestbook](https://guestbooks.meadow.cafe/guestbook/316) ✍️`
    - Fix: Update the guestbook URL to reference issue 317 (or verify the correct guestbook link for this issue).
  - **[LOW] typo** — "to much" should be "too much".
    - `I care to much about actually getting stuff done`
    - Fix: Change "to much" to "too much".

### #318 — Weekly Thing 318 / Sycophancy, Rollerblades, Yoga

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor missing-word typo in the llm-prices.com entry.
  - **[LOW] typo** — Missing word — likely 'how he is using LLMs' — renders as an ungrammatical clause.
    - `this short writeup highlights how is using LLMs to actually make the tool as well`
    - Fix: Insert 'he' so it reads 'highlights how he is using LLMs'.

### #319 — Weekly Thing 319 / Embeddings, Passkeys, Macros

- Era: Buttondown
- Overall: The issue is structurally sound and era-normal; the main concern is the large set of 404'd image URLs on files.thingelstad.com already captured by the static audit, which will degrade the Journal and cover sections for archive readers.
  - **[LOW] dangling-reference** — The guestbook link references '316' which is a prior issue number; if this is meant to be issue-specific for #319 it's stale, though it may just be a shared guestbook.
    - `Sign the [Weekly Thing Guestbook](https://guestbooks.meadow.cafe/guestbook/316) ✍️`
    - Fix: Verify whether the guestbook URL should match the current issue number or is intentionally a shared guestbook.

### #321 — Weekly Thing 321 / Saluting, Tetris, Sky

- Era: Buttondown
- Overall: Issue #321 is in good shape overall; only minor typos and one stray Unicode artifact were found, none of which break readability.
  - **[LOW] typo** — This is a quoted photo of a bumper sticker, so the 'breaks'/'brakes' spelling is intentional content (not an editorial typo) — not flagging.
    - `MY BREAKS ARE GOOD!`
    - Fix: No change; quoted verbatim from image.
  - **[LOW] migration-artifact** — The character ￼ (U+FFFC, object replacement character) is a stray artifact likely from copying from an app that embedded an inline object.
    - `Available for visitors until Labor Day. ￼🤩`
    - Fix: Remove the ￼ character before the 🤩 emoji.
  - **[LOW] typo** — 'bale' should be 'bail' in the idiom 'bail on it' — a clear spelling error.
    - `they bale on it`
    - Fix: Change 'bale' to 'bail'.
  - **[LOW] typo** — The author's name is Jenny Odell (as shown by the URL and the book's author listing), not 'Jenni'.
    - `[Jenni Odell](https://www.jennyodell.com)`
    - Fix: Change 'Jenni Odell' to 'Jenny Odell'.
  - **[LOW] narrative-break** — Stray underscores mid-blockquote appear to be a broken italics toggle, leaving visible underscores in the rendered text.
    - `does not find it in 100 runs._ _So on this benchmark`
    - Fix: Remove the stray `_ _` or properly close/open the italics markers.

### #322 — Weekly Thing 322 / Banff & Lake Louise

- Era: Buttondown
- Overall: Clean photo-essay issue with era-normal structure; only two minor grammar slips noted.
  - **[LOW] typo** — 'at the sun rises' should be 'as the sun rises'.
    - `On the shore of the Bow River at the sun rises on the snowy peaks`
    - Fix: Replace 'at' with 'as'.
  - **[LOW] typo** — 'will captures' is ungrammatical; should be 'will capture'.
    - `When you are seeking that perfect light that will captures the feeling`
    - Fix: Change 'captures' to 'capture'.

### #323 — Weekly Thing 323 / Context, Dithering, Liquid Glass

- Era: Buttondown
- Overall: The issue reads cleanly overall; the only concerns are an unrendered survey template tag and a stray object-replacement character from a lost inline attachment.
  - **[MEDIUM] migration-artifact** — This looks like an unrendered Buttondown survey template tag that may not have been substituted in the archived version.
    - `{{ survey.612poapchallengesignup }}`
    - Fix: Verify this template tag renders in the archive; if not, replace with a direct signup link or the rendered survey embed.
  - **[LOW] image-problem** — The '￼' character (U+FFFC Object Replacement Character) indicates a missing/stripped inline image or attachment from the source.
    - `Tasty but also over-the-top sweet. Also over-the-top tall! ￼`
    - Fix: Remove the stray object-replacement character or restore the intended inline image.

### #324 — Weekly Thing 324 / Agents, Shortcuts, Joy

- Era: Buttondown
- Overall: Issue is generally clean and well-formed; the only notable issue is a duplicated/malformed link after the H. Ward Miles mention in the Stone Arch Bridge Fest entry.
  - **[MEDIUM] malformed-link** — There is a duplicate/extra link immediately after the H. Ward Miles link with a trailing period in the URL, producing visible broken-looking text like '[www.hwardmiles.com.]' linking to an invalid URL ending with a period.
    - `Mazie bought a piece of art with her own money -- her very first art purchase from [H. Ward Miles](https://www.hwardmiles.com)[www.hwardmiles.com.](https://www.hwardmiles.com.)`
    - Fix: Remove the duplicate '[www.hwardmiles.com.](https://www.hwardmiles.com.)' fragment, leaving only the first properly formatted link.

### #325 — Weekly Thing 325 / Platform, Agents, Legacy

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor typos noted, and the Buttondown template conditionals render correctly.
  - **[LOW] typo** — Grammatical error — likely meant 'if you wish' or 'if you are so inclined'.
    - `Feel free to go there if you are wish.`
    - Fix: Change to 'if you wish' or similar.
  - **[LOW] typo** — 'cooyright' is a clear misspelling of 'copyright'.
    - `Important ruling for AI model training, cooyright, and fair use.`
    - Fix: Correct 'cooyright' to 'copyright'.

### #326 — Weekly Thing 326 / Tempo, Seedship, Refraction

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and a couple of stray object-replacement characters in one Journal entry.
  - **[LOW] typo** — 'site' should be 'sit' — clear typo.
    - `They all site in a [POAP Claims](https://www.thingelstad.com/categories/poap-claims/) category too.`
    - Fix: Change 'site' to 'sit'.
  - **[LOW] typo** — 'your' should be 'you're' — clear typo.
    - `If your like many, it has been a while.`
    - Fix: Change 'your' to 'you're'.
  - **[LOW] other** — The two ￼ characters are Unicode object-replacement characters, typically leftover from unrendered inline images/emoji during copy-paste.
    - `Awesome day for the 7th Annual Team SPS Kubb Tournament! Bonus for me to fulfill my wish of being a Kubb tournament director. ￼￼`
    - Fix: Remove the ￼￼ object-replacement characters or replace with intended emoji.

### #327 — Weekly Thing 327 / Prototypes, Tahoe, UTF-8

- Era: Buttondown
- Overall: Issue #327 is in good shape overall; only a few minor typos and a quote-mismatch in one H3 link title were noted.
  - **[LOW] typo** — "must" should be "most" — clear typo in context.
    - `This may be the must useful environment for widgets`
    - Fix: Change "must useful" to "most useful".
  - **[LOW] typo** — Grammatically broken phrase; likely meant "it is always running".
    - `on my Mac it is always run it`
    - Fix: Rewrite to "on my Mac it is always running".
  - **[LOW] typo** — "your" should be "you're".
    - `If your curious how the very heart of your computer works`
    - Fix: Change "If your curious" to "If you're curious".
  - **[LOW] malformed-link** — Mismatched quote characters in the link title (curly opening quote, straight closing quote) — minor but visible.
    - `### [“Hello, is this Anna?": Unpacking the Lifecycle of Pig-Butchering Scams](https://arxiv.org/pdf/2503.20821)`
    - Fix: Normalize to matching quotes (both curly or both straight).

### #328 — Weekly Thing 328 / Agents, Pulse, Vision

- Era: Buttondown
- Overall: Issue is in generally good shape; a few minor typos ('There' vs 'Their', 'CharGPT', missing article) and one orphaned quote mark are the only concerns.
  - **[LOW] typo** — 'There' should be 'Their', and 'strikes a ton of change' appears to be a malformed phrase (likely meant 'strikes a tone of change').
    - `There annual letter strikes a ton of change.`
    - Fix: Change to 'Their annual letter strikes a tone of change.'
  - **[LOW] typo** — 'CharGPT' is a typo for 'ChatGPT'.
    - `I just got my first [CharGPT Pulse]`
    - Fix: Change 'CharGPT' to 'ChatGPT'.
  - **[LOW] narrative-break** — Orphaned closing quote — the blockquote has a trailing double-quote with no matching opening quote.
    - `The model could already do this, but there wasn't a product built around this capability!"`
    - Fix: Remove the stray trailing double-quote at the end of the blockquote.
  - **[LOW] typo** — Missing article — should read 'it is a great app'.
    - `and it is great app to host various LLM models`
    - Fix: Insert 'a' before 'great app'.

### #329 — Weekly Thing 329 / Another Thing

- Era: Buttondown
- Overall: The issue is in good shape overall with only a few minor typos; no narrative breaks, dangling references, or migration artifacts detected.
  - **[LOW] typo** — 'LIttle' has an incorrect capitalization (capital I instead of lowercase).
    - `A Redundant Array of [LIttle Free Libraries](https://littlefreelibrary.org)`
    - Fix: Change 'LIttle' to 'Little'.
  - **[LOW] typo** — Double colon appears to be an accidental typo.
    - `Some observations::`
    - Fix: Replace '::' with a single ':'.
  - **[LOW] typo** — 'Analtyics' is a misspelling of 'Analytics'.
    - `[Plausible Analtyics 2](https://github.com/jthingelstad/microdotblog-plausible)`
    - Fix: Correct 'Analtyics' to 'Analytics'.

### #330 — Weekly Thing 330 / Music, Intervals, Nanochat

- Era: Buttondown
- Overall: Issue is in good shape overall; only minor typos and a couple of missing separators in H3 link titles were found.
  - **[LOW] typo** — The H3 title appears to be missing a separator (likely a dash or pipe) between 'plugins' and 'Anthropic', similar to other titles in the issue that use ' - ' or ' | '.
    - `Customize Claude Code with plugins Anthropic`
    - Fix: Change to 'Customize Claude Code with plugins - Anthropic' for consistency with other link titles.
  - **[LOW] typo** — Missing separator between 'size' and 'Anthropic' — inconsistent with the site/publication style that uses ' - ' or ' | ' before the source.
    - `A small number of samples can poison LLMs of any size Anthropic`
    - Fix: Change to 'A small number of samples can poison LLMs of any size - Anthropic'.
  - **[LOW] typo** — Grammatical error: 'have went' should be 'went' or 'have gone'.
    - `Tammy and I have went to the`
    - Fix: Replace 'have went' with 'went'.
  - **[LOW] typo** — 'get his' is a typo for 'get hit'.
    - `Note, it hurts to get his with a frisbee in the head.`
    - Fix: Change 'get his' to 'get hit'.
  - **[LOW] typo** — 'cut did' appears to be a leftover word fragment from editing — likely should be just 'did'.
    - `I cut did a lot of early work using Subversion`
    - Fix: Remove 'cut' so it reads 'I did a lot of early work...'.

### #331 — Weekly Thing 331 / RFC, Security, Tokens

- Era: Buttondown
- Overall: Issue is in reasonable shape overall, but contains several small prose errors (duplicated 'are are', 'by baseline' for 'my baseline', 'a programming' for 'a programmer', and a malformed sentence about Torres) worth a quick copyedit.
  - **[LOW] typo** — Duplicated word 'are are' — the link text starts with 'are' immediately after the word 'are'.
    - `Simon Willison says they are [are awesome, maybe a bigger deal than MCP](https://simonwillison.net/2025/Oct/16/claude-skills/)`
    - Fix: Remove one of the duplicate 'are' words so it reads 'Simon Willison says they are [awesome, maybe a bigger deal than MCP]'.
  - **[LOW] typo** — Sentence appears to have a missing word (likely 'coding' or 'required'), making it ungrammatical.
    - `a CTO should not be for their job`
    - Fix: Restore the missing word, e.g., 'a CTO should not be coding for their job'.
  - **[LOW] typo** — 'a programming' should be 'a programmer'.
    - `if you are not a programming but curious`
    - Fix: Change 'a programming' to 'a programmer'.
  - **[LOW] typo** — 'by baseline' should be 'my baseline'.
    - `I've lowered by baseline from 90 to closer to 70`
    - Fix: Change 'by baseline' to 'my baseline'.
  - **[LOW] narrative-break** — Sentence appears malformed — 'doesn't extend that' doesn't parse; likely missing a word such as 'mention' or 'note'.
    - `she doesn't extend that doing the work the way she describes also has many other versions like sharing and version control.`
    - Fix: Rework the sentence, e.g., 'she doesn't mention that doing the work the way she describes also has many other benefits like sharing and version control.'
  - **[LOW] malformed-link** — Orphan closing quote after 'comments' with no matching opening quote, suggesting dropped markup.
    - `[RFC](https://www.ietf.org/process/rfcs/), or request for comments", were documents`
    - Fix: Add the missing opening quote before 'request' or remove the stray closing quote.

### #333 — Weekly Thing 333 / Gemini, LangChain, Illusion

- Era: Buttondown
- Overall: Issue #333 is in generally good shape and reads cleanly; the main concerns are a handful of minor typos ("how much fine", "frustrating banal", "The is", "to by", "totally 22 sold").
  - **[LOW] typo** — "how much fine" should be "how much fun" — clear typo.
    - `I was telling some friends how much fine I’m having playing with Agent stuff`
    - Fix: Change "how much fine" to "how much fun".
  - **[LOW] typo** — "frustrating banal" should be "frustratingly banal" — missing adverb ending.
    - `the cause was frustrating banal.`
    - Fix: Change to "frustratingly banal".
  - **[LOW] typo** — "The is" should be "This is" — clear typo.
    - `The is the closest clustering of amounts`
    - Fix: Change "The is" to "This is".
  - **[LOW] typo** — "to by" should be "to buy" — clear typo.
    - `You can see folks tend to by in pairs`
    - Fix: Change "by" to "buy".
  - **[LOW] typo** — "totally 22 sold" should be "totaling 22 sold".
    - `get more made the week after the sale -- totally 22 sold.`
    - Fix: Change "totally" to "totaling".
  - **[LOW] typo** — Filename contains misspelling "annaul" instead of "annual" — likely just a filename typo but worth noting; image appears to load fine so low severity.
    - `![A bar graph displays the annual fundraising totals for Things 4 Good Fall Fundraiser from 2021 to 2025, showing a gradual increase each year, reaching $9,048 in 2025.](https://files.thingelstad.com/weekly-thing/333/journal/t4g-annaul-sum.png)`
    - Fix: Verify the image URL is correct; if so, no action needed (cosmetic filename issue).

### #334 — Weekly Thing 334 / Privacy, Shopping, Consciousness

- Era: Buttondown
- Overall: The issue is in good shape overall with only minor typos and one awkward link title.
  - **[LOW] typo** — "does anywhere" appears to be a typo for "goes anywhere".
    - `I'm dubious this stuff does anywhere but I applaud the attempt`
    - Fix: Change "does anywhere" to "goes anywhere".
  - **[LOW] typo** — "though" should be "thought".
    - `I hadn't though that much about this but found this an interesting read.`
    - Fix: Change "hadn't though" to "hadn't thought".
  - **[LOW] typo** — Appears to be a garbled abbreviation (likely intended "etc.") inside the quoted block.
    - `eg.c)`
    - Fix: If quoting verbatim, consider [sic]; otherwise correct to "etc.".
  - **[LOW] malformed-link** — The link title reads awkwardly — likely missing a separator like "|" between "Platform" and "Anthropic".
    - `**[Introducing advanced tool use on the Claude Developer Platform Anthropic](https://www.anthropic.com/engineering/advanced-tool-use)**`
    - Fix: Change to "Claude Developer Platform | Anthropic".

### #335 — Weekly Thing 335 / Complexity, Fizzy, Soul

- Era: Buttondown
- Overall: The issue is in good shape overall; only minor wording issues were noted and no migration artifacts or structural problems were found.
  - **[LOW] typo** — This sentence appears to be the opposite of the intended meaning; likely should read 'make sure it is enough' given the surrounding context about having sufficient context.
    - `You then have to make sure it isn't enough.`
    - Fix: Change 'isn't enough' to 'is enough'.
  - **[LOW] typo** — 'which as a Python program' is ungrammatical; should be 'which is a Python program'.
    - `[runprompt](https://github.com/chr15m/runprompt) which as a Python program`
    - Fix: Replace 'which as' with 'which is'.

### #336 — Weekly Thing 336 / Culture, Retention, Transmission

- Era: Buttondown
- Overall: Clean issue with era-normal structure; only one minor typo found.
  - **[LOW] typo** — 'developmetn' is a clear typo for 'development'.
    - `Is agentic developmetn just a new abstraction?`
    - Fix: Change 'developmetn' to 'development'.

### #337 — Weekly Thing 337 / Sunrise, Vision, Offline

- Era: Buttondown
- Overall: Issue is in good shape overall; only two minor spelling inconsistencies in the escape rooms list.
  - **[LOW] typo** — 'St. Pual' is an obvious misspelling of 'St. Paul' (other entries in the same list spell it correctly).
    - `The Hospital in St. Pual, MN`
    - Fix: Change 'St. Pual' to 'St. Paul'.
  - **[LOW] typo** — 'Cabinet Mysterlis' is inconsistent with the other two adjacent entries spelled 'Cabinet Mysteriis' (and the URL confirms the correct spelling).
    - `**[Cabinet Mysterlis](https://cabinetmysteriis.ca/en/)** - Screaming Metal`
    - Fix: Change 'Cabinet Mysterlis' to 'Cabinet Mysteriis'.

### #338 — Weekly Thing 338 / Authority, Humanizer, Left

- Era: Buttondown
- Overall: Issue is largely clean, but contains an unrendered Buttondown template tag for the straw poll that will show literally in the archive, plus a minor typo and a likely missing separator in one H3 title.
  - **[HIGH] migration-artifact** — This is an unrendered template placeholder that will appear literally to readers of the archive.
    - `{{ survey.strawpoll338 }}`
    - Fix: Replace with the actual poll embed/content or remove the placeholder before archiving.
  - **[MEDIUM] malformed-link** — The title appears to be missing a separator (likely a pipe) between 'constitution' and 'Anthropic', suggesting a formatting error.
    - `### [Claude's new constitution Anthropic](https://www.anthropic.com/news/claude-new-constitution)`
    - Fix: Change to 'Claude's new constitution | Anthropic' to match the site's title convention.
  - **[LOW] typo** — 'kindapped' is a misspelling of 'kidnapped'.
    - `head coach [Adrian Heath](https://en.wikipedia.org/wiki/Adrian_Heath) being kindapped!`
    - Fix: Change 'kindapped' to 'kidnapped'.

### #339 — Weekly Thing 339 / OpenClaw, Isometric, Prism

- Era: Buttondown
- Overall: Issue #339 is in good shape overall; only two minor prose typos were noted and nothing structural is broken.
  - **[LOW] typo** — 'on thing' should be 'one thing' — a clear typo.
    - `The act of consuming on thing to create another`
    - Fix: Change 'on thing' to 'one thing'.
  - **[LOW] typo** — 'in they believed' appears to be a typo for 'and they believed' or 'what they believed'.
    - `The visionaries were in pursuit of a different, in they believed better, world.`
    - Fix: Rewrite to 'a different, and they believed better, world' or similar.

### #340 — Weekly Thing 340 / Moltbook, Frontier, Poster

- Era: Buttondown
- Overall: Issue is in good shape overall with era-normal Buttondown structure; only a single minor typo noted.
  - **[LOW] typo** — 'how knows' should be 'who knows' — a clear word-substitution typo.
    - `And how knows where this goes.`
    - Fix: Change 'how knows' to 'who knows'.

### #341 — Weekly Thing 341 / Minions, MAX, ReMemory

- Era: Buttondown
- Overall: Issue is mostly clean, but a duplicated pull-quote under the Stripe Minions entry is a clear migration/copy-paste error that a reader would notice, plus a minor duplicated word in a heading.
  - **[HIGH] other** — The pull quote under the Stripe Minions entry is the same Excel quote used earlier in the Om Malik entry; it doesn't relate to Stripe's coding agents and appears to be a copy-paste error.
    - `### [Minions: Stripe’s one-shot, end-to-end coding agents | Stripe Dot Dev Blog](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)

Super interesting read about how Stripe is building agentic capabilities for their development teams.

> There was no need to remake the platform (Excel) or write any custom code. I didn’t have to learn yet another tool. I didn’t need to change Excel.`
    - Fix: Replace the duplicated Excel quote with an appropriate quote from the Stripe Minions article, or remove the blockquote.
  - **[LOW] typo** — The link title contains 'Anthropic Anthropic' — the word is duplicated in the headline.
    - `### [Claude is a space to think | Anthropic Anthropic](https://www.anthropic.com/news/claude-is-a-space-to-think)`
    - Fix: Remove the duplicated 'Anthropic' from the H3 title.

### #342 — Weekly Thing 342 / Claude, Otto, Elixir

- Era: Buttondown
- Overall: The issue is well-structured and readable; only minor typos ('role' vs 'roll', 'scape', 'asing', 'there/their', a missing 'go') merit attention.
  - **[LOW] typo** — 'how I role' should be 'how I roll' — a clear homophone typo.
    - `We needed a website for our clan because that is how I role`
    - Fix: Change 'how I role' to 'how I roll'.
  - **[LOW] typo** — 'scape rooms' is missing the 'e' — should be 'escape rooms'.
    - `We love to do scape rooms`
    - Fix: Change 'scape rooms' to 'escape rooms'.
  - **[LOW] typo** — 'asing' is a typo for 'asking'.
    - `asing Claude Code in the Cloud`
    - Fix: Change 'asing' to 'asking'.
  - **[LOW] typo** — 'there' should be 'their' — possessive is required.
    - `I could click on an individual and see there claims!`
    - Fix: Change 'there claims' to 'their claims'.
  - **[LOW] typo** — 'your' should be 'you're'. This appears in a quoted journal post title/text.
    - `If your reading my blog`
    - Fix: If editorial, change to "you're"; otherwise leave as-is since it's a quoted journal entry.
  - **[LOW] narrative-break** — Sentence is phrased as a question but ends with a period, creating a minor narrative inconsistency.
    - `could I build this whole website from my phone while laying in bed.`
    - Fix: Replace the terminal period with a question mark.
  - **[LOW] typo** — Missing verb — likely 'I'm going to go on a walk'.
    - `I’m going to on a walk for at least an hour.`
    - Fix: Insert 'go' before 'on a walk'.

### #343 — Weekly Thing 343 / Commune, Chaos, Renaissance

- Era: Buttondown
- Overall: Issue is generally in good shape with era-normal Buttondown structure; main concerns are a missing https:// on one diff link and a couple of minor typos.
  - **[LOW] typo** — 'what your reading' should be 'what you're reading', and 'agnatically' appears to be a typo for 'agentically'.
    - `ask yourself how you know that half of what your reading on any social network isn't agnatically generated.`
    - Fix: Change to 'what you're reading' and 'agentically generated'.
  - **[MEDIUM] malformed-link** — The diff link URL is missing the https:// protocol, which will cause it to be treated as a relative link and break.
    - `([diff](github.com/jthingelstad/elixir-bot/compare/2f4c31ff72a330e1d9a2b86bc1028704d7ce97d2...bf4570c4f5820e4403d4731d48be20f38fa95298))`
    - Fix: Prefix the URL with https:// so it resolves correctly.
  - **[LOW] typo** — Awkward/broken sentence construction ('set for it was pleasant') suggests a missing word, and 'whisps' should be 'wisps'.
    - `And incredibly predictably when our original departure time was set for it was pleasant with little whisps of snow.`
    - Fix: Rephrase for clarity and correct 'whisps' to 'wisps'.

### #344 — Weekly Thing 344 / Mythos, Artemis, Signals

- Era: Buttondown
- Overall: Issue is in good shape overall; only a minor typo ("agnatically") and one sentence fragment were noted.
  - **[LOW] typo** — "agnatically" is a misspelling of "agentically" in context about agentic transformation.
    - `However, to agnatically transform something`
    - Fix: Change "agnatically" to "agentically".
  - **[LOW] narrative-break** — This is a sentence fragment lacking a verb (e.g., "is from a weekend in the Azores").
    - `Her most recent update from a weekend in the Azores.`
    - Fix: Rewrite as a complete sentence such as "Her most recent update is from a weekend in the Azores."

## Clean issues (23)

#6, #7, #132, #137, #146, #149, #172, #174, #177, #182, #199, #200, #209, #219, #238, #242, #270, #307, #310, #313, #316, #320, #332
