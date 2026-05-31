---
microblog_id: 1077253
url: "https://www.thingelstad.com/2020/04/21/jsonfeed-on-blot.html"
title: "JSONFeed on Blot"
published: "2019-02-05T05:00:00+00:00"
post_kind: post
categories: []
---

I've been enjoying [Blot](https://blot.im/) a lot. I've enjoyed its approach to blogging. There is plenty of power there, and it’s dead simple to add new content. I've now moved most of my websites to Blot, and it supports [RSS](https://en.wikipedia.org/wiki/RSS) automatically, but I also wanted to support [JSONFeed](https://jsonfeed.org). When I tried to set that up I could not make it work. I hit a brick wall 🧱 with the [Mustache templates](http://mustache.github.io) that Blot provides, with no ability to safely encode HTML into JSON. I sent an email to David who runs Blot. He replied right away that he was going to add something to make this work. He sent  me an email today to let me know he added a `{{#encodeJSON}}`  capability. I plugged it into my view and it worked like a charm.

I've spent a bit of time making sure this template works as it should and I think I got it. If you would like to add support for JSONFeed to your Blot site, you can create a new view in a custom template, I used the name `jsonfeed.json`. Beware that you cannot use the same basename for two different views, so you cannot make `feed.xml` and `feed.json` for no good reason. For now, use a different name.

```
{ {{! First build the header for the feed. }}
  "version": "[jsonfeed.org/version/1](https://jsonfeed.org/version/1)",
  "title": "{{#encodeJSON}}{{{title}}}{{/encodeJSON}}",
  "description": "{{#encodeJSON}}Feed for {{{title}}}{{/encodeJSON}}",
  "home_page_url": "{{{blogURL}}}",
  "feed_url": "{{{blogURL}}}/jsonfeed.json",
  "items": [
    {{#recentEntries}}
    { {{! Now create an entry for each post }}
      "id": "{{{blogURL}}}{{{url}}}",
      "title": "{{#encodeJSON}}{{{title}}}{{/encodeJSON}}",
      {{#summary}}"summary": "{{#encodeJSON}}{{{summary}}}{{/encodeJSON}}",{{/summary}}
      {{#thumbnail.large.url}}"image": "{{{blogURL}}}{{{thumbnail.large.url}}}",{{/thumbnail.large.url}}
      "content_html": "{{#encodeJSON}}{{#absoluteURLs}}{{{body}}}{{/absoluteURLs}}{{/encodeJSON}}",
      "date_published": "{{#formatDate}}YYYY-MM-DDTHH:mm:ssZ{{/formatDate}}",
      {{#metadata.externalurl}}"external_url": "{{{metadata.externalurl}}}",{{/metadata.externalurl}}
      "url": "{{{blogURL}}}{{{url}}}"
    }{{^last}},{{/last}}
    {{/recentEntries}}
  ]
}
```

Once I got this setup [Feedbin](https://feedbin.com), which supports JSONFeed, was able to once again see my feeds and pulled in new content right away. It works great! Thanks to David for such a great service as Blot, and for adding this capability to support JSONFeed! 👏
