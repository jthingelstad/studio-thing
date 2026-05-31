---
microblog_id: 1075820
url: "https://www.thingelstad.com/2008/08/17/wordpress-iphone-application.html"
title: "WordPress iPhone Application and RSD Link"
published: "2008-08-17T05:00:00+00:00"
post_kind: post
categories: []
---

I [posted before from the WordPress iPhone
application](https://www.thingelstad.com/2008/07/22/wordpress-for-iphone.html)
when it was released. Its pretty nifty. When they upgraded it to 1.1
though I could no longer get it to work on my blog anymore. I was mighty
confused since it worked for every other blog that is hosted on my
server, but not mine.

I finally [did some digging into the
problem](http://iphone.trac.wordpress.org/ticket/48#comment:3) and for
some reason my blog wasn't outputting an RSD link which is needed for
the application to find the XML-RPC endpoint. A quick
`grep -R rsd` found the issue.

`remove_action('wp_head', 'rsd_link');`

That was hiding out in my functions.php file. I removed it and I'm
cooking along with the [iPhone WordPress
application](http://iphone.wordpress.org/) again. Beware if your theme
does something similar. Found and fixed just [before leaving
town](https://www.thingelstad.com/2008/08/14/summer-of-love.html)!
