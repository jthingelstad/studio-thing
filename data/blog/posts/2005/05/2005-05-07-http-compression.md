---
microblog_id: 1076325
url: "https://www.thingelstad.com/2005/05/07/http-compression.html"
title: "HTTP Compression"
published: "2005-05-07T05:00:00+00:00"
post_kind: post
categories: []
---

I finally got HTTP compression working on content that matters -- like
ASPX pages. It looks like pages are compressing about 4:1 or more. This
should mean much faster download times since my broadband connection is
my most limiting issue. I found [some excellent instructions for doing
this](http://www.wwwcoder.com/main/parentid/170/site/3669/68/default.aspx).
You need to edit the IIS6 metabase for compression to work as you would
want and this article explains it will.

I also moved [Road Sign Math](https://www.roadsignmath.xyz) to it's own
web server now so it is isolated and I also enabled compression on it.

Let me know if you notice faster responses when you are browsing our
site.
