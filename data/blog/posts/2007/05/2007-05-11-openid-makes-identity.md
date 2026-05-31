---
microblog_id: 1076054
url: "https://www.thingelstad.com/2007/05/11/openid-makes-identity.html"
title: "OpenID Makes Identity Easy"
published: "2007-05-11T05:00:00+00:00"
post_kind: post
categories: ["Minnestar"]
---

<img src="https://www.thingelstad.com/uploads/2020/5e87cc09d1.gif" style="width: 107px; float: right; margin-left: 10px; " />

I've been using [OpenID](http://www.openid.net/) for a couple of weeks now, and I'm really **impressed**. I created an OpenID identity on [MyOpenID](http://www.myopenid.com/) a few months ago, but there was nothing to use it with so it just sat. In these few months though, there has been a lot of progress! Recently [David Hansson](http://www.loudthinking.com/) was blogging about OpenID which peaked my interest again (I asked him about it in the [interview with him at Minnebar](https://www.thingelstad.com/2007/05/09/minnebar.html) --fast forward to 44:13 minutes). There are now a decent number of web properties that are using OpenID to manage authentication. **What is OpenID?**

I'm not going to write this when others have done it so well. [Excerpt from
ReadWriteWeb](http://www.readwriteweb.com/archives/microsoft_openid_five_key_takeaways.php):

> OpenID is an open, decentralized, free framework for user-centric digital identity. It is aimed at solving the problem of Web single sign-on. How does the problem of web single sign-on affect you? Well, if you struggle with keeping track of different usernames and passwords at different websites where you have an account, OpenID can help you. With OpenID you will be assigned a standard username (typically a URL or an i-name, similar to an email address) that you can use on all sites that support OpenID.

There is a wealth of information at the [OpenID](http://openid.net/) "[How it works](http://openid.net/about.bml)" page as well. If you insist on not wanting to read anything (and you likely wouldn't have made it this far in this post if that were the case), [Simon Willison](http://simonwillison.net/2006/Dec/22/screencast/) did a nice [screencast on using OpenID](http://simonwillison.net/2006/openid-screencast/) that is worth watching.

### Where is the momentum?

OpenID is getting a surprising amount of support. There are now [over one hundred sites](https://www.myopenid.com/directory), including some fairly large ones, that allow OpenID authentication. The list is growing daily with sites like [Digg announcing they will be using OpenID](http://www.techcrunch.com/2007/02/20/kevin-rose-at-fowa-digg-adopts-openid/). [Microsoft](http://www.microsoft.com/) is working to make [OpenID and CardSpace work together](http://www.readwriteweb.com/archives/microsoft_openid_five_key_takeaways.php). [AOL](http://www.aol.com/) has adopted OpenID and [every AOL account now has OpenID capability](http://dev.aol.com/aol-and-63-million-openids) (all 63 million of them!). [Sun](http://www.sun.com/) has [announced support of OpenID](http://radar.oreilly.com/archives/2007/05/sun_supports_op.html). [Mozilla](http://www.mozilla.org/) has also announced that [Firefox 3.0 will support OpenID](http://radar.oreilly.com/archives/2007/01/firefox_30_requ.html). I'm a bit mystified at Google's complete [silence on this topic](http://blog.javia.org/?p=44).

That is a lot of activity, and much more momentum than was ever enjoyed by passed failed attempts at single-sign-on on the web like Microsoft Passport (now [Windows LiveID](https://accountservices.passport.net/)). The fact that OpenID is decentralized, free and open-source gives it a very good chance at making it.

### Cool OpenID Stuff

Once you have an OpenID account using OpenID-enabled sites is a breeze. [Here is my OpenID](http://thingles.myopenid.com/). I can go to any OpenID-enabled site and type in <http://thingles.myopenid.com/> and I'm in. I could even make that my own website URL, but I haven't found a need. Passwords become a thing of the past.

Having a centralized identity also opens up new capabilities. [Jyte](http://jyte.com/) is a website that makes little sense without OpenID. Jyte is like [Everybody Votes for Wii](https://www.thingelstad.com/2007/02/13/everyone-votes-on.html) built on OpenID using the Web. See [my Jyte page](http://jyte.com/profile/thingles.myopenid.com). What makes Jyte compelling is that identity is shared across OpenID sites. So, if I gave permission, another website could query Jyte, using my OpenID URI, and retrieve my information from Jyte to personalize my experience at the new site. Very cool! *(And a little scary.)*

[ClaimID](http://claimid.com/) is another interesting idea around identity management. It uses the centralized identity of OpenID to allow you to [claim ownership of URL's](http://claimid.com/account/help). See [my ClaimID page](http://claimid.com/thingles). It combines OpenID federation, with the [MicroID](http://www.microid.org/) (get the [Wordpress plugin](http://www.richardkmiller.com/blog/archives/2006/03/microid-plugin-for-wordpress)!) [microformat](http://microformats.org/) (a topic worthy of another post) to allow you to verify ownership of URL's and centralize this in one federated OpenID-enabled identity.

### Hopes

I hope that OpenID continues to get adoption. Identity management is a big problem on the web, and everyone has a myriad of passwords. Additionally, it gets really annoying to have to retype your name, email, address, etc. OpenID has a great framework for selectively controlling the distribution of that information. It removes so much of the friction from both signing up for a new service, and returning to use it in the future.
