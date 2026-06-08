# Thingy Roadmap

Thingy is the authenticated archive agent for Jamie Thingelstad's public work. It answers from the published corpus only: The Weekly Thing, thingelstad.com, and Another Thing. The product direction is to make that archive feel alive, explorable, and trustworthy without turning Thingy into a general-purpose assistant.

## Recently Completed

- **Three-source corpus**: Weekly Thing, blog, and podcast corpora are first-class API sources with source selectors in the web UI.
- **Richer link graph**: linked domains, internal links, resolved blog-to-blog links, and cross-source links are indexed as separate signals.
- **Freshness pipeline**: external blog and podcast sync jobs feed Studio before corpus rebuild/upload, so new source content can reach the API through CI/CD.
- **Chat-native Thingy UI**: thingy.thingelstad.com moved from a publication-style page to a chat-client experience with a conversation rail, mobile drawer, floating input, visible archive work, rich markdown, tables, copy/share, and curiosity maps.
- **Server-side conversations**: authenticated conversations, turns, tool traces, citations, feedback, artifacts, and evaluator metadata now live in DynamoDB. The client no longer owns history as local-only state.
- **Magic-link authentication**: subscriber login now proves inbox access with Fastmail JMAP magic-link email from `thingy@thingelstad.com`.
- **Conversation modes**: Thingy supports four permissioned modes:
  - `thingy`: default archive agent for readers.
  - `research_guide`: deeper timelines, reading paths, and synthesis for supporting members.
  - `thought_partner`: owner-only mode for Jamie to challenge and refine ideas against the public archive.
  - `trusted_circle`: warmer close-reader mode for explicitly invited people.
- **User profile and memory**: Thingy can remember explicitly offered reader preferences, names, and archive interests across conversations.
- **Agentic welcome**: Thingy can generate contextual welcomes from local time, profile, previous conversations, and entitlements instead of relying on static starter prompts.
- **Archive tools**: the agent has deterministic and exploratory tools for corpus stats, latest content, yearly signals, archive lens, entity lens, source neighborhoods, claim checks, archive gems, link/domain questions, and source inventory.
- **Curiosity map**: Thingy can draw and store an exploratory map from the archive, with rail-triggered maps starting new conversations and input-triggered maps staying in the current one.
- **Operator eval loop**: a DynamoDB Stream eval Lambda reviews updated conversations out of band, writes quality metadata back to the canonical conversation rows, and posts compact webhook cards to Discord.
- **Operator report**: local static HTML report generation gives conversation-grounded review with filters, eval metadata, feedback, tool traces, and Jamie-vs-reader labeling.

## Current Product Shape

Thingy should feel like an agent inside a bounded archive. It can be proactive, suggest paths, connect themes, remember reader preferences, and challenge ideas in the right mode. It should not invent outside facts, browse the live web, or imply private knowledge beyond what the user explicitly provides and what exists in the public corpus.

The main product bets now are:

- **Trust through visible work**: show archive tools and source grounding without making the conversation noisy.
- **Delight through exploration**: use curiosity maps, archive gems, source neighborhoods, and trails to make the archive feel discoverable.
- **Personal continuity**: remember what a returning authenticated user has explored, while keeping memory explicit and conservative.
- **Mode-aware posture**: make the same corpus feel different for a casual reader, a supporting member doing research, Jamie thinking out loud, or a close friend.

## Near-Term Direction

- **Mode rollout and permissions**: finish the operational path for granting Trusted Circle access through Buttondown tags and make the operator report clearly surface mode usage.
- **Better operator dashboard**: keep Discord webhooks as notifications, but move deeper review to a local/web operator interface grounded in server-side conversations.
- **Corpus freshness observability**: make it obvious when the API corpus was last built from each source and whether new blog/podcast content has landed.
- **Citation discipline**: keep improving evaluator checks for citation-footer mismatches, retrospective evidence mislabeled as contemporaneous, and title-only recommendations.
- **Runtime resilience**: continue improving timeout handling, partial-answer handling, and evaluator interpretation of runtime exhaustion.
- **Browser QA discipline**: keep mobile/tablet/desktop interaction tests for rail, mode selection, conversations, curiosity maps, source picker, and input controls.

## Ideas Under Consideration

- **Published life timeline pages**: if Jamie publishes timeline-style pages on thingelstad.com, pull them into the public corpus as normal blog/page content rather than building a hidden private corpus.
- **Authenticated operator UI**: after stronger owner auth exists for admin surfaces, replace the local static report with a real operator dashboard. Treat this carefully because it increases attack surface.
- **Deeper feedback loop**: let downvote comments and eval notes become a structured improvement queue, not just passive metadata.
- **Conversation export/share**: offer a clean way to share or archive a conversation while preserving citations and artifacts.
- **Corpus coverage dashboard**: show source counts, freshness, link graph health, missing transcript/post metadata, and source-specific search quality checks.

## Principles

- Keep Thingy grounded in the published corpus.
- Prefer durable source metadata over prompt cleverness.
- Make the agent capable, but keep the boundary legible.
- Use server-side conversations as the canonical record.
- Make operator review asynchronous; Discord should never be in the user request path.
- Avoid hidden private corpora unless the product direction changes explicitly.
