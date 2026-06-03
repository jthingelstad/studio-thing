---
microblog_id: 1074916
url: "https://www.thingelstad.com/2013/04/20/display-mediawiki-job.html"
title: "Display MediaWiki job queue size inside your wiki"
published: "2013-04-20T05:00:00+00:00"
post_kind: post
categories: []
---

I wanted to find an easy way to show the current size of the [MediaWiki job queue](https://www.mediawiki.org/wiki/Manual:Job_queue) on [WikiApiary](http://wikiapiary.com/wiki/Main_Page). When you make changes to templates that are used on thousands of pages the queue can get backed up and it's nice to have an easy way to keep an eye on this. The job queue is even one of the data points WikiApiary tracks and graphs. But I wanted something that was as close to realtime as possible. It wasn't hard to do. This solution uses the [External Data](http://www.mediawiki.org/wiki/Extension:External_Data) ([see WikiApiary usage page](http://wikiapiary.com/wiki/Extension:External_Data)) extension.

First we need to get the data. Let's start by calling the siteinfo API method. The magic words are used to make this generic, and this **should** result in the right URL. If you are using a protocol-relative server setting you will have to modify this.

```
{{#get_web_data: url={{SERVER}}{{SCRIPTPATH}}/api.php?action=query&meta;=siteinfo&siprop;=statistics&format;=json
  | format=JSON
  | data=jobs=jobs}}
```

Now External Data has done the work and the value is stored for us. Now we get it by simply calling:

`{{#external_value:jobs}}`

I like to put that in a style so it's big and obvious.

If you're thinking ahead you'll now be saying "Yeah, that's neat, but it will be cached in MediaWiki for a hours!". Yes, it will be unless you add a `__NOCACHE__` directive to the page and use the [MagicNoCache](https://www.mediawiki.org/wiki/Extension:MagicNoCache) extension. This extension allows you to disable the MediaWiki cache on a page-by-page basis, very handy.

If you wanted to use this in multiple places you could even put an `<onlyinclude>` around it and transclude the job queue size in other pages, however I would be cautious about that if using the `__NOCACHE__` directive as well.
