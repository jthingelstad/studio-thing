---
microblog_id: 1076307
url: "https://www.thingelstad.com/2005/06/11/hardcore-geeking.html"
title: "Hardcore Geeking!"
published: "2005-06-11T05:00:00+00:00"
post_kind: post
categories: []
---

I've been having fun with what I expect will be my last weekend of hardcore geeking with my gear at home for a while. Once Baby Thingelstad arrives I'll have more important things to do!

This weekend I jammed on two tools. First is [Snort](http://www.snort.org/), which I have setup in a network intrusion detection mode. I now have one of my [Fedora](http://www.redhat.com/fedora/) boxes listening on an unnumbered interface to all traffic on my gateway. Snort, with the appropriate ruleset, watches *all traffic* over the wire and takes note of anything suspicious. Snort then logs this to a [mysql](http://www.mysql.com/) database and I'm using [BASE](http://sourceforge.net/projects/secureideas/) to review the information. BASE is nothing to get excited about, but it seems to be the best out there.

I am getting some interesting information out of this rig. I'm pretty amazed at how many times [SQL Slammer](http://www.snort.org/pub-bin/sigs.cgi?sid=2003) is **still** hitting me. It tries to get to me about every 20 minutes. [Code Red](http://www.snort.org/pub-bin/sigs.cgi?sid=1256) is less active than it was before, but it's still out there. Perhaps oddest of all is whoever is at [hammurabi.acc.umu.se](http://hammurabi.acc.umu.se/) who is hitting Road Sign Math with a [large ICMP packet](http://www.snort.org/pub-bin/sigs.cgi?sid=499) on a seemingly random interval all day.

The other tool I got going this weekend is [Cacti](http://www.cacti.net/). Cacti is a better (I think?) and easier to use (without a question) [SNMP](http://www.snmp.com/) graphing tool than [MRTG](http://people.ee.ethz.ch/~oetiker/webtools/mrtg/). I'm going to leave MRTG and Cacti running in parallel probably for ever. Some things I like better in MRTG than Cacti. Cacti uses [RRDTool 1.2](http://people.ee.ethz.ch/~oetiker/webtools/rrdtool/) (as opposed to 1.0) and generates these super nice images with anti-aliasing and robust font support (static image for example, [as compared to](https://www.thingelstad.com/2005/05/21/fun-with-mrtg.html).

<img src="https://www.thingelstad.com/uploads/2020/015c42b19c.png" alt="Network traffic graph for gateway IP 24.123.126.42 on enet1, showing bits per second over a 24-hour period with several traffic spikes.">

I'd share access to these tools with you like I do with MRTG and my web logs but they require logins and I also don't know that I want people being able to see attack alerts my intrusion detection system is throwing. You can admire the login pages from the links at the bottom of the page. As a side benefit of this work I've now designated a Linux server as a first-class citizen in my server setup and can now deploy other packages on it in the future if I want.
