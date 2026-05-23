# Reference

Durable, operational/technical reference — the stuff you reach for while *building or debugging*
the systems behind The Weekly Thing. Distinct from [`docs/`](../docs/README.md), which is the
canonical editorial spec for *how the newsletter itself works*, and from [`notes/`](../notes/README.md),
which is point-in-time project history.

| Doc | What it covers |
|---|---|
| [`librarian.md`](librarian.md) | Thingy / Archive Librarian — local corpus build, AWS runtime, Bedrock embeddings, deploy, observability. (The reader-facing *role* + voice lives in [`docs/agents/thingy.md`](../docs/agents/thingy.md).) |
| [`systems/`](systems/README.md) | Third-party integration gotchas — Buttondown, Pinboard, Stripe, Tinylytics: auth quirks, identifier confusions, endpoint catalogs, hard limits. |

If you're re-deriving an integration fact from cURL probes, the relevant page here needs an update.
