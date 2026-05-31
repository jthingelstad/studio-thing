---
microblog_id: 1076041
url: "https://www.thingelstad.com/2007/06/01/going-offline-with.html"
title: "Going Offline with Google Gears"
published: "2007-06-01T05:00:00+00:00"
post_kind: post
categories: []
---

I just spent a little while getting caught up on a variety of sites with
[Google Reader](http://reader.google.com/). Reader is my RSS tool of
choice. This isn't all that special, except that I did it while sitting
on an airplane.

Last night Google released the first "developer release" (alpha?) of
[Google Gears](http://gears.google.com/), and along with it Google
Reader got a revision to allow you to go offline using Gears. The
experience was pretty amazing. Reader works just as you would expect it
to. You launch your web browser, go to the Reader URL and instead of the
expected error since your not online, you actually get the site but in
offline mode.

This is a first release for Reader using the offline capability so it's
a little overly modal (either offline or not) and some features are
frustratingly unavailable, particularly marking all items read. To my
surprise sharing items is available.

Google Gears, the technology that makes this all possible, provides a
nice suite of features to make this all work. I'm assuming that the
Googleplex is hard at work on making an offline version of
[GMail](http://www.gmail.com/), it's the most obvious next candidate. I
did a little poking around the developer documentation for Gears and I
was really excited to see that all the hooks are there for 'sometimes
offline' applications. With a little bit of ingenuity we should see web
applications that seamlessly go online and offline as needed. I'd love
to see this in a number of tools -- all the [37
Signals](http://www.37signals.com/) applications,
[Wordpress](http://www.wordpress.org/), [Google
Calendar](http://www.google.com/calendar).

I think this is a big moment. The Internet is nearly pervasive, but
there are times when it may be unavailable. The biggest net benefit of
technology like Gears may be in making applications much more resilient
to transient network failures -- in addition to the offline experience.

It will be worthwhile to keep a close eye on this space.

### Update

I used this on the flight back with a lot more unread items
and it again worked great. Going offline took more time since there was
more data. The lack of a mark all as read feature in offline Reader is a
real pain though.

### Update 2

I tried getting this going in Firefox on Vista and the
installer fails. The Mac OS X Firefox install is a breeze and is just a
browser plugin. The Windows install is a separate installer. YMMV.
