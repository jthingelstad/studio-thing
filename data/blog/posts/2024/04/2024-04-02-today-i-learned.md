---
microblog_id: 3947151
url: "https://www.thingelstad.com/2024/04/02/today-i-learned.html"
title: "Today I Learned: DNS and Wildcard Records"
published: "2024-04-03T02:11:23+00:00"
post_kind: post
categories: []
---

One of my favorite features of Fastmail is mail routing. I can use that to create any number of ad hoc email addresses in the format of `anything` at `jamie.thingelstad.com`. I've been using this feature for a while and to set it up you create a wildcard `MX` entry for your domain pointing to Fastmail. This way it works for all users of your domain. A couple of weeks ago these addresses stopped working though and I had no idea why.

I actually raised the issue with Fastmail support and they confirmed that there was no `MX` entry for `jamie.thingelstad.com`. They then asked if I had setup any `CNAME`s or `A` records recently for that name. Then it hit me, I had recently created a `TXT` entry for `jamie.thingelstad.com`. 

It turns out the second that there is any record of any type on a name you no longer get the benefit of the wildcard entry. I created the specific `MX` entries for `jamie.thingelstad.com` and everything started to work just as it should.
