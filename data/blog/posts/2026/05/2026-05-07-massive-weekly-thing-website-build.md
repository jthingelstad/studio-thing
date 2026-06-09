---
microblog_id: 5863188
url: "https://www.thingelstad.com/2026/05/07/massive-weekly-thing-website-build.html"
title: "Massive Weekly Thing Website Build"
published: "2026-05-08T03:00:00+00:00"
post_kind: post
categories: ["Weekly Thing", "Featured"]
---

I've commented that agentic coding makes things that were previously on your "list of impossible projects" into things that you can do. I have long had on my "impossible project" list the desire to create a website for the Weekly Thing that let the archive shine in ways that I knew were possible but no solution out there delivered. With 9 years of writing and 345 issues in the archive there is so much to surface.

To do this I knew I would need to build it on my own. I could use the Buttondown API to get the issues and make them accessible. But then I needed a website. I needed a content pipeline. Oh, and that archive has old formats from different platforms that were a mangled mess of HTML.

This was truly on the "impossible list" for me personally. If I wanted to spend tens-of-thousands of dollars, or probably even more, I maybe could have hired someone to build it. A laughable idea really.

So I decided to take my experiences with Claude Code, Claude Design, and Codex and point it at this problem. Over the last couple of weeks I've been working on the new Weekly Thing website experience.

I just have to say I'm so thrilled with the results that I can barely handle it. Rather than type a novel here I'm just going to list out what the site has. Even better, go there and explore:

[**https://weekly.thingelstad.com**](https://weekly.thingelstad.com/)

Here is what the new site has!

1️⃣ Completely reimagined **landing page to describe the Weekly Thing**. Gone is the basic Buttondown paragraph of text and a signup button. The home page hopefully gives a much better feel for what the Weekly Thing is.

2️⃣ [**Archive**](https://weekly.thingelstad.com/archive/) page has full index of every issue back to number 1. This is also now optimized for the Weekly Thing with issue images, link counts, organized by year.

3️⃣ **[Thingy](https://thingy.thingelstad.com/chat/), the Weekly Thing librarian** that has read every issue of the Weekly Thing and is ready to converse with you about all of it. I have wanted to make an agent like this for over a year and it is finally real. I've found this fascinating to play with and ask questions of.

You will see this feature requires you to provide your subscriber email address. It is only available to confirmed subscribers of the Weekly Thing.

You may recall in [WT311](https://weekly.thingelstad.com/archive/311/) I shared a custom GPT that was sort of like this. That was grade school level. Thingy is much smarter!

Some prompts that are fun to explore with Thingy:

- [How has the arc of AI evolved in the Weekly Thing?](https://thingy.thingelstad.com/chat/?prompt=How+has+the+arc+of+AI+evolved+in+the+Weekly+Thing%3F)
- [Compare Tik Tok, Facebook, and X from the archive.](https://thingy.thingelstad.com/chat/?prompt=Compare+Tik+Tok%2C+Facebook%2C+and+X+from+the+archive.)
- [Explain to me how Jamie connects Indie Web and Crypto? They seem very opposite to me.](https://thingy.thingelstad.com/chat/?prompt=Explain+to+me+how+Jamie+connects+Indie+Web+and+Crypto%3F+They+seem+very+opposite+to+me.)

4️⃣ **[Search](https://weekly.thingelstad.com/search/) is now super powered.** The searching is indexed into the section of the weekly thing. This works way better than before.

5️⃣ On the page for each issue you will see that there is a **Table of Contents** on the left. It is a little thing, but another example of something I've wanted for a long time. The Weekly Thing is long and this gives a way to navigate. Also, each of those items is a hyperlink so you can now send a link to a specific notable link in a specific issue.

6️⃣ Big one -- **you can now LISTEN to the Weekly Thing**. I've filled this in for the last 10 issues. On the issue page there is a "Listen" button where it will be read for you.

7️⃣ **Podcast?** Well if I have an audio file for each issue why not bundle that into a podcast. So I did. You should be able to find the Weekly Thing on [Apple Podcasts](https://podcasts.apple.com/us/podcast/weekly-thing/id1895865769) and [Spotify](https://open.spotify.com/show/43A9fytZDKaZhrkp3qbukh). It is propagating through other platforms. Should be on [Overcast](https://overcast.fm/itunes1895865769/weekly-thing) too.

8️⃣ **Support for LLMs.txt!** This is a bit hidden, but if you want to talk with the LLM of your choice about the Weekly Thing, give the LLM this link: 

[https://weekly.thingelstad.com/llms.txt](https://weekly.thingelstad.com/llms.txt)

That provides an LLM optimized index of the entire 345 issues, as well as links to LLM optimized versions of every email! This means ChatGPT or Claude or whatever else can dive deep into the content. I have actually used this myself when asking a model to do some research with me.

A quick note about the audio:

- This doesn't replace or remove my actual podcast, [Another Thing](https://another.thingelstad.com/). There is still just one episode there but I'm not giving up on that.
- The audio for the Weekly Thing is text-to-speech using a transformed version of the email text. It announces sections, gives links numbers, announces quotes, and cuts some sections. I've listened to a few and think it works reasonably well.
- I'll probably evolve the generated audio, and right now it only exists for the last 10 issues, but I plan to backfill all issues with audio over time.

Take a look. Try out the archive, search, Thingy. Listen to an issue. And let me know what you think… anything not work right? Read wrong? Something missing? Or just that you think it is all cool?
