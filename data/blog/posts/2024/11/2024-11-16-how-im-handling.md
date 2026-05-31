---
microblog_id: 4439549
url: "https://www.thingelstad.com/2024/11/16/how-im-handling.html"
title: "How I’m handling Twitter embeds from deleted accounts"
published: "2024-11-16T17:14:44+00:00"
post_kind: post
categories: []
---

I’m seeing a lot of people that I was connected with on <strike>Twitter</strike> X deleting their profiles. This actually ends up having an impact on my blog because of embeddings. When I left Twitter years ago I exported my archive and [imported it into my blog](https://www.thingelstad.com/2017/05/06/importing-tweets-from.html). Over the years I've merged that content in as "native" as I can. The reality is that Twitter status updates are often very different than a blog post.

There were a number of retweets that I did that I also migrated. When I did those I used [Hugo](https://gohugo.io)'s ability to embed a Tweet using a [shortcode](https://gohugo.io/content-management/shortcodes/). That results though in build errors if those Tweets become unavailable. I get an error that looks like this (I anonymized the identifiers).

`Error: ERROR Failed to get JSON resource "https://publish.twitter.com/oembed?dnt=false&url=https%3A%2F%2Ftwitter.com%2Fusername%2Fstatus%2F123456789123456": Failed to retrieve remote file: Forbidden, body: "{\"error\":\"Sorry, you are not authorized to see this status.\",\"request\":\"\\/oembed?dnt=false&url=https%3A%2F%2Ftwitter.com%2Fusername%2Fstatus%2F123456789123456\"}"`

I debated how to approach this and decided that I would delete my references to these as well. That seems like the best way to honor the original authors intent. They deleted that content themselves. The result is that I've deleted several historical posts on my blog in recent days as people have deleted their accounts on X. Mostly those posts had no meaningful content from me.
