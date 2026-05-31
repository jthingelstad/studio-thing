---
microblog_id: 1075062
url: "https://www.thingelstad.com/2011/08/30/test-post-for.html"
title: "Test Post for RSS Feed"
published: "2011-08-30T05:00:00+00:00"
post_kind: post
categories: []
---

I've seen this problem for a while now where [Google
Reader](http://www.google.com/reader/) isn't getting my RSS feed for
days, and sometimes weeks at a time. I have a theory for why it is
happening and this post is a test for me to see if my fix worked.

### Update

Well, my theory seems to be right. At one point in the past I had setup
[PubSubHubbub](http://code.google.com/p/pubsubhubbub/) for my
[RSS](http://www.whatisrss.com/) feed and a while back I uninstalled it.
No reason really, just wasn't sure I really needed it. I think that
Google Reader had flagged my RSS feed as one that supports PubSubHubbub
and decided that it would not poll it in the future and just wait to get
notified. When I reinstalled PubSubHubbub and I posted this it appeared
in Google Reader in seconds.

Seems that once you advertise that you support PubSubHubbub you should
make sure to continue to support it.

### Update 2

Even the update to this post appeared in Google Reader in seconds. Looks
like my RSS feed is back in business.
