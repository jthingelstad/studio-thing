---
microblog_id: 3562215
url: "https://www.thingelstad.com/2023/09/24/how-i-build.html"
title: "How I Build the Weekly Thing"
published: "2023-09-24T14:03:02+00:00"
post_kind: post
categories: ["Weekly Thing"]
---

One of the common questions I’m asked is how I create the [Weekly Thing](https://weekly.thingelstad.com). There are two flavors of this question. One is about finding content and writing, and the other is about the technical act of producing each issue. This article is an attempt to answer the second question about producing each issue.

I just finished a big revamp of the automation that I use to build each issue of the Weekly Thing so it feels like a good time to document and share how it works. I’m very happy with how this is working now, and have used automation to achieve two goals.

1. Remove as much of the fiddly bits around formatting and connecting systems as possible, leaving my time for the creative part of writing and sharing.
2. Allow some sections to be authored ahead of time, so I can create in small chunks of time.

The revamp had some additional goals, or things to fix that I badly needed to address.

1. It should run on any platform. Some of my steps required software that only worked on iOS so I oddly couldn't run my automation on my Mac.
2. No Python scripts, all native Shortcuts. I had some steps that involved Python and that was harder to maintain and change.
3. Durability, better error handling, and logging. When my automation didn’t work it was hard to know why. Not good when your on deadline!
5. Automation for all sections. For 6 years the photo section has never been supported with automation.

I’m happy to report that my new automation does all of the above, and even pulls in an additional big feature of [reducing image sizes](https://www.thingelstad.com/2023/09/23/smaller-images-for.html).

### Overall Solution

Let's start with an overall view of the whole process. This diagram shows how the various parts are connected. Green boxes are Shortcuts, and grey boxes are Apps or Services. The people represent where I author and interact to create content. This isn't 100% of everything, but covers the important parts.

<img src="https://www.thingelstad.com/uploads/2023/weekly-thing-automation-2023.png" width="600" height="804" alt="">

The easiest way to think of this is that the Build Issue shortcut has a list of other Shortcuts. It iterates through that list calling each shortcut. Those shortcuts in turn return a block of Markdown text. Once all shortcuts have been called, they are then combined into one Markdown block for final review and editing.

This approach is fundamentally the same as I [have used since 2017](https://www.thingelstad.com/2017/06/23/assembling-the-weekly.html). The biggest change since then is I call many more Shortcuts, and back then I pulled HTML since MailChimp required that.

The huge change that I've been making is that each section Shortcut is much more durable, and uses Data Jar to cache and manage data.

### Software Manifest

Core technologies that are used for this include.

- [Shortcuts](https://support.apple.com/guide/shortcuts/welcome/ios): This is the heart of the solution and where everything starts.
- [Drafts](https://getdrafts.com): I use Drafts for a ton of things, including writing this blog post. Drafts has incredible support for Shortcuts and automation. Any sections of the Weekly Thing that are just writing I do in Drafts. These are then put into Workspaces in Drafts to interact with Shortcuts. For example, the Currently section is a Workspace in Drafts that is pulled in via a Shortcut.
- [Data Jar](https://datajar.app): This is like a simple database that allows me to cache and store content for each Shortcut.
- [S3 App](https://s3files.app): Great app that was a huge unlock for me since it allowed me to finally automate the Photo section, and in general makes it super simple to get files on the web from Shortcuts.
- [Pinboard API](https://www.pinboard.in/api/): All the links in Featured, Notable, and Briefly come from Pinboard, and I author the blurbs about them in Pinboard as well. They end up in the respective section because I add a "_featured" or "_briefly" tag to them. If no tag, they are in Notable. The reason this works well is that I can author in Markdown in Pinboard, even though Pinboard has no idea what Markdown is.
- [thingelstad.com RSS Feed](https://www.thingelstad.com/feed.xml): RSS is how I pull my blog posts into the Journal section. This is a little weird since I author my blog in Markdown, and then pull it via RSS in HTML, and then convert the HTML back to Markdown. That process seems weird but I will likely keep it since the conversion does a couple of nice things to insure the Markdown is well formatted.

Shortcuts is where the majority of the work for this occurs and here is my current set.

<img src="https://www.thingelstad.com/uploads/2023/screenshot-2023-09-23-at-5.07.32-pm.png" width="600" height="345" alt="">

The "Build Issue" Shortcut is the one that collects markdown from all the sections and assembles it. You will see a lot of "Section:Name" shortcuts, those are the ones that are responsible for returning a section. Mostly the names make sense for a number of other utility shortcuts.

### Data Jar

The other very important component is Data Jar, which you can think of like a database or cache for Shortcuts. Data Jar is a game changer for Shortcuts as it allows you to share and keep state between various Shortcuts. Here is what the Data Jar dictionary for issue 262 looks like.

<img src="https://www.thingelstad.com/uploads/2023/screenshot-2023-09-23-at-5.07.54-pm.png" width="600" height="283" alt="">

As much as possible the section Shortcuts use Data Jar to store anything they need. I'll use a simple example with Section:Fortune. Each issue of the Weekly Thing has a Fortune that I set. The basic flow is:

1. See if "Weekly Thing.«Current Issue».Fortune" exists in Data Jar, if it does return markdown and you are done.
2. If "Weekly Thing.«Current Issue».Fortune" does not exist present random Fortunes to user until one is selected.
3. Once Fortune is selected, store it at "Weekly Thing.«Current Issue».Fortune" and return markdown.

By using this approach I can run this anytime I want to get that section final, and when I build it at publishing time it will not require any input from me. This makes things very durable as well since I can re-run the automation easily.

### Summary

One of the takeaways I hope you have from reading this is that while Shortcuts seem pretty trivial, you can assemble them in interesting way with additional software to create very powerful solutions. Especially with add-ons like Data Jar and S3 Files you can do some incredible stuff.

I also think this is a good example of how you can apply automation to personal workflows. I try to use as much automation as possible to remove mundane components from my week. It is worth investing the time in Shortcuts or similar tools to see where you might personally benefit.

_See [discussion on Weekly Thing Forum](https://ponder.us/group/weeklything/discussions/271)._

_This post is part of the [Shortcuts Collection](https://www.thingelstad.com/collections/shortcuts/)._
