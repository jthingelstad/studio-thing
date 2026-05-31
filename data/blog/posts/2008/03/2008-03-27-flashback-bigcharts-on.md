---
microblog_id: 1075905
url: "https://www.thingelstad.com/2008/03/27/flashback-bigcharts-on.html"
title: "Flashback: BigCharts on CNBC"
published: "2008-03-27T05:00:00+00:00"
post_kind: post
categories: ["Videos", "BigCharts"]
---

**Flashback to February 4, 1998!** Here are a couple of videos that I stumbled upon on my machine recently. These are an extraordinary walk down memory lane for me, back to the early days of starting [BigCharts.com](http://www.bigcharts.com/).

We were still very early in the development BigCharts. There were only a dozen or so people in the company. I was sitting at my desk talking to our ISP about getting some more bandwidth. At the time we had a single [T1](http://en.wikipedia.org/wiki/Digital_Signal_1) with a now trivial 1.5 Mbps of bandwidth, about what my cable modem at home does, and only used about a quarter of that. In those days I always had a TV with [CNBC](http://www.cnbc.com/) on in my office and this came on the screen with no warning.

<video controls="controls" playsinline="playsinline" src="https://files.thingelstad.com/posts/2008/bigcharts-on-cnbc-day-1.mp4" width="100%" poster="https://files.thingelstad.com/posts/2008/bigcharts-on-cnbc-day-1.jpg" preload="none"></video>

I sat in my chair stunned in silence, and then hung up on the person I was talking to. At the time we served BigCharts off of a single Sparc 20 clone. The site ran with a clunky combination of [Perl](http://www.perl.org/) and [CGI](http://en.wikipedia.org/wiki/Common_Gateway_Interface) work sitting behind a very early version of [Apache](http://www.apache.org/). With that clip on CNBC an avalanche of people started to come to the site. To be fair, back then that probably meant a couple of thousand. I really don't know how many it was since we didn't even have log analytics back then. Small numbers in 1998. I tried to get onto the server via console and it wouldn't respond. The load average had spiked so high that I couldn't get enough CPU to even get a prompt. We ended up pulling the ethernet cable to kill the traffic just to get onto the machine.

February 4th was a Wednesday. This was the first week that my friend [Chris](http://www.tersteeg.org/) had joined BigCharts. We immediately got everyone together and I sat on the Sparc and figured out what, if anything, we could do. We realized our load average was up over 100 because we were [forking](http://en.wikipedia.org/wiki/Fork_%2528operating_system%2529) Perl processes everywhere. Remember, this was old CGI stuff, no [mod_perl](http://perl.apache.org/) here. So on his third day at work I started handing Chris Perl programs that he translated into C and gave me an executable for. As we replaced each piece the next one fell down, and we repeated the translation process.

After a couple of hours traffic subsided and we had converted enough things to native executables that we were okay. So the next day this video segment aired.

<video controls="controls" playsinline="playsinline" src="https://files.thingelstad.com/posts/2008/bigcharts-on-cnbc-day-2.mp4" width="100%" poster="https://files.thingelstad.com/posts/2008/bigcharts-on-cnbc-day-2.jpg" preload="none"></video>

I love this bit. It is so *quaint*. I love how [Bill Griffeth](http://www.cnbc.com/id/15838137/site/14081545/?site=14081545&site=14081545) gives us a total pass on the site going down. It's just taken as a given, when a lot of people go to a website, the server goes down. Few things highlight so starkly for me how the web has matured over the last decade.

Anyway, obviously with a mere 24 hour gap and being a startup with no real money we had the same issue. A ton of people pointed their browsers at us, the server got overloaded and we had a challenging couple of hours. If I remember right we just let the system ride through it on the second day since we'd already optimized as much as we could in that window.

Shortly after this we started a total revamp of our code. The final stage was a migration to Windows and distributing on multiple servers. But right away we started to push a lot of things that we were doing in CGI/Perl down into Javascript functions on the browser. If only the concept of a [CDN](http://en.wikipedia.org/wiki/Content_Delivery_Network) existed back then that would have helped us a lot too.

Ahh... good times.

PS - Final comment. The "viewer" that sent the note into CNBC was our CEO and Founder, [Philip Hotchkiss](http://www.linkedin.com/pub/0/5b1/a8)!
