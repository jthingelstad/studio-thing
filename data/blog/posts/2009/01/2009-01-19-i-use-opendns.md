---
microblog_id: 1075681
url: "https://www.thingelstad.com/2009/01/19/i-use-opendns.html"
title: "I use OpenDNS, and you should too!"
published: "2009-01-19T06:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/2c9a4e96e3.gif" style="width: 150px; float: right; margin-left: 10px; " />

A few months ago I switched my home network to using
[OpenDNS](https://www.opendns.com/) for domain name lookups. Prior to
that I had typically ran my own DNS server on my home LAN. This was a
near requirement for me because I hosted some of my sites at my house
and I needed to resolve them to private addresses when on the home LAN,
blah. It was annoying. I no longer do that, and no longer need to run my
own DNS, and good riddance.

Note, if you don't know what DNS is, or what name resolution is, you can
probably stop reading now. ;-) If you are interested to learn more the
[DNS page on Wikipedia](http://en.wikipedia.org/wiki/Domain_Name_System)
will get you started. Read it and then proceed. **DNS is to the Internet
like legs shoes are to walking.**

I relied for a bit on Comcast's DNS servers and they were fine but they
didn't give me any added value. I poked around and found OpenDNS and it
looked really promising. I posted on Twitter about it and found a
handful of [friends of mine](http://twitter.com/hadar) that are
[technical rockstars](http://twitter.com/mkortekaas) and had been
happily using it for a long time. I guess I was slow to the
party.

Anyway, after using OpenDNS for a while now I strongly endorse it. I
would go so far as to suggest that anyone with the option of flipping
DNS providers should switch to it. Some reasons.

### Content Filtering

When you start using OpenDNS you create an account and you can manage
how DNS requests should be handled. OpenDNS has a whole set of content
filtering options and everyone should ask it to filter Phishing sites.
Phishing sites have gotten incredibly good, and I love the fact that
OpenDNS will simply not allow a computer on my network to go to a site
marked as a phishing site. This alone is worth the switch.

The options are numerous for filtering. You can be as strict or open as
you like. I think this is a great place to implement this sort of policy
on a home network. No software to maintain, it just works and keeps
working. This is how parental controls and basic Internet safety should
be done.

### Statistics

OpenDNS makes it really easy to get information on DNS requests. You can
get a cool graph like this.

<img src="https://www.thingelstad.com/uploads/2020/44109074d1.png" style="max-width: 500px; " />

Okay, that is cool because it is a graph and all graphs are cool. But it
is also useful. Let's say that you got a virus or spambot on one of your
computers. You would possibly notice a large spike in the number of DNS
requests being issued. Sudden and large changes in that graph indicate
something unusual is going on somewhere.

### Other Stuff

To me this is enough to justify the switch to a wonderful free service.
There are some other things that it does that may be cool. It allows you
to great shortcuts, so in my house if you type "thing"  into a
browser it will turn that into "thingelstad.com" or
"goog" into "www.google.com". Firefox can do that too,
but having it at the DNS level is nifty since it works everywhere
(iPhone, Wii).

It's free, you just create an account and change your router to start
using the OpenDNS servers!
