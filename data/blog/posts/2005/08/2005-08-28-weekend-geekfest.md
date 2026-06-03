---
microblog_id: 1076266
url: "https://www.thingelstad.com/2005/08/28/weekend-geekfest.html"
title: "Weekend Geekfest"
published: "2005-08-28T05:00:00+00:00"
post_kind: post
categories: []
---

I spent a bit of time this weekend on my home network. I had a "security incident" about 10 days ago that I had to both clean-up and prevent from happening again. No damage of any significance was done. I had setout on segmenting my network and replacing my ZyWall with a full-blown firewall. I did not end up there as it just turned out to be way too much work to get going. Instead I reinstated all my firewalls on every machine and pruned down the ports. I also put in place blocking rules on my LAN to WAN connection to block certain traffic that *should* never originate from my LAN, like IRC for example. This is a nice step-up, although not as robust as my plans were.

I also reformatted and reinstalled my Linux boxes (victims of said "security incident") with Fedora Core 4. This time I left SELinux enabled and clamped down the firewall more.

I've also been working on reducing my electrical load in the house so I've made all the desktops go to sleep with inactivity. I was able to setup all of my backup scripts to use Wake-on LAN functionality to turn on in the middle of the night, do their housework, and then go back to sleep and stop spinning the electric dial so much. Of course my servers still have to stay on all the time, but this cuts in half the number of machines powered on at times.
