---
microblog_id: 1075016
url: "https://www.thingelstad.com/2011/11/20/move-to-linode.html"
title: "Move to Linode"
published: "2011-11-20T06:00:00+00:00"
post_kind: post
categories: []
---

This website (and all the other websites I run) should all be running **much** faster now. This weekend I flipped everything from my previous VPS at [Slicehost](https://www.slicehost.com/) to a new instance at [Linode](https://www.linode.com/).

There is a ridiculous amount I could write about the move, and I'll try to share what I think is most helpful to others. In general I can say that the Linode hosts are a lot faster than the Slicehost instance I had. Doing basic Linux stuff was 2-3 times faster on Linode than on Slicehost.

<img src="https://www.thingelstad.com/uploads/2020/0604f0c284.png" alt="Bar chart showing PHP cache hits at 99.9% (1588335) versus misses at 0.1% (2234), with green and brown bars respectively." style="max-width: 219px; " />

My new setup is also a lot faster due to how I deployed [WordPress](https://wordpress.org/) and [MediaWiki](https://www.mediawiki.org/). I'm now running everything on [nginx](https://nginx.com/) instead of [Apache](http://www.apache.org/). I'm also serving all my PHP out of php5-cgi instead of mod\_php. Perhaps even more importantly I got all of my wiki and blog instances running under one PHP install for MediaWiki and WordPress. As a result, the [APC](https://php.net/manual/en/book.apc.php) module for PHP can do its job right. I'm now getting 99.9% PHP cache hits.

With all that said I fully expect I may have a thing or two not working right now. If you see anything broken a comment or email would be great.
