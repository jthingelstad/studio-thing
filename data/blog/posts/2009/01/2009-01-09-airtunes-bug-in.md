---
microblog_id: 1075712
url: "https://www.thingelstad.com/2009/01/09/airtunes-bug-in.html"
title: "AirTunes Bug in Apple TV 2.3"
published: "2009-01-09T06:00:00+00:00"
post_kind: post
categories: ["Family"]
---

I was doing some work on [my Apple TV's](https://www.thingelstad.com/2007/12/21/all-in-on.html) today, swapping out hard drives, and at the same time we've had some painting going on so my 802.11n network has been offline. I got done upgrading the Apple TV and plugged it into ethernet to do an initial sync. Afterwards I put it upstairs where it normally sits on an 802.11n wireless network, but today it's not connected to anything. That was fine since I wanted to test playing local content.

Mazie wanted to watch a quick show so I fired that up and it worked great, no issues. I decided then to play some music and hit a wall. The Apple TV refused to play any music or audiobooks. At first I thought it was something with [FairPlay](http://en.wikipedia.org/wiki/FairPlay), even though that made no sense, but I couldn't even play MP3 files I had ripped off of my own CD's. Something was amiss.

It hit me then that this Apple TV typically connects to the [AirTunes](http://en.wikipedia.org/wiki/AirTunes#AirTunes) destination for the Living Room, and that with no network connection it wouldn't be able to see that. **Bug!** I tested it out and verified that this is indeed a bug in Apple TV 2.3.

<img src="https://www.thingelstad.com/uploads/2020/da782428e4.jpg" style="max-width: 290px; " />

If you have your Apple TV set to play through an AirTunes destination, and you then take the Apple TV off of all networks, it will fail on playback of content that it would typically send to AirTunes (video will work fine since that never goes to AirTunes). Now, what really kills about this bug is that since there is no network the menus have no options to deselect an AirTunes destination. It seemed the only way to get rid of this issue would have been to do a reset, or get it back on a network and deselect the remote speaker destination. Ugly.

I chose to just get it online and deselect the speaker set. Resetting settings would cause me to have to change other things as well. I filed a [bug report with Apple](https://bugreport.apple.com/), \#6484963. Hopefully they will clean this up. It's not a likely scenario, but I could see it happening particularly if you took an Apple TV to a cabin for the weekend and then wanted to listen to music without a network connection.
