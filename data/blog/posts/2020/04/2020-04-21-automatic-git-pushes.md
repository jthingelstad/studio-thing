---
microblog_id: 1077261
url: "https://www.thingelstad.com/2020/04/21/automatic-git-pushes.html"
title: "Automatic Git Pushes with Gitwatch"
published: "2019-06-30T03:25:00+00:00"
post_kind: post
categories: []
---

I've been using [blot.im](https://blot.im/) to publish my websites for a while. Originally Blot only used Dropbox to manage content for your website, but it now supports `git` and that is my preference. One of the things I haven't liked though is having to do git commands all the time as I do things on my blog. Then I found [gitwatch](https://github.com/gitwatch/gitwatch) and it is perfect for this use case.

Gitwatch watches a folder and anytime something changes it automatically commits it and optional pushes it to a remote. Using gitwatch I can set it running in the background and then do whatever I want with my website and it updates automatically in the background. Pretty great!
