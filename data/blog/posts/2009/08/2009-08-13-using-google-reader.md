---
microblog_id: 1075448
url: "https://www.thingelstad.com/2009/08/13/using-google-reader.html"
title: "Using Google Reader"
published: "2009-08-13T05:00:00+00:00"
post_kind: post
categories: []
---

I was excited to read about recent [enhancements to Google Reader, particularly the "Send
to..."](http://googlereader.blogspot.com/2009/08/flurry-of-features-for-feed-readers.html) feature that allows you to post items from [Google Reader](http://www.google.com/reader/) into
[Facebook](http://www.facebook.com/), [Twitter](http://twitter.com/), [Delicious](http://www.delicious.com/) and many other sites.

But, I wanted to send things to [WordPress](http://www.wordpress.org/) and that isn't in the list. However, the Reader team smartly left a way for you to manually add your own "Send to..." destinations. I considered this and thought it may match well with WordPress built-in "Press this" function. And it does!

You cannot use the "Press this..." function directly in Reader as it is Javascript and Reader wants a URL. But, you can just post directly to `press-this.php`. The URL is (make sure to replace with your own domain name!)

`http://www.YOURDOMAINHERE.com/wp-admin/press-this.php?u=${url}&t=${title}&s=${source}&v=2`

Google Reader will substitute the items in braces. Now you have an easy "Send to..." option from Google Reader.

To create this go to Google Reader and open Settings. Select the "Send To" tab and click on the "Create a custom link" button. Then fill it in similar to this picture:

![google-reader-send-to-for-wordpress2](https://www.thingelstad.com/uploads/2020/6aa4cb1434.png)

Also, if you want the nice WordPress icon next to the link put the Icon URL in as

`http://s.wordpress.org/favicon.ico?3`

Have fun blogging!
