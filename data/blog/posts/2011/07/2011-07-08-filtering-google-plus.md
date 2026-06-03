---
microblog_id: 1075099
url: "https://www.thingelstad.com/2011/07/08/filtering-google-plus.html"
title: "Filtering Google Plus Notification emails"
published: "2011-07-08T05:00:00+00:00"
post_kind: post
categories: []
---

It sure didn't take long for Google Plus to start filling my mailbox with email notifications of all sorts of actions. Luckily, its super simple to filter Google Plus notifications. Just capture any email matching...

`[@plus.google.com](http://plus.google.com)`

and send it to a folder.

If you use [Sieve](http://en.wikipedia.org/wiki/Sieve_(mail_filtering_language)) like I do, the rule to match is...

```
header :contains "From" [
    "@plus.google.com"
]
```

Much better.
