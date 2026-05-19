---
buttondown_id: em_73cwkxbtmv9p8a9r92mk508g0g
number: 347
subject: Weekly Thing 347 / Scrum, FilamentHound, DO_NOT_TRACK
publish_date: '2026-05-10T12:00:00Z'
slug: '347'
description: Claude personal guidance, Redis array type, watchOS maps, AI company learning, Agentic Coding, workplace productivity, Death of Scrum.
image: https://files.thingelstad.com/weekly-thing/347/cover.jpg
absolute_url: https://buttondown.com/weekly-thing/archive/347/
domains:
- antirez.com
- aws.amazon.com
- david-smith.org
- death-of-scrum.net
- donottrack.sh
- ens.domains
- filamenthound.com
- franktisellano.github.io
- larsfaye.com
- nooneshappy.com
- pyinfra.com
- sethmlarson.dev
- www.anthropic.com
- www.derekthompson.org
- www.robert-glaser.de
- www.theverge.com
links:
- text: 'Redis array type: short story of a long development - <antirez>'
  url: https://antirez.com/news/164
  domain: antirez.com
  heading_context: '[Redis array type: short story of a long development - <antirez>](https://antirez.com/news/164)'
  section: Notable
- text: When everyone has AI and the company still learns nothing
  url: https://www.robert-glaser.de/when-everyone-has-ai-and-the-company-still-learns-nothing/
  domain: www.robert-glaser.de
  heading_context: '[When everyone has AI and the company still learns nothing](https://www.robert-glaser.de/when-everyone-has-ai-and-the-company-still-learns-nothing/)'
  section: Notable
- text: Agentic Coding is a Trap | Lars Faye
  url: https://larsfaye.com/articles/agentic-coding-is-a-trap
  domain: larsfaye.com
  heading_context: '[Agentic Coding is a Trap | Lars Faye](https://larsfaye.com/articles/agentic-coding-is-a-trap)'
  section: Notable
- text: Appearing Productive in The Workplace — No One's Happy
  url: https://nooneshappy.com/article/appearing-productive-in-the-workplace/
  domain: nooneshappy.com
  heading_context: '[Appearing Productive in The Workplace — No One''s Happy](https://nooneshappy.com/article/appearing-productive-in-the-workplace/)'
  section: Notable
- text: Six Years Perfecting Maps on watchOS - David Smith, Independent iOS Developer
  url: https://david-smith.org/blog/2026/04/29/maps-on-watchos/
  domain: david-smith.org
  heading_context: '[Six Years Perfecting Maps on watchOS - David Smith, Independent iOS Developer](https://david-smith.org/blog/2026/04/29/maps-on-watchos/)'
  section: Notable
- text: How people ask Claude for personal guidance — Anthropic
  url: https://www.anthropic.com/research/claude-personal-guidance
  domain: www.anthropic.com
  heading_context: '[How people ask Claude for personal guidance — Anthropic](https://www.anthropic.com/research/claude-personal-guidance)'
  section: Notable
- text: The Death of Scrum — An Interactive Essay
  url: https://death-of-scrum.net/
  domain: death-of-scrum.net
  heading_context: '[The Death of Scrum — An Interactive Essay](https://death-of-scrum.net/)'
  section: Notable
- text: Datatype — variable font that turns text into charts
  url: https://franktisellano.github.io/datatype/
  domain: franktisellano.github.io
  heading_context: null
  section: Briefly
- text: Hand‑drawn QR codes — Seth Larson
  url: https://sethmlarson.dev/hand-drawn-qr-codes
  domain: sethmlarson.dev
  heading_context: null
  section: Briefly
- text: FilamentHound — Best Prices on 3D Printing Filament
  url: https://filamenthound.com/
  domain: filamenthound.com
  heading_context: null
  section: Briefly
- text: pyinfra - Fast Python Infrastructure Automation & Configuration Management Tool
  url: https://pyinfra.com/
  domain: pyinfra.com
  heading_context: null
  section: Briefly
- text: The AWS MCP Server is now generally available | AWS News Blog
  url: https://aws.amazon.com/blogs/aws/the-aws-mcp-server-is-now-generally-available/
  domain: aws.amazon.com
  heading_context: null
  section: Briefly
- text: Names Are No Longer Single Objects | ENS Blog
  url: https://ens.domains/blog/post/names-are-no-longer-single-objects
  domain: ens.domains
  heading_context: null
  section: Briefly
- text: DO_NOT_TRACK
  url: https://donottrack.sh/
  domain: donottrack.sh
  heading_context: null
  section: Briefly
- text: How American Dads Became the Parents Their Fathers Never Were
  url: https://www.derekthompson.org/p/why-do-richer-dads-spend-more-time
  domain: www.derekthompson.org
  heading_context: null
  section: Briefly
- text: Meta lost 20 million users last quarter | The Verge
  url: https://www.theverge.com/tech/921089/meta-earnings-q1-2026-user-decline-ai-investments
  domain: www.theverge.com
  heading_context: null
  section: Briefly
word_count: 4530
---
Hello there!

On May 13th it will be the nine year anniversary of me sending these emails. Two years ago I introduced the Supporting Membership program and I love the fact that we can do some good together! I just sent a contribution of

**$1,164.92**

to the Electronic Frontier Foundation with the proceeds from the last year! 👏

![](https://files.thingelstad.com/weekly-thing/347/eff-donation.png)

This includes all membership as well as sales of the [Yearly Thing book](https://www.thingelstad.com/2026/01/20/i-made-a-book-yearly.html)!

That also means we have raised…

**$1,792.37**

in total through this program!

Amazing. Thank you! By the way, check out the [Supporting Members](https://weekly.thingelstad.com/members/) section of the website for more information and a super streamlined way to become a member.

Don't want a recurring charge but you do want to be part of giving back? The [members page](https://weekly.thingelstad.com/members/) now has a place where you can make a **one-time contribution** into the Supporting Members program. Cool huh?

Next week I'll share more about the non-profit we are supporting for the 9th year. Stay tuned!

Sometimes these emails get long, and this one certainly did. Don't skip the blog posts for the new Weekly Thing website and my Your Version Number project! Or just skip the blog posts and go right to them…

➡️ [Weekly Thing](https://weekly.thingelstad.com)

➡️ [Your Version Number](https://yourversionnumber.com)

---

![](https://files.thingelstad.com/weekly-thing/347/cover.jpg)

[Minnebar](https://minnestar.org/minnebar/) t-shirt collection from 20 years of barcamps!

May 02, 2026
Best Buy HQ, Richfield, Minnesota

---

## New Weekly Thing Website

I've commented that agentic coding makes things that were previously on your "list of impossible projects" into things that you can do. I have long had on my "impossible project" list the desire to create a website for the Weekly Thing that let the archive shine in ways that I knew were possible but no solution out there delivered. With 9 years of writing and 345 issues in the archive there is so much to surface.

To do this I knew I would need to build it on my own. I could use the Buttondown API to get the issues and make them accessible. But then I needed a website. I needed a content pipeline. Oh, and that archive has old formats from different platforms that were a mangled mess of HTML.

This was truly on the "impossible list" for me personally. If I wanted to spend tens-of-thousands of dollars, or probably even more, I maybe could have hired someone to build it. A laughable idea really.

So I decided to take my experiences with Claude Code, Claude Design, and Codex and point it at this problem. Over the last couple of weeks I've been working on the new Weekly Thing website experience.

I just have to say I'm so thrilled with the results that I can barely handle it. Rather than type a novel here I'm just going to list out what the site has. Even better, go there and explore:

[**https://weekly.thingelstad.com**](https://weekly.thingelstad.com/)

Here is what the new site has!

1️⃣ Completely reimagined **landing page to describe the Weekly Thing**. Gone is the basic Buttondown paragraph of text and a signup button. The home page hopefully gives a much better feel for what the Weekly Thing is.

2️⃣ [**Archive**](https://weekly.thingelstad.com/archive/) page has full index of every issue back to number 1. This is also now optimized for the Weekly Thing with issue images, link counts, organized by year.

3️⃣ **[Thingy](https://weekly.thingelstad.com/thingy/), the Weekly Thing librarian** that has read every issue of the Weekly Thing and is ready to converse with you about all of it. I have wanted to make an agent like this for over a year and it is finally real. I've found this fascinating to play with and ask questions of.

You will see this feature requires you to provide your subscriber email address. It is only available to confirmed subscribers of the Weekly Thing.

You may recall in [WT311](https://weekly.thingelstad.com/archive/311/) I shared a custom GPT that was sort of like this. That was grade school level. Thingy is much smarter!

Some prompts that are fun to explore with Thingy:

- [How has the arc of AI evolved in the Weekly Thing?](https://weekly.thingelstad.com/thingy/?prompt=How+has+the+arc+of+AI+evolved+in+the+Weekly+Thing%3F)
- [Compare Tik Tok, Facebook, and X from the archive.](https://weekly.thingelstad.com/thingy/?prompt=Compare+Tik+Tok%2C+Facebook%2C+and+X+from+the+archive.)
- [Explain to me how Jamie connects Indie Web and Crypto? They seem very opposite to me.](https://weekly.thingelstad.com/thingy/?prompt=Explain+to+me+how+Jamie+connects+Indie+Web+and+Crypto%3F+They+seem+very+opposite+to+me.)

4️⃣ **[Search](https://weekly.thingelstad.com/search/) is now super powered.** The searching is indexed into the section of the weekly thing. This works way better than before.

5️⃣ On the page for each issue you will see that there is a **Table of Contents** on the left. It is a little thing, but another example of something I've wanted for a long time. The Weekly Thing is long and this gives a way to navigate. Also, each of those items is a hyperlink so you can now send a link to a specific notable link in a specific issue.

6️⃣ Big one – **you can now LISTEN to the Weekly Thing**. I've filled this in for the last 10 issues. On the issue page there is a "Listen" button where it will be read for you.

7️⃣ **Podcast?** Well if I have an audio file for each issue why not bundle that into a podcast. So I did. You should be able to find the Weekly Thing on [Apple Podcasts](https://podcasts.apple.com/us/podcast/weekly-thing/id1895865769) and [Spotify](https://open.spotify.com/show/43A9fytZDKaZhrkp3qbukh). It is propagating through other platforms. Should be on [Overcast](https://overcast.fm/itunes1895865769/weekly-thing) too.

8️⃣ **Support for LLMs.txt!** This is a bit hidden, but if you want to talk with the LLM of your choice about the Weekly Thing, give the LLM this link:

<https://weekly.thingelstad.com/llms.txt>

That provides an LLM optimized index of the entire 345 issues, as well as links to LLM optimized versions of every email! This means ChatGPT or Claude or whatever else can dive deep into the content. I have actually used this myself when asking a model to do some research with me.

A quick note about the audio:

- This doesn't replace or remove my actual podcast, [Another Thing](https://another.thingelstad.com/). There is still just one episode there but I'm not giving up on that.
- The audio for the Weekly Thing is text-to-speech using a transformed version of the email text. It announces sections, gives links numbers, announces quotes, and cuts some sections. I've listened to a few and think it works reasonably well.
- I'll probably evolve the generated audio, and right now it only exists for the last 10 issues, but I plan to backfill all issues with audio over time.

Take a look. Try out the archive, search, Thingy. Listen to an issue. And let me know what you think… anything not work right? Read wrong? Something missing? Or just that you think it is all cool?

---

## Your Version Number

In 2018 I wrote about [Your Version Number](https://www.thingelstad.com/2018/02/24/your-version-number.html):

> I think the version metaphor works. You are a different person in your 20s, 30s, 40s and so on. Your life changes in meaningful ways! MAJOR version! Each year we tend to think of new things and new goals, but we don't break backwards compatibility. MINOR version! And I think most people try to make each day a bit better than the last. PATCH level!

I've had a [shortcut that shows my version](https://www.thingelstad.com/2025/02/25/jamie.html) on my phone for the last year. And now I decided to make this a fun website!

Now available…

### [Your Version Number](https://yourversionnumber.com/)

[![](https://files.thingelstad.com/weekly-thing/347/journal/your-version-number.png)](https://yourversionnumber.com/)

Super simple single-page app that allows you to add one or more birthdays and see the version number. The magic here is all the data is held in the URL so you can bookmark, set as your homepage, or share with others. And sure it is fun seeing you and your friends daily versions, but it is even more fun with all the custom themes!

- `dark` -- Minimalist dark mode with violet accents.
- `family` -- Warm cream + handwritten Caveat, family-album feel.
- `pastel` -- Soft gradient haze with pastel cards.
- `birthday` -- Confetti, balloons, and party-hat pink.
- `nature` -- Scattered leaves on linen, earthy serif.
- `ocean` -- Wavy gradients with a tiny shoreline wave.
- `galaxy` -- Deep-space gradient with neon numerals.
- `zen` -- Quiet cream with a vermillion first-letter.
- `weather` -- Sky-blue card with a sun/cloud per row.
- `polaroid` -- Taped Polaroid grid with a slight tilt.
- `tarot` -- Purple stars and Fool / Priestess / Empress cards.
- `newspaper` -- Broadsheet typography with section rules.
- `subway` -- Black NYC subway map with route bullets.
- `receipt` -- Thermal-printer monospace with QTY 1.
- `steampunk` -- Sepia gear-and-cog ledger.
- `brutalist` -- Yellow + red + black, oversized type.
- `comic` -- Comic panels with POW / ZAP / BOOM stickers.
- `memphis` -- 80s squiggles, triangles, and dots.
- `vinyl` -- Spinning 33⅓ records.
- `terminal` -- Green-on-black CLI prompt.
- `arcade` -- Pixel-fonted hi-score CRT cabinet.
- `vaporwave` -- Pink/cyan grid with a palm-tree sunset.
- `y2k` -- Frosted-glass chrome and blur.
- `pixel` -- Eight-bit pixel font on a dark green field.
- `gameboy` -- Classic GB DMG palette and cart silhouette.

Wait though, there is more.

### [Your Version Number: Work Edition](https://yourversionnumber.com/work/)

[![](https://files.thingelstad.com/weekly-thing/347/journal/your-version-number-work.png)](https://yourversionnumber.com/work/)

I decided to bring the same version number semantics to your job! Here we have YEARS.QUARTERS.BUSINESS_DAYS! Add your whole team in and share the URL with everyone.

And of course the Work Edition has work themes!

- `boardroom` -- Board-update slide with KPI rail (ARR, NPS, payback).
- `slack` -- Slack channel feed with reactions and avatars.
- `slidedeck` -- Confidential business-review slide with three bullets.
- `earnings` -- Live stock-ticker on a black trading screen.
- `github` -- GitHub PR list with avatars, labels, and the Open pill.
- `whiteboard` -- Sticky-note grid in primary colors.
- `inbox` -- Gmail-style inbox with subject lines and senders.
- `okr` -- Q-scorecard with progress bar and ON-TRACK pill.
- `cubicle` -- Manila-folder corporate newsletter.
- `kanban` -- Jira-style cards in an In-Progress column.
- `standup` -- Daily-standup card with Yesterday / Today / Blockers.
- `invite` -- Calendar invite with Accepted check.
- `confluence` -- Wiki page with breadcrumbs and comment counts.
- `zoom` -- Gallery-view tiles with reactions.
- `spreadsheet` -- Excel grid with row numbers.
- `pomodoro` -- Tomato-timer Deep Work card.
- `ooo` -- Out-of-office auto-reply with handwritten signature.

A fun little project made possible with Claude Code and I. 🤩

---

## Notable

_You can discuss any of these links at the [Weekly Thing 347 tag in r/WeeklyThing](https://www.reddit.com/r/weeklything/?f=flair_name%3A%22Weekly%20Thing%20347%22)._

### [Redis array type: short story of a long development - <antirez>](https://antirez.com/news/164)

I love that antirez (author of Redis) is sharing so much about his use of agentic coding. We need more stories from experts like this that provide mission-critical software. Also, software written in difficult environments like C!

> Thanks to AI, the specification evolved a lot, via back and forth of feedback, intellectual challenges about what was the best design, what was the right compromise, what was too engineered and what not.

The iterations at the specification level have to be a huge unlock. For an expert to be able to explore different approaches in rapid succession allows you to innovate much faster.

> You know what was the biggest realization of all that? For high quality system programming tasks you have to still be fully involved, but I ventured to a level of complexity that I would have otherwise skipped. AI provided the safety net for two things: certain massive tasks that are very tiring (like the 32 bit support that was added and tested later), and at the same time the virtual work force required to make sure there are no obvious bugs in complicated algorithms. To write the initial huge specification was the key to the successive work, as it was the key to review each single line of sparsearray.c and t_array.c and modifying everything was not a good fit.

He took a bigger bet, went for a bigger slice of functionality, and had a bigger outcome by using agentic coding tools.

### [When everyone has AI and the company still learns nothing](https://www.robert-glaser.de/when-everyone-has-ai-and-the-company-still-learns-nothing/)

Getting AI tools to your company and getting individual use out of them is not the hard thing, it is figuring out how your organization learns and improves with this capability. I'm seeing this right now because people are bringing a typical enterprise mindset to token consumption. Buying AI tools isn't expensive, but tokens are. And if you approach that with a desire to minimize token usage, you are going to destroy your potential. The question should **not** be token consumption, but instead value creation over token consumption.

I'm quoting at length here because I think this is so important.

> I keep coming back to three capabilities companies will need in the messy middle.
>
> 1. Agent Operations: which agents and AI tools are running, what systems they can touch, which data they can see, which actions require approval, where identity, audit, permissions, and runtime visibility live. This is the control side, and it matters because agentic work eventually touches real systems.
> 2. Loop Intelligence: which AI-assisted (or fully agentic) loops actually produce learning, which ones stay open, which ones decay, where agents create leverage, where they sprawl into side quests, which teams are stuck in tight supervision because they lack tests, context, or intuition. Which teams are ready for looser delegation.
> 3. Agent Capabilities: how useful capabilities get distributed across the organization without pretending that three monolithic agents can do everyone's work. AI is starting to behave more like a fluid base technology than a single application category. It does not fit cleanly into one "HR agent," one "engineering agent," one "sales agent," each sitting somewhere in the enterprise zoo. The better question is how capabilities flow into the places where work happens: employee harnesses, background agents, product teams, platform services, local skills, MCP servers, evaluation suites, runbooks, examples, and domain-specific procedures.
>
> This is where the platform question gets interesting. Who owns these capabilities? How does a useful agent skill discovered in one team become available to others without turning into a dead template? How do you enrich a developer's harness differently from a product person's harness, a support team's background agent, or a compliance workflow? Which capabilities belong close to the team, which belong in a platform layer, and which should never be generalized because the local context is the whole point?

How you operationalize this in a company is not solved at this time. I'm seeing it myself and seeing others wrestle with it. I like the foundational elements that this article puts forward.

Another model that I've considered is the transition from capital with servers to ephemeral infrastructure in the cloud. In a way capital is a lot like your team. It is hard to move around, hard to acquire, hard to change, but also incredibly powerful for the right things. The cloud made a part of that very flexible and just-in-time. We are already using different LLM models to bring just the right amount of intelligence to a task. And like the cloud we know that required a certain cost in tokens which is easy to know.

This morning I was doing a weekly review on one of my agents and Claude Code used the logging I have to show me five different skills the agent has and, to the penny, how much each of those cost me over the last week. That visibility applied to other tasks allows us to get much smarter.

### [Agentic Coding is a Trap | Lars Faye](https://larsfaye.com/articles/agentic-coding-is-a-trap)

This is a balanced article from an engineer seeing all sides of agentic coding. I found myself reading this and thinking that I agree and disagree based on the thing you are making. Not all code is equal. Some code deserves additional effort and oversight, and other stuff does not. I think folks don't consider that enough. For some solutions I think the process that is described here is spot on. For others, I would not agree.

I do think the issue that everyone is seeing but nobody knows the answer to is how junior engineers learn the hard things. I don't claim to know the answer, but I do know that just like so many other things there was a time when engineers needed to know assembly and for sure the "grey beards" of the time thought it was insane that a modern developer couldn't add some assembly in the midst of their solution.

The abstractions keep growing. Prompts are a new abstraction. Claude generated plans are an abstraction. I think the leap for us is to consider them as much part of the code base as the actual code that the computer runs.

The assertion of Vendor Lock-in though I would disagree with. This line:

> You know how much your employees cost; you have no idea how much your token costs will be day to day, month to month, year to year. If your entire team is using agentic coding as the default, your expense account will need to remain highly nimble.

To me the giant challenge in front of us is figuring out how you measure value creation over token usage.

### [Appearing Productive in The Workplace — No One's Happy](https://nooneshappy.com/article/appearing-productive-in-the-workplace/)

LLM capabilities are pouring into many professions and on the whole I'm bullish about this and think it will be transformational. However, there are disconnects that we need to become culturally attuned to. This article highlights one that we need to gain skill on first.

> In any previous era, the quality of a piece of work was a more or less reliable signal of the competence of the person who produced it. A novice essay read like a novice essay; novice code crashed in novice ways. AI has severed that relationship. A novice now produces work that does not betray the novice, because the competence the work reflects is not the novice's competence at all. It is the system's. The person, in the transaction, becomes a kind of conduit, capable of routing the output to a recipient and incapable of evaluating it on the way through.

As a recipient of information we need to now perceive that you can have expertise-signal with novice-capability. This was previously not possible. The signal actually looks a bit like a student cheating and handing in someone else's work. That isn't the right framing though since it is common to do this while performing a job. People routinely engage with expertise without the domain details. But as a recipient of information we now need to ask two questions: is the information presented of the quality it deserves, and is the person or system providing it actually capable of the assertion.

The article goes on to define how we can test that capability.

> Generative AI does well on tasks where feedback is fast, where being approximately right is good enough, where the human remains the final arbiter. Drafting a memo, generating examples, summarizing material the reader could verify if they cared to. The University of Illinois Generative AI guidance [[7](https://nooneshappy.com/article/appearing-productive-in-the-workplace/#ref-7)] and the PLOS Computational Biology "Ten Simple Rules" paper on AI in research [[8](https://nooneshappy.com/article/appearing-productive-in-the-workplace/#ref-8)], among the more careful documents now circulating, list much of this explicitly: **brainstorming, copyediting, reformulating one's own ideas, pattern detection in data one already understands**.

Read broadly I think it is critical that we know when we are "playing tennis without a net" as it were. If you are using AI for a task that is not testable, you need to treat that different than one that is testable. Testability of the assertion is key to knowing where you can get leverage. This is the magic unlock with software, because code is testable within limits. And the place where automatic programming still needs expert engineers is the untestable bits.

How do you apply this testability to other domains? And then how do you calibrate expertise into the system? Ideally expertise determines ways to make things testable that appear not to be. That is where I find real leverage. The LLM itself can be used to make the untestable output testable.

### [Six Years Perfecting Maps on watchOS - David Smith, Independent iOS Developer](https://david-smith.org/blog/2026/04/29/maps-on-watchos/)

Lovely essay emphasizing the artisanal effort put into making a feature work in the best way possible. I had to re-read when I hit the line "So… I commissioned a custom map." What? The extreme number of iterations put into making this user experience delightful is impressive and a good peek into what goes into making a truly remarkable experience a reality.

### [How people ask Claude for personal guidance — Anthropic](https://www.anthropic.com/research/claude-personal-guidance)

Interesting article including actual data. It is super interesting to me that "Health / Wellness" and "Professional / Career" are 27 and 26% respectively. Then a 50% drop-off to the next two, followed by another 50% drop-off to everything else. When I saw this it was like a giant blinking sign saying "COACH". Both of those areas are places where people get coaches if they can afford it and have a big enough need. AI coaches has always been an area I think we will see a ton of specialization in. Opening access to coaching feels incredibly powerful. It is also interesting that these two areas have lower rates of sycophancy.

The other take away is how the sycophancy rates are dropping with each model. That proves this is a problem solvable by training.

### [The Death of Scrum — An Interactive Essay](https://death-of-scrum.net/)

This article (worksheet?) hits on many of the topics I referenced in my [Software Is Liquid](https://www.thingelstad.com/2026/04/20/software-is-liquid.html) post from last week. When constraints, inputs, and outputs change it is necessary to review the system you are operating to see what changes are needed. That is what brought Scrum into existence and it is the thing that should make us question its utility going forward. The challenge to me is if not this, then what. There are four options suggested here: Shape Up, The Linear Method, Continuous Flow, and Agent-First Development. It will be interesting to see if we are able to move, as an industry, to something that is more focused on the particular aspects of the outcome we are shooting for, as opposed to the limitations and constraints of the system we have to work in.

---

---

## Journal

[May 1, 2026 at 11:13 AM](https://www.thingelstad.com/2026/05/01/had-second-shingrex-shot-yesterday.html)

Had second Shingrex shot yesterday and so far feel okay. First shot gave me shivers but it was a lot colder then. Hoping for the best and good to avoid shingles. 💉

[May 1, 2026 at 4:00 PM](https://www.thingelstad.com/2026/05/01/unwelcome-surprise-to-have-water.html)

Unwelcome surprise to have water ponding around the well head at the cabin. This isn't good. 😬

![](https://files.thingelstad.com/weekly-thing/347/journal/6892e7bbc6.jpg)

[May 2, 2026 at 8:38 AM](https://www.thingelstad.com/2026/05/02/so-great-to-connect-with.html)

So great to connect with Minnebar OG's this morning. Awesome to have Ben and Luke here to celebrate Minnebar 20!

![](https://files.thingelstad.com/weekly-thing/347/journal/99d6116d2c.jpg)

[May 2, 2026 at 3:00 PM](https://www.thingelstad.com/2026/05/02/tyler-led-his-first-session.html)

[Tyler](https://tyler.thingelstad.com) led his first session at Minnebar today! He did an amazing job talking about AI in Schools and what is good, bad, and how schools should adapt. 👏

![](https://files.thingelstad.com/weekly-thing/347/journal/bcee8dc4ab.jpg)

[May 2, 2026 at 5:00 PM](https://www.thingelstad.com/2026/05/02/tyler-and-i-were-lucky.html)

Tyler and I were lucky enough to be interviewed for the Minnebar 20 special video today.

![](https://files.thingelstad.com/weekly-thing/347/journal/1f7d857cab.jpg)

[May 2, 2026 at 1:34 PM](https://www.thingelstad.com/2026/05/02/great-teamsps-group-at-minnebar.html)

Great TeamSPS group at Minnebar 20!

![](https://files.thingelstad.com/weekly-thing/347/journal/0cad4da399.jpg)

[May 2, 2026 at 7:08 PM](https://www.thingelstad.com/2026/05/02/pla-run-to-microcenter.html)

PLA run to Microcenter.

![](https://files.thingelstad.com/weekly-thing/347/journal/d81050bd61.jpg)

[May 3, 2026 at 12:11 PM](https://www.thingelstad.com/2026/05/03/pla-storage-organized-and-ready.html)

PLA storage organized and ready to go!

![](https://files.thingelstad.com/weekly-thing/347/journal/9035d3801d.jpg)

[May 3, 2026 at 6:06 AM](https://www.thingelstad.com/2026/05/03/up-and-writing-at-am.html)

Up and writing at 6am for the next [Weekly Thing](https://weekly.thingelstad.com)!

While I'm doing that I've got Claude Code backfilling audio versions of the Weekly Thing, and another Claude Code instance doing some incremental work on [Elixir](https://poapkings.com/elixir/).

[May 3, 2026 at 12:12 PM](https://www.thingelstad.com/2026/05/03/tyler-and-i-are-at.html)

Tyler and I are at Fat Pants Brewing for the last-minute rescheduled Miami GP! Go Ferrari! Go Red Bull!

![](https://files.thingelstad.com/weekly-thing/347/journal/a814739f8a.jpg)

![](https://files.thingelstad.com/weekly-thing/347/journal/08388e7462.jpg)

[May 3, 2026 at 4:29 PM](https://www.thingelstad.com/2026/05/03/pokmon-afternoon-at-minnesota-card.html)

Pokémon afternoon at [Minnesota Card Show](https://www.cardshowmn.com)!

![](https://files.thingelstad.com/weekly-thing/347/journal/0b741e13d6.jpg)

[May 6, 2026 at 9:26 PM](https://www.thingelstad.com/2026/05/06/prompt-i-gave-claude-code.html)

Prompt I gave Claude Code on a recent project.

> I would like to iterate faster. I would like you to use the ANTHROPIC API key and ask Haiku to generate 20 questions for each agent persona that Jamie (me) would reasonably ask. Then run those questions to each agent and see how they respond. Adjust based on that and keep iterating until all 4 agents respond to the 20 questions okay. Make sense?

Worked well.

[May 6, 2026 at 5:07 PM](https://www.thingelstad.com/2026/05/06/mazie-is-home-from-her.html)

[Mazie](https://mazie.thingelstad.com/) is home from her semester abroad! 🥳

![](https://files.thingelstad.com/weekly-thing/347/journal/b918f9f38f.jpg)

[May 6, 2026 at 9:24 PM](https://www.thingelstad.com/2026/05/06/we-are-all-into-noah.html)

We are all into [Noah Kahan](https://noahkahan.com), and Mazie is [maybe infatuated](https://mazie.thingelstad.com/2026/05/05/i-love-the-great-divide.html) with his music. We had a nice night on the couch with her back home and the incredible [Out of Body](https://www.netflix.com/title/82161512) documentary about his rise. It is incredible how quickly Kahan's popularity exploded and the movie chronicles the journey.

![](https://files.thingelstad.com/weekly-thing/347/journal/108ebb3814.jpg)

---

## Briefly

It is incredible what you can make a font do. This seems perfect for a variety of inline data visualizations. → **[Datatype — variable font that turns text into charts](https://franktisellano.github.io/datatype/)**

Delightful bit creating QR codes with pencil and paper. (Bonus, local Minneapolis blogger I wasn't following!) → **[Hand‑drawn QR codes — Seth Larson](https://sethmlarson.dev/hand-drawn-qr-codes)**

I went to "3D Printing: One step closer to the home replicator?" at Minnebar 20. The presenter shared that he had created this website to help people get good deals. It was a great session. → **[FilamentHound — Best Prices on 3D Printing Filament](https://filamenthound.com/)**

Ansible without the YAML. → **[pyinfra - Fast Python Infrastructure Automation & Configuration Management Tool](https://pyinfra.com/)**

I've commented about platforms making command-line interfaces to allow agents to use them, and shifting to agents as their customer. MCP is an evolution and secondary channel to do that. → **[The AWS MCP Server is now generally available | AWS News Blog](https://aws.amazon.com/blogs/aws/the-aws-mcp-server-is-now-generally-available/)**

ENS continuing to improve blockchain accessibility, but also showing the state of the art in how blockchain native applications work. It is funny to me that the massively decentralized ENS is learning delegation from the centralized DNS system. → **[Names Are No Longer Single Objects | ENS Blog](https://ens.domains/blog/post/names-are-no-longer-single-objects)**

Web browsers added a "do not track" feature years ago. Don't take too much solace in it though, since it is not enforceable, just a way of sharing a preference. It is also the case that a lot of other tools send tracking information, so this environment preference is an attempt to create a similar mechanism. → **[DO_NOT_TRACK](https://donottrack.sh/)**

Interesting data on the evolving roles of Dads in the household. → **[How American Dads Became the Parents Their Fathers Never Were](https://www.derekthompson.org/p/why-do-richer-dads-spend-more-time)**

Some good news! 🎉 → **[Meta lost 20 million users last quarter | The Verge](https://www.theverge.com/tech/921089/meta-earnings-q1-2026-user-decline-ai-investments)**

---

**To all the Moms out there I want to wish you a Happy Mother's Day!** Y'all are amazing. Particularly all the Moms I know. Nothing but delightful and wonderful women in that group. Our kids have been blessed to have an incredible Mom, and both Tammy and I are the wonderful results of great Moms. Love you Mom! Love you dear! 🥰

---

A haiku to leave you with…

**Hand‑drawn QR dreams,
Redis arrays tell stories —
Dads learn to listen**

Would you like to discuss the topics in the Weekly Thing further? Check out the [Weekly Thing on Reddit](https://www.reddit.com/r/weeklything/). 👋

👨‍💻
