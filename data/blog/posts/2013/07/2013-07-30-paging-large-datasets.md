---
microblog_id: 1074910
url: "https://www.thingelstad.com/2013/07/30/paging-large-datasets.html"
title: "Paging Large Datasets in Semantic MediaWiki"
published: "2013-07-30T05:00:00+00:00"
post_kind: post
categories: []
---

I've been working with [Yaron Koren](http://yaronkoren.com)'s new [Miga](http://migadv.com) project to provide an offline, mobile optimized way of accessing the nutrition data in [Wikinosh](http://wikinosh.com/). [It works pretty well!](http://wikinosh.com/miga/#) However, we hit a couple of walls trying to get the 20,000+ food items in Wikinosh exported for use in Miga. If you are trying to page thru large data sets in [Semantic MediaWiki](http://semantic-mediawiki.org/wiki/Semantic_MediaWiki) read on.

### Large Offsets

The best way to do this is to use queries of 500 items at a time and use incrementing offsets to retrieve each set of rows. This works really well and is easy to code. However, when you run this the first time if you have over 5,000 records you will notice that your while loop will never finish. Very odd. When you look at the data you will also see that after a few thousand rows, the first set of data just repeats over and over and you never reach the end.

A quick look in SMW\_QueryProcessor.php on line 611 shows this:

```
$params['offset'] = array(
    'type' => 'integer',
    'default' => 0,
    'negatives' => false,
    'upperbound' => 5000 // TODO: make setting
 );
```

Now that makes sense. It turns out that if your offset value is greater than 5,000 it won't be used. To make matters worse, this doesn't generate an error it simply ignores the offset. Ugh! The "TODO" is still a to do, there is no setting for this. If your working with large data, you will want to increase the offset to something large enough to accommodate your largest set. Since Wikinosh has 21,000+ items, I set it to `30000`.

### Query Max

Now that you have your offset changed you can go ahead and run your export again. It will chug along and then hit 10,000 records and stop. What? Sure, you increased your offset however you probably still have the default `$smwgQMaxLimit` value of `10000`. So, if your offset is greater than the query max, you get 0 rows and your done. This setting **does** have a way to override, set `$smwgQMaxLimit = 30000;` in your LocalSettings.php and you will be ready to go.

With these two changes in place, I can now easily page through 500 records at a time and get everything out exactly as I expect.

There are currently two bugs open on these behaviors. Check those for current status of these settings: [SMW Ask query offset has a hardcoded limit](https://bugzilla.wikimedia.org/show_bug.cgi?id=49203) and [SMW Ask query offset should error if maximum offset is exceeded](https://bugzilla.wikimedia.org/show_bug.cgi?id=52137).
