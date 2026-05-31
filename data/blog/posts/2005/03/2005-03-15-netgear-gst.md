---
microblog_id: 1076352
url: "https://www.thingelstad.com/2005/03/15/netgear-gst.html"
title: "NetGear GS716T"
published: "2005-03-15T06:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/71dcf73fbb.gif" style="width: 120px; float: right; margin-left: 10px; " />

I've written on our site about some of the trials and tribulations I had
with my previous gigabit switch. I had purchased a cheap SMC 8508T
switch a while back, [it
died](https://www.thingelstad.com/2004/12/19/trouble-in-gig.html), I had to
RMA it and I've been having very, very odd problems lately. I finally
decided enough is enough and I decided to get a switch that I could
manage at some level. I looked at a number of switches and the [NetGear
GS716T](http://www.netgear.com/products/details/GS716T.php) seemed to be
a good compromise between price and performance.

I plugged the switch in tonight, just unplugged everything from the
current switch to the new one. Everything came up no problem. The 716T
is a smart switch but it doesn't require any configuration, out of the
box it will just operate as a dumb switch. After plugging in and
verifying everything was working fine I installed the administrative
software and it immediately found the switch and I was able to configure
it for the network.

Physically the box is stable. Power supply is internal so no annoying
power brick. Good compliment of lights -- however I find the use of
green v. yellow LED for different speeds impossible to detect on the
device. Luckily I don't really care since the web interface gives all
this information and more. The two fans built into the unit are loud
though. I wouldn't want this thing where you would care about ambient
noise. Rack mount ears included and it will be very stable in a rack.

The administrative interface is basic, but covers all the bases. I
haven't figured out the details of the VLAN support, trunking, QoS, etc.
Not sure I even need it but will be fun to play with. I'm eagerly
looking forward to the next firmware upgrade so I can get jumbo frames
and basic SNMP support (need to have [MRTG](http://www.mrtg.org/) graphs
on all the ports of course!).
