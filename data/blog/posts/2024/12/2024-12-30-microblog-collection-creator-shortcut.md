---
microblog_id: 4563205
url: "https://www.thingelstad.com/2024/12/30/microblog-collection-creator-shortcut.html"
title: "Micro.blog Collection Creator Shortcut"
published: "2024-12-30T16:02:43+00:00"
post_kind: post
categories: []
---

Recently micro.blog added a powerful new feature to create [photo collections](https://help.micro.blog/t/photo-collections/3366). Using this feature you can group photos together and then use a special micro.blog shortcode to reference that collection in a blog post or page. 

This is a powerful feature and one of the things I wanted to do with it was create collections for the "gallery" blog posts I have on my site, posts that often have six or more images as a collection. However, there is no way to easily create a collection from a list of uploads that already exist. That is the gap this shortcut solves!

Collection Creator is intended to take the contents of a blog post, find all referenced images on that post, and then add them to an existing collection! The shortcut structure is straightforward:

1. Receive the text, expected via a copy/paste.
2. Find all referenced uploads in the text.
3. You pick an existing collection.
4. It adds each image to that collection.

After it is complete you can remove the image references from the blog post and replace with the collection shortcode.

**There is a [newer version of this Shortcut](https://www.thingelstad.com/2025/01/11/microblog-collections-shortcuts.html)!**

### Notes

1. This shortcut **requires** two constants to be set: the base URL of your site and an App Token to authenticate to the Micro.blog API.
2. This shortcut has a **dependency** on the very powerful [Logger for Shortcuts](https://shortcutslogger.dev) app. This is particularly useful when adding several uploads to a collection since you can see the progress and it takes several seconds per image. I've had this shortcut take over a minute to run and watching Logger is helpful to see progress.
3. This shortcut will **not** create a collection for you. You should do that in the Micro.blog Uploads interface before running the shortcut. 
4. If there is an error and you process 10 images but the API fails and only 9 are added to the collection you can simply rerun it again with no issue.
