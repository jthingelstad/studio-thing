---
buttondown_id: em_69141yfm8581xaejqqtp6pkjb3
number: 289
subject: Weekly Thing 289 / Queueing, Counting, Mapping
publish_date: '2024-05-25T12:00:00Z'
slug: '289'
description: Efficient new way to count, 2nd-gen email, ideal email folder structure, Windows Returns, mapping LLMs, queueing strategies, No Wrong Doors.
image: https://files.thingelstad.com/weekly-thing/289/cover.jpg
absolute_url: https://buttondown.com/weekly-thing/archive/289/
domains:
- arstechnica.com
- encore.dev
- gabrielsieben.tech
- kottke.org
- lethain.com
- om.co
- seths.blog
- stratechery.com
- thesweetsetup.com
- vitalik.eth.limo
- www.anthropic.com
- www.lofibucket.com
- www.quantamagazine.org
- www.theguardian.com
links:
- text: Computer Scientists Invent an Efficient New Way to Count | Quanta Magazine
  url: https://www.quantamagazine.org/computer-scientists-invent-an-efficient-new-way-to-count-20240516/
  domain: www.quantamagazine.org
  heading_context: '[Computer Scientists Invent an Efficient New Way to Count | Quanta Magazine](https://www.quantamagazine.org/computer-scientists-invent-an-efficient-new-way-to-count-20240516/)'
  section: Notable
- text: Thinking out loud about 2nd-gen Email – Gabriel Sieben
  url: https://gabrielsieben.tech/2024/05/17/thinking-out-loud-2nd-gen-email/
  domain: gabrielsieben.tech
  heading_context: '[Thinking out loud about 2nd-gen Email – Gabriel Sieben](https://gabrielsieben.tech/2024/05/17/thinking-out-loud-2nd-gen-email/)'
  section: Notable
- text: The Ideal Email Folder Structure – The Sweet Setup
  url: https://thesweetsetup.com/the-ideal-email-folder-structure/
  domain: thesweetsetup.com
  heading_context: '[The Ideal Email Folder Structure – The Sweet Setup](https://thesweetsetup.com/the-ideal-email-folder-structure/)'
  section: Notable
- text: Windows Returns – Stratechery by Ben Thompson
  url: https://stratechery.com/2024/windows-returns/
  domain: stratechery.com
  heading_context: '[Windows Returns – Stratechery by Ben Thompson](https://stratechery.com/2024/windows-returns/)'
  section: Notable
- text: Mapping the Mind of a Large Language Model | Anthropic
  url: https://www.anthropic.com/research/mapping-mind-language-model
  domain: www.anthropic.com
  heading_context: '[Mapping the Mind of a Large Language Model | Anthropic](https://www.anthropic.com/research/mapping-mind-language-model)'
  section: Notable
- text: How do layer 2s really differ from execution sharding?
  url: https://vitalik.eth.limo/general/2024/05/23/l2exec.html
  domain: vitalik.eth.limo
  heading_context: '[How do layer 2s really differ from execution sharding?](https://vitalik.eth.limo/general/2024/05/23/l2exec.html)'
  section: Notable
- text: Queueing – An interactive study of queueing strategies – Encore Blog
  url: https://encore.dev/blog/queueing
  domain: encore.dev
  heading_context: '[Queueing – An interactive study of queueing strategies – Encore Blog](https://encore.dev/blog/queueing)'
  section: Notable
- text: No Wrong Doors | Irrational Exuberance
  url: https://lethain.com/no-wrong-doors/
  domain: lethain.com
  heading_context: '[No Wrong Doors | Irrational Exuberance](https://lethain.com/no-wrong-doors/)'
  section: Notable
- text: 'Interviewed: my creative process – On my Om'
  url: https://om.co/2024/05/17/interview-my-blogging-process/
  domain: om.co
  heading_context: null
  section: Briefly
- text: The History of Tetris World Records
  url: https://kottke.org/24/05/the-history-of-tetris-world-records
  domain: kottke.org
  heading_context: null
  section: Briefly
- text: “Unprecedented” Google Cloud event wipes out customer account and its backups | Ars Technica
  url: https://arstechnica.com/gadgets/2024/05/google-cloud-accidentally-nukes-customer-account-causes-two-weeks-of-downtime/
  domain: arstechnica.com
  heading_context: null
  section: Briefly
- text: How a 64k intro is made
  url: https://www.lofibucket.com/articles/64k_intro.html
  domain: www.lofibucket.com
  heading_context: null
  section: Briefly
- text: “I don’t learn that way” | Seth's Blog
  url: https://seths.blog/2024/05/i-dont-learn-that-way/
  domain: seths.blog
  heading_context: null
  section: Briefly
- text: Microplastics found in every human testicle in study | The Guardian
  url: https://www.theguardian.com/environment/article/2024/may/20/microplastics-human-testicles-study-sperm-counts
  domain: www.theguardian.com
  heading_context: null
  section: Briefly
word_count: 2040
---
Good morning! 👋

I hope you are having a great start to your Memorial Day weekend and the official start of summer! It is time to get the grill going and s'mores supplies for the campfire. Mazie is back home from college and Tyler is counting down the last days of school. What a fun time of year.

Hope you get a bunch of time outside with the sun. 😎

---

## Currently

**Eating:** Mazie had these **[Carmelita Bars](https://www.averiecooks.com/carmelitas/)** at St. Olaf and decided to make a batch at home. They are ridiculously good. Proceed with caution. ⚠️

**Drinking:** Staying away from caffeine has me exploring tea for those times when I still want a warm beverage. A friend recommended **[August Uncommon Tea](https://august.la/)** to me and I ordered the [set of caffeine free samplers](https://august.la/collections/herbal-teas/products/top-10-caffeine-free-teas-sampler) to try. I’m enjoying a mug of [Psychocandy](https://august.la/collections/tea/products/psychocandy) right now, which deserves credit if only for the great name!

---

![](https://files.thingelstad.com/weekly-thing/289/cover.jpg)

Beautiful [Clematis](https://en.wikipedia.org/wiki/Clematis) flowers.

May 19, 2024
Minneapolis, Minnesota

---

## Notable

### [Computer Scientists Invent an Efficient New Way to Count | Quanta Magazine](https://www.quantamagazine.org/computer-scientists-invent-an-efficient-new-way-to-count-20240516/)

Wow, this is a fun algorithm to get an approximation of the number of unique elements in a list.

> Next, move to Round 2. Continue as in Round 1, only now we’ll make it harder to keep a word. When you come to a repeated word, flip the coin again. Tails, and you delete it, as before. But if it comes up heads, you’ll flip the coin a second time. Only keep the word if you get a second heads. Once you fill up the board, the round ends with another purge of about half the words, based on 100 coin tosses.

This is the kind of problem that programmers, particularly those working at scale, have to deal with fairly regularly. It seems easy "well, just count the things", but counting, particularly unique things, in a list that is billions or billions of billions long is very resource intensive. And often an approximate count is fine.

### [Thinking out loud about 2nd-gen Email – Gabriel Sieben](https://gabrielsieben.tech/2024/05/17/thinking-out-loud-2nd-gen-email/)

Sieben goes on a fun and thought-provoking journey exploring how we could go about innovating at the protocol layer for email. Email is still such a critical capability, and the foundations of it are beyond creeky. We have built so much around it though that it seems completely ossified. This article suggests ways to break-through that ossification and create new approaches.

### [The Ideal Email Folder Structure – The Sweet Setup](https://thesweetsetup.com/the-ideal-email-folder-structure/)

It has been years since I have given much thought to how I use folders in my email, but seeing this article brought it to mind. I generally agree with this article to not create a ton of folders like most people (including myself) did decades ago. But I also don't recommend just using Inbox and Archive as this article suggests.

My approach is to **use folders for retention and workflow reasons, and never for topics**. Here is how this looks for me:

- **Auto Replies**: I create mail rules that catch things like Out of Office messages and I route them here out of my normal workflow.
- **Scratch**: This is like my desktop but for email. Items go here if it is something that requires action but I cannot get to it quickly, and for some reason doesn't go to OmniFocus.
- **Save**: I put receipts and things in here, and this folder automatically deletes after 365 days.
- **External**: I have email addresses on GMail and iCloud, and they autoforward to this folder. I don't intermingle them with normal mail since nobody should be sending to those addresses.

I also use Sanebox which manages a separate set of folders that I don't really interact with directly.

### [Windows Returns – Stratechery by Ben Thompson](https://stratechery.com/2024/windows-returns/)

Interesting recap of Microsoft's most recent Windows announcements and the new class of "Copilot+ PCs".

> The end result — assuming that reviewed performance measures up to Microsoft’s claims — is an array of hardware from both Microsoft and its OEM partners that is MacBook Air-esque, but, unlike Apple’s offering, actually meaningfully integrated with AI in a way that not only seems useful today, but also creates the foundation to be dramatically more useful as developers leverage Microsoft’s AI capabilities going forward. I’m not going to switch (yet), but it’s the first time I’ve been tempted; at a minimum the company set a clear bar for Apple to clear at next month’s WWDC.

🤔

### [Mapping the Mind of a Large Language Model | Anthropic](https://www.anthropic.com/research/mapping-mind-language-model)

Interesting analysis from Anthropic figuring out how to model out the "feature" components of an LLMs data (brain?) and then modify the priority of a "feature" to change the way in which it engages.

> The fact that manipulating these features causes corresponding changes to behavior validates that they aren't just correlated with the presence of concepts in input text, but also causally shape the model's behavior. In other words, the features are likely to be a faithful part of how the model internally represents the world, and how it uses these representations in its behavior.

Someone call up a neuroscientist for AI!

### [How do layer 2s really differ from execution sharding?](https://vitalik.eth.limo/general/2024/05/23/l2exec.html)

Vitalik sharing his thinking about the benefits of Ethereum's approach to scaling via Layer 2 networks.

> Because Ethereum is a layer-2-centric ecosystem, you are free to go independently build a sub-ecosystem that is yours with your unique features, and is at the same time a part of a greater Ethereum.

I think this approach is a great one and it is one of the many reasons I continue to be enthusiastic about Ethereum. You can imagine a collection of networks that are all interoperable as part of the Ethereum ecosystem solving a very broad and diverse set of needs. It is harder to do, and slower in the near-term, but if done right will allow for incredible capability.

### [Queueing – An interactive study of queueing strategies – Encore Blog](https://encore.dev/blog/queueing)

Great overview of various queue solutions using interactive visuals to let you play with sending messages into the queues and seeing how they behave. It is fun to see many people playing with these interactive learning experiences.

### [No Wrong Doors | Irrational Exuberance](https://lethain.com/no-wrong-doors/)

I had not heard of this No Wrong Doors approach but I like the approach. I've seen issues like this many times in my own organizations. The internal operations of a large team are often complex, and that complexity is typically (not always) needed for various reasons. But it makes things harder to navigate. Hence No Wrong Doors.

> Beyond being helpful to your colleagues, which is an obvious goal in some companies and not-at-all a cultural priority in others, I think there are a number of other advantages to think about here. First, being helpful creates positive relationships across organizations. Second, it makes it more obvious where you do have genuine areas of ambiguous ownership, and makes it possible for informed parties to escalate that rather than relying on folks with the least context to know to escalate the ambiguities. Third, it educates folks asking for help about the right thing to do, because a knowledgeable person helping is a great role model of the best way to solve a problem. Finally, if you happen to route to the wrong person–it happens!–then you learn that immediately rather than forcing someone without context to navigate the confusion.

I've seen and helped this happen in teams like Help Desk, but applying the concept to more boutique needs could add a lot of value.

---

## Journal

[May 17, 2024 at 10:30 PM](https://www.thingelstad.com/2024/05/17/tyler-and-i.html)

Tyler and I went to see the [Minnesota Orchestra](https://www.minnesotaorchestra.org) [Star Wars: The Last Jedi in Concert](https://www.minnesotaorchestra.org/tickets/calendar/movies-music/star-wars-the-last-jedi/) tonight. Having never been to something like this we weren’t sure what to expect and were instantly blown away. What a fabulous experience!

![](https://files.thingelstad.com/weekly-thing/289/journal/8ceba8e0a4.jpg)

[May 18, 2024 at 5:40 PM](https://www.thingelstad.com/2024/05/18/with-just-one.html)

With just one final left next week Mazie is wrapping up her Freshman year at St. Olaf. She did an amazing job in her classes and made a ton of new friends. We packed up her dorm room and moved her stuff home today. It is great to have her back home for the summer.

![](https://files.thingelstad.com/weekly-thing/289/journal/6b115d6e27.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/55cfb4c542.jpg)

[May 18, 2024 at 5:42 PM](https://www.thingelstad.com/2024/05/18/we-visited-the.html)

We visited the [Quaking Bog](https://www.minneapolisparks.org/parks-destinations/parks-lakes/quaking_bog/) at Theodore Wirth today. We’d never been there and I was lucky enough to have wore my Chaco sandals. If you go, be prepared for your feet to get wet. It is a cool spot.

![](https://files.thingelstad.com/weekly-thing/289/journal/7658fa7aee.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/0e42deed64.jpg)

[May 18, 2024 at 5:44 PM](https://www.thingelstad.com/2024/05/18/while-we-were.html)

While we were at Theodore Wirth we also stopped by the [Eloise Butler Wildflower Garden and Bird Sanctuary](https://www.minneapolisparks.org/parks-destinations/parks-lakes/gardens__bird_sanctuaries/eloise_butler_wildflower_garden_and_bird_sanctuary/) and walked through the loop. It was really pretty. We’ll be back for sure.

![](https://files.thingelstad.com/weekly-thing/289/journal/8c752c88ee.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/4aaac95d98.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/c21e0ed831.jpg)

[May 18, 2024 at 5:48 PM](https://www.thingelstad.com/2024/05/18/microblog-just-added.html)

Micro.blog just added a new feature to [comment directly on a blog post](https://news.micro.blog/2024/05/18/we-launched-two.html) on a hosted blog, instead of having to do it in the timeline on micro.blog. This also allows you to authenticate a comment using Mastadon or Blue Sky, in addition to micro.blog itself. Easier commenting now available!

[May 18, 2024 at 7:59 PM](https://www.thingelstad.com/2024/05/18/great-night-for.html)

Great night for Minnesota United FC v Portland Timbers! ⚽️

![](https://files.thingelstad.com/weekly-thing/289/journal/5c69290e9e.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/4e13d37f2c.jpg)

[May 19, 2024 at 11:12 PM](https://www.thingelstad.com/2024/05/19/this-blackened-swordfish.html)

This Blackened Swordfish with Spanish Rice special at [6Smith](https://www.6smith.com) was so good I came back to have it a second time.

![](https://files.thingelstad.com/weekly-thing/289/journal/68c6ca9194.jpg)

[May 19, 2024 at 11:18 PM](https://www.thingelstad.com/2024/05/19/tammy-and-i.html)

Tammy and I saw [The Decemberists](https://www.decemberists.com) at the [Palace Theatre](https://first-avenue.com/venue/palace-theatre/) tonight. They were great as always. What wasn't great were our seats -- balcony row W.

![](https://files.thingelstad.com/weekly-thing/289/journal/01d093a5ef.jpg)

![](https://files.thingelstad.com/weekly-thing/289/journal/f6406b9f4a.jpg)

[May 19, 2024 at 11:21 PM](https://www.thingelstad.com/2024/05/19/ive-gotten-into.html)

I've gotten into the NBA playoffs a bit this year. I'm was very happy (and a little surprised?) to see the [Timberwolves](https://www.nba.com/timberwolves/) beat the [Nuggets](https://www.nba.com/nuggets/) in game seven of their series! **Let's go Wolves!** 🏀

[May 19, 2024 at 11:23 PM](https://www.thingelstad.com/2024/05/19/two-decades-ago.html)

Two decades ago when I started publishing on the web I would have never guessed that linking to websites, with no URL redirection or tracking tags, would feel almost subversive now. I now find myself delighting in adding even more links to blog posts. Creating the web I want!

[May 21, 2024 at 6:26 PM](https://www.thingelstad.com/2024/05/21/awesome-to-see.html)

Awesome to see my [Weekly Thing Seven Year Anniversary POAP](https://collectors.poap.xyz/drop/173575) highlighted in the most recent [Week in POAP](https://www.poap.news/may-21-2024/) today. 🤩

---

### Weekly Thing Forum 🆕

Join Tom Mungavan, Barry Hess, Lou Plummer, Patrick Hambek, Eric Walker, and many other Weekly Thing readers in the [Weekly Thing Forum](http://ponder.weeklything.com). Recent topics include:

- [Destroying Young People's Future](https://ponder.us/group/weeklything/discussions/601)
- [Weekly Thing 287](https://ponder.us/group/weeklything/discussions/600)
- [AI controlled F16 fight humans](https://ponder.us/group/weeklything/discussions/589)
- [Ukraine Aid](https://ponder.us/group/weeklything/discussions/586)
- [NASA’s Voyager 1 Resumes Sending Engineering Updates to Earth](https://ponder.us/group/weeklything/discussions/583)

---

## Briefly

I've followed Om for years and it was super cool to see [him featured on People & Blogs](https://manuelmoreale.com/pb-om-malik)! I feel a little cooler now since [I was also featured on People & Blogs](https://manuelmoreale.com/pb-jamie-thingelstad). 🤩 → **[Interviewed: my creative process – On my Om](https://om.co/2024/05/17/interview-my-blogging-process/)**

I’m good at Tetris, but not anywhere near great. It is still one of my favorite games. I’m looking forward to watching this movie!  → **[The History of Tetris World Records](https://kottke.org/24/05/the-history-of-tetris-world-records)**

This is absolutely terrifying! → **[“Unprecedented” Google Cloud event wipes out customer account and its backups | Ars Technica](https://arstechnica.com/gadgets/2024/05/google-cloud-accidentally-nukes-customer-account-causes-two-weeks-of-downtime/)**

Cool article going into details how these very small executables that create amazing graphics are done. → **[How a 64k intro is made](https://www.lofibucket.com/articles/64k_intro.html)**

Learn through play, not by watching. → **[“I don’t learn that way” | Seth's Blog](https://seths.blog/2024/05/i-dont-learn-that-way/)**

I feel like there is going to be a developing story about microplastics and a range of impacts to humans. → **[Microplastics found in every human testicle in study | The Guardian](https://www.theguardian.com/environment/article/2024/may/20/microplastics-human-testicles-study-sperm-counts)**

---

## Fortune

Here is your fortune…

**Don't look now, but the man in the moon is laughing at you. 🌝**

Thank you for subscribing to the [Weekly Thing](https://weekly.thingelstad.com/)!

---

## Want to support the Weekly Thing?

First — thank you for subscribing and reading. Here are some things you can do that would be great…

- **Share** [Weekly Thing 289 / Queueing, Counting, Mapping](https://buttondown.com/weekly-thing/archive/289/) with others you know!
- **Post** about the [Weekly Thing](https://weekly.thingelstad.com) and let others know about it.
- **Join** the [Weekly Thing Forum](https://ponder.us/join/9235b7db) and connect with others.
- **[Email me](mailto:jamie@thingelstad.com)** comments, feedback, or just to say Hi!
