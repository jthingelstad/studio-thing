---
microblog_id: 1074724
url: "https://www.thingelstad.com/2017/11/26/envisioning-a-cloud.html"
title: "Envisioning a Cloud Native Wiki"
published: "2017-11-26T22:37:37+00:00"
post_kind: post
categories: []
---

A few years ago I dove deeply into the wiki ecosystem and learned all about [MediaWiki](#), its plugins and various extensions. I started a wiki to index all of the other wiki's called [WikiApiary](https://wikiapiary.com/wiki/Main_Page). The wiki movement was huge, and it still has a tremendous amount of energy and incredibly devoted users. [Wikipedia](https://www.wikipedia.org), in my opinion, is one of the most amazing creations of the Internet.

However, the wiki movement has hit the skids lately. There was a significant rush of wiki hosting platforms early on, and those mostly didn't work. [Wikia](http://www.wikia.com/) is perhaps an exception however it's driven itself into the hole of fandom in a big way. Sadly many wiki platforms continue to sit on top of ugly PHP code and MySQL databases, with old codebases and arcane syntax.

In recent years email newsletters have seen a resurgence. I'd like to see wikis make a similar revival but for that to happen, we need to have some new energy in the wiki ecosystem. We need a cloud-native wiki solution. What would that look like?

### Cloud Native Wiki

First thing first wikis should enable communities of any size, so the cost of running a wiki needs to be as cheap as possible. A serverless approach seems to make the most sense. If nobody is using the wiki the cost of running it should be no more than the storage, and that can be very cost effective.

-   Store all wiki pages and objects in S3. Store the objects in an
    editable format, something like Markdown, but also store it as HTML
    as well so it can be served directly out of S3. Think of how static
    site generators work.
-   The wiki itself should live in Lambda functions exposed through API
    Gateway. All editing and modifying of objects in the S3 bucket
    should be done via this method.
-   The wiki should be self-managed by a central source to update it.
    Wiki's have a history of being poorly maintained. You should be able
    to create an IAM credential and give the ability for the Lambda
    functions and infrastructure of the wiki to be updated
    automatically.

### Let Millions of Wikis Flourish

Ideally, someone should be able to start a wiki by creating an AWS account and then creating the IAM account for provisioning and updating. That account should then do all the initial setup as well as updating over time.

The content would be held in Markdown files in S3, as well as rendered HTML. This content would be easily mirrored off of S3 so it could be taken somewhere else. If the Lambda functions were all removed, the wiki should still run in static mode with no editing.

If we had this kind of capability, perhaps we could see wikis reenter the landscape for all the good that they can provide.
