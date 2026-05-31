---
microblog_id: 1076302
url: "https://www.thingelstad.com/2005/06/24/stopping-trackback-spam.html"
title: "Stopping TrackBack Spam with DotText"
published: "2005-06-24T05:00:00+00:00"
post_kind: post
categories: []
---

I've seen a huge increase in trackback spam to my sites lately. It's now reached hundreds a day. I thought this was one or two hosts so I added a rule to snort to capture trackback spam and found it was coming from nearly all unique IP addresses. I'm guessing this is being propogated via spyware that is sitting on unsuspecting peoples computers. I couldn't just block this at the router like I do with feedback spam since it was coming from a variety of sources.

I did a quick search after a failed attempt at stopping this with [ISAPI URL rewriting](http://www.isapirewrite.com/) because it cannot see POST data. However, [a developer in Ireland has solved this problem and been kind enough to share his solution](http://briandela.com/blog/archive/2005/06/17/500.aspx). I just installed it and am waiting to verify everything works well. One concern I have is that his solution is built against DotText 0.95.2004.102 and I'm running 0.95.2004.111. The 111 build was a bug fix build, and the last one that I know of, issued by the author to fix some API issues. So far the `Dottext.Framework.dll` file seems to work fine intermixed with the other version, but I'm not positive yet.

While typing this I got my first spam alert, check it out

> Spam has been detected!!!
>
> Title: black jack  
> URL: BLAHBLAH  
> IP Address: 218.244.225.180  
> Excerpt:
>
> Take your time to visit some helpful info in the field of \<A href="URL REMOVED"\>vegas casinos\</A\>

Looks like the detection part is working! Provided I don't have anything break I'm going to be a much happier blogger.
