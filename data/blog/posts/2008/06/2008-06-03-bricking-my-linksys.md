---
microblog_id: 1075857
url: "https://www.thingelstad.com/2008/06/03/bricking-my-linksys.html"
title: "Bricking my Linksys WTR-54GS"
published: "2008-06-03T05:00:00+00:00"
post_kind: post
categories: []
---

Sometimes I really should know better. There are some things you just don't do, like updating firmware on something when you need it right away, or **hacking** the firmware on your travel router, when you are in the first part of a six week road trip!

<img src="https://www.thingelstad.com/uploads/2020/f9f08dd547.gif" alt="Linksys WTR-54GS travel router next to an equals sign, followed by a brick labeled THE BRICK, illustrating the router being bricked." style="max-width: 400px; " />

I've had a [Linksys WTR-54GS](http://www.linksys.com/servlet/Satellite?c=L_Product_C2&childpagename=US%2FLayout&cid=1122062241008&pagename=Linksys%2FCommon%2FVisitorWrapper) for a while now. [I've used it quite a bit](https://www.thingelstad.com/2007/12/04/linksys-wtrgs-making.html). It's nice to get to a hotel that doesn't have wireless and pop the WTR-54GS in and you've got your very own private, secure WiFi network. This is a good thing for our trip since we are traveling with two laptops and two iPhones and WiFi is a must have.

When in Seattle I did some research on hacking the WTR-54GS and putting [DD-WRT](http://www.dd-wrt.com/) on it. This sounded great to me, since Linksys has done a horrible job supporting this device. It is now discontinued so effectively it's dead and DD-WRT gives a great way to put a Linux based system on it and get a ton of additional functionality. Great!

I checked out [the instructions](http://www.dd-wrt.com/phpBB2/viewtopic.php?t=21959) and decided I shouldn't do it. It was too risky. I may need the router at the next stop. If it went wrong, I'd have a brick on my hands. Nope, no way.

Then that just cycled and cycled. I had to. I now knew I *could* hack it and I therefore must. To make matters even better, I would be running the hack from Windows running inside of Parallels on my MacBook Pro. Great -- even more risk. 🙂

I did the hack and everything went really great, until it didn't. The router just died after flashing a new boot-loader on it and I can't get it do to anything. I may be able to bring it back to life with a JTAG cable, but that is a serious amount of work for sometime when I'm back at home. Lesson learned, should have left it alone.

Of course the hotel we stayed at for [RailsConf](https://www.thingelstad.com/2008/06/03/railsconf-recap.html) lacked WiFi, and my brick didn't do any good.
