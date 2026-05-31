---
microblog_id: 1075473
url: "https://www.thingelstad.com/2009/07/15/fancy-email-signatures.html"
title: "Fancy Email Signatures with hCard Microformat"
published: "2009-07-15T05:00:00+00:00"
post_kind: post
categories: []
---

I recently redid my email signature. I've been using an HTML signature for a while and my friend [Kent](http://www.thetangens.net/) complained to me one day that my emails always wrap odd on the iPhone. I figured out that I had an HTML element with a minimum width around 300 pixels. Fine for a computer, but it made the iPhone mail program scroll - in the worst way possible - horizontally.

I figured since I was going to redo it I would simplify, but also wanted to add some function. So, I decided to make use the [hCard microformat](http://microformats.org/wiki/hcard) in the signature. It wasn't too hard to get right, and it looks normal when viewed but an hCard aware client would see the data markup.

```html
<div style="width: 100%; margin: 14pt 0px; padding: 2px; border-top: 1px #dddddd dashed; font-family: Helvetica Neue, Helvetica, Arial, sans-serif; font-size: 10pt; color: black;" id="hcard-Jamie-Thingelstad-Personal" class="vcard">
    <a style="white-space: nowrap; font-weight: bold;" href="/" class="url fn">Jamie Thingelstad</a>
<div><a href="mailto:jamie@thingelstad.com" class="email">jamie@thingelstad.com</a></div>
<div style="white-space: nowrap;" class="tel">mobile: <span class="value">612-810-3699</span></div>
<div>find me on <a href="aim:addbuddy?screenname=jthingelstad" class="url">AIM</a> <a href="http://twitter.com/thingles" class="url">Twitter</a> <a href="http://www.facebook.com/thingles" class="url">Facebook</a> <a href="http://www.linkedin.com/in/jthingelstad" class="url">LinkedIn</a></div>
</div>
```

I found two tools that helped with this a lot. There is an [hCard creator](http://microformats.org/code/hcard/creator) that helped with figuring out what the structure should look like, and very importantly an [hCard validator](http://hcard.geekhood.net/) that you can pass a code fragment into and it validates and decodes it.

With all that said, I don't think there is a single email client that will honor hCard. But, if one comes along I'm ready.
