---
microblog_id: 1075267
url: "https://www.thingelstad.com/2010/12/14/omnifocus-and-sync.html"
title: "OmniFocus and Sync Server Possibilities"
published: "2010-12-14T06:00:00+00:00"
post_kind: post
categories: []
---

I often like to dream that I get to wave a magic wand and influence the future product plans of software that I use. I've been a constant user of [OmniFocus](https://www.omnigroup.com/omnifocus/) since the very first release on the Mac. I jumped right in when the [iPhone version](https://www.omnigroup.com/omnifocus/#literally-everywhere) came out and eagerly grabbed the [iPad version](https://www.omnigroup.com/omnifocus/#literally-everywhere) when it was released.

<img src="https://www.thingelstad.com/uploads/2020/f22ff9784a.png" style="width: 200px; float: right; margin-left: 10px; " />

A while back Omni started to host their own Omni Sync Server for OmniFocus. Before that, you had to use [MobileMe](http://www.me.com/), [WebDAV](http://en.wikipedia.org/wiki/WebDAV) or some other wonky stuff. I used MobileMe for a long time to sync multiple instances of OmniFocus on different Macs as well as my iPhone. I've had as many as five separate installs of OmniFocus running and synchronizing and OmniFocus has done a great job making it all seamlessly work.

When the [Omni Sync Server](https://www.omnigroup.com/sync/) was released it made my head buzz with a handful of things that I really wished that I could do with it. Let me take the three ideas that I can't get out of my head and share them with some hope that [Ken Case](https://twitter.com/kcase) and the Omni team will think they are awesome and run with it. :-)

### OmniFocus for Web

Since my OmniFocus data is on the Omni Sync Server, I would really like to have a HTML browser-based version of OmniFocus that I can get to from any web browser and manage tasks. Why? There are a few reasons.

<img src="https://www.thingelstad.com/uploads/2020/c5099e0d8d.gif" style="width: 200px; float: right; margin-left: 10px; " />

Even though I have OmniFocus on my Macs, my iPhone and my iPad there are still times that I'm at a computer that isn't mine and I would really like to get a full desktop-like experience to work on some stuff.

With that being said, I think the biggest reason to do this would be to reach non-Mac users. The iPhone and iPad versions of OmniFocus are awesome, but I would hesitate to recommend it **only** on those devices. I have friends that use Windows and if there was a web version it would give them a place to go during the workday and hammer away on things.

This could also turn into the hub for managing devices that you are synchronizing with, and a wonderful way to manage any data inconsistencies that may pop up. It could also be a great partner to OmniFocus on all platforms to host documents in the cloud for access anywhere.

### Push Notifications

When iOS 4.0 came out OmniFocus immediately started supporting local notifications, which was a step in the right direction. However, it drives me crazy. Here is the problem.

Assume I have a task due at 4:30p and I do it at 2:00p on my Mac. I switch over to OmniFocus (which is open all the time) and mark the task as complete. A couple of hours later I'm getting ready to go and my iPhone is displaying an alert because I didn't get the task done. Since I haven't opened OmniFocus on my iPhone and done a synchronize it didn't know this alert wasn't correct, the task is completed.

I really think that [Omni Group](https://www.omnigroup.com/) needs to jump in and deal with this using real push notifications. The sync server should be the one to send those notices, and it would have the current state and know that that earlier task has already been completed. There is no need to notify me. This could also be used to dynamically change the badge count to show the real number of tasks due without me even opening OmniFocus. That is another pet peeve. At 9am OmniFocus will say there are 3 tasks to do, when I open it and it walks through the data I really have 14 tasks. I really want the badge number to be right at all times, regardless of when OmniFocus was last launched.

(While at it all of the weird calendar synchronization stuff in OmniFocus could be removed and the server could just host an iCal feed I could subscribe to.)

### Web API

My last big, big hope is to have a web-based API to get access to OmniFocus. OmniFocus is scriptable using AppleScript, but that doesn't work for the types of actions I want to use it with.

My hope here is to be able to merge [cron](http://en.wikipedia.org/wiki/Cron), a bunch of [bash](http://en.wikipedia.org/wiki/Bash_(Unix_shell)), [Ruby](http://en.wikipedia.org/wiki/Ruby_(programming_language)) or [Perl](http://en.wikipedia.org/wiki/Perl_(programming_language)) code along with [curl](http://en.wikipedia.org/wiki/CURL) to create tasks.

Some scenarios:

- I want to have a cron job run on a Linux server, check if security updates are available, and if they are create a task for me to apply them.
- I want to check a handful of websites. So, I create a daily cron job that looks at the websites using curl and detects changes. It then creates a task to look into it.
- I want to take the RSS feed from a Basecamp project and filter it for actions I care about, and then create tasks in OmniFocus.

You get the idea. I think the interface should be simple. Probably should use [JSON](http://en.wikipedia.org/wiki/JSON) to transfer data around. Should support HTTPS. Should allow read and write.

This would be really fun, and I think that the creative solutions built around it would go beyond what anyone imagines now.

### There is more…

Those three things are the big ones that I want out of the Omni Sync Server. There are more things that I would like to be able to do with it.

- The biggest shortcoming of OmniFocus is that there is no sharing. I would like to share tasks with my wife and others. The Sync server could make that happen.
- I **really** would like to see [RSS](http://en.wikipedia.org/wiki/RSS) for tasks. It would be really cool for one person to publish a feed of tasks via RSS and then have the Omni Sync Server subscribe to that feed. Imagine a personal trainer sending 20 clients workout tasks. (Seriously, this could be **huge**.)
- There are a lot of systems that I would like OmniFocus to synchronize with. Basecamp is the big one. I would love to see JIRA there as well. The biggest problem building this stuff is a lack of defined end-point to program to. There is a 3rd party sync service that integrates with Basecamp called [Spootnik](http://www.spootnik.net/). However, I won't do it. It's too much of a commitment to have that be your main sync server. If there was a robust API, developers all over would write synchronization scripts between dozens of services and OmniFocus.

I realize doing any of this would likely mean that OmniFocus would have to stop supporting the other synchronization methods. That doesn't bother me. I would still have the data locally. And the added benefits, particularly with an API, would be huge wins.

That's that. So what do you say Ken Case? OmniFocus 2.0? :-)
