---
microblog_id: 1072935
url: "https://www.thingelstad.com/2020/04/18/suggestions-for-importing.html"
title: "Suggestions for importing Jekyll blog to micro.blog?"
published: "2020-04-18T11:23:53+00:00"
post_kind: post
categories: []
---

Micro.blog community: I need to migrate about 8,000 blog posts from a Jekyll site to micro.blog. Does anyone have suggestions or pointers to existing tools?

At first glance I thought I would write a Python script to recurse the `_posts` directory and hit micro.blog's API creating each post. However, I have Jekyll tags in those markdown files that will cause serious challenges. Now I'm thinking I should use Jekyll to publish the site and then use the RSS or even a custom file, perhaps JSONFeed, to then import into micro.blog? Then I can make Jekyll do the hardest work for me.

Anyone done this and can recommend an approach? This seems to be similar to the method [Manton Reece](https://manton.org) used when [importing his podcast](https://www.manton.org/2018/11/12/timetable-migrated-to.html).
