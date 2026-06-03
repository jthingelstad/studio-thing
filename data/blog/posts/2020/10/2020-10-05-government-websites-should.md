---
microblog_id: 1199212
url: "https://www.thingelstad.com/2020/10/05/government-websites-should.html"
title: "Government Websites Should be Surveillance Free"
published: "2020-10-06T02:48:05+00:00"
post_kind: post
categories: []
---

Excuse me while I vent for a moment. Today I tried to visit the [State of Minnesota COVID-19](https://mn.gov/covid19/) resource page. I wanted to see what the State of Minnesota had shared recently. However, when I visited the page it was blank. Just a white page.

I run multiple layers of software to block surveillance software on the web. It amazes me that this software blocks about 30% of all requests that my browser attempts to make, and by and large websites I visit are unaffected. Just think about that for a second. <mark>30% of all web activity that my browser goes to offers no value to me, but is instead surveilling me for various other activities.</mark>

Back to the State of Minnesota though, unfortunately their site breaks entirely if you block this surveillance. I tested it and if I paused blocking it worked, enabled blocking and it was a blank white screen again.

<img src="https://www.thingelstad.com/uploads/2020/a950dda69a.png" width="696" height="472" alt="Safari browser on macOS showing a tracker-blocking extension popup listing 7 blocked requests on the Minnesota COVID-19 government website mn.gov/covid19" />

This burns me up because this is _my_ government resource that I want to access, and I do not think that _my_ government should force me to be surveilled by private companies in order to access resources I want as a citizen of my state. I feel the same way when government services are only available via social networks. <mark>There should be no circumstance where I should have to submit to surveillance in order to get access to government information.</mark>

So, what is all this amazing stuff that the State of Minnesota wants to watch me with? Let's take a look.

First, we have Google Tag Manager which is Google's bundled thing to put nearly anything into a website. Google is all over the web and follows us nearly everywhere I go. I especially dislike the idea of Google seeing what resources I’m looking at from government services. That could lead to some terrible profiling activities. Plus, Google has nothing to do with Minnesota and I don't see why I need to send my data to a company in California to get information from Minnesota.

<pre>Registrant Organization: Google LLC
Registrant State/Province: CA
Registrant Country: US</pre>

Next we have SiteImprove! Now we aren't just getting another state involved but an entire separate country. It turns out that a company in Denmark is also needed to get me my COVID-19 information from Minnesota.

<pre>Registrant Organization: Siteimprove AS
Registrant State/Province: 
Registrant Country: DK</pre>

Okay, deep breaths. Now we add `cdn.perfdrive.com`, which I've never heard of. They don't seem to have an easily available website. Their domain registration is hidden behind a legal proxy, so I have no means to identify who this company is that is getting my data.

Then we have something called `btstatic.com`. The domain’s whois information shows some entity in Chicago, IL but then an administrative contact in the United Kingdom. With Denmark already in the mix we have a full global action here for me to talk to my State Government.

<pre>Registrant Organisation: Signal Digital, Inc.
Registrant Street: 222 N. LaSalle St.
Registrant Street: Suite 1600
Registrant City: Chicago
Registrant State/Province: IL
Registrant Postal Code: 60601
Registrant Country: US

Admin Organisation: Safenames Ltd
Admin Street: Safenames House, Sunrise Parkway
Admin Street: Linford Wood
Admin City: Milton Keynes
Admin State/Province: Bucks
Admin Postal Code: MK14 6LS
Admin Country: UK</pre>

Rounding out the fun we also have two additional California companies that are getting my data too. Apparently we are **optimizing** via `optimizely.com` and **amplifying** via `amplitude.com`! Ugh.

<pre>Registrant Organization: Optimizely
Registrant State/Province: California
Registrant Country: US

Admin Organization: Amplitude
Admin State/Province: CA
Admin Country: US</pre>

So to recap, in order for me to get COVID-19 information from the State of Minnesota I need to give my data to three companies in California, one in Denmark, one in Chicago or the UK, and a final one that I have no legal way of identifying.

<mark>It should be a requirement that government resources on the web are available without surveillance.</mark> Citizens should not be forced to send there data all over the globe to get something that is essential to the services expected.
