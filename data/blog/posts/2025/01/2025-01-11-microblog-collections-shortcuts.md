---
microblog_id: 4589500
url: "https://www.thingelstad.com/2025/01/11/microblog-collections-shortcuts.html"
title: "Micro.blog Collections Shortcuts"
published: "2025-01-11T14:57:11+00:00"
post_kind: post
categories: []
---

I've gone "all in" on Micro.blog's [photo collection](https://help.micro.blog/t/photo-collections/3366) feature. I've created **64 collections** so far which if I’m reading id numbers right means **17% of all collections** on micro.blog are ones I made. 🤓

I needed some tooling in order to migrate to collections and use them the way that I want to. I’m sharing here the three shortcuts that I've created to do this: Creator, Copier, and Viewer.

Requirements to be aware of:
- You will need an App Token for these Shortcuts. Create one on [your apps screen](https://micro.blog/account/apps). 
- These shortcuts, like most of my more complicated shortcuts, all use [Logger for Shortcuts](https://shortcutslogger.dev). Make sure to install that on your devices. It is free and a great utility. I debated removing the logging methods to avoid this dependency but these shortcuts can run for 20 or 30 seconds and it is very helpful to be able to see the logging output while it is running.

### Collection Creator

I've updated my [original Collection Creator shortcut](https://www.thingelstad.com/2024/12/30/microblog-collection-creator-shortcut.html) through my own use. Most of my collections have been populated with this Shortcut. I've found it even more useful than I thought to be able to take a clipboard full of URLs and create a collection out of the linked images. I've used it for posts, for pages, and even some cases where I just grabbed a bunch of image links and create a collection.

<img src="https://www.thingelstad.com/uploads/2025/collection-creator.png" width="600" height="315" alt="">

Improvements since the [first release](https://www.thingelstad.com/2024/12/30/microblog-collection-creator-shortcut.html):

- Improved confirmation prompts for clarity.
- Improved logging to be more useful and include progress indicators like "1 of n" to each item. [^1]
- After completing create the shortcode for the collection and put in the clipboard so ready to use.
- Minimal monitoring of API failure. [^2]

**Add [Micro.blog Collection Creator](https://www.icloud.com/shortcuts/a34f7c9d3599451b9c10b5ebd81ab965) Shortcut**

### Collection Copier

I’m not sure how common this will be, but at times I want to include all the photos from one collection into another collection. For example:

- [Blog post about a day of hiking in Switzerland](https://www.thingelstad.com/2023/07/16/hiking-scuol-to.html) uses a collection for that post.
- Page about that [overall trip](https://www.thingelstad.com/collections/switzerland-italy-2023/) has a collection of photos for that trip.
- A photo page that contains [all photos I've taken in Switzerland](https://www.thingelstad.com/photos/switzerland/).

<img src="https://www.thingelstad.com/uploads/2025/collection-copier.png" width="600" height="336" alt="">

In this case these photos are in three collections. The easiest way to populate the aggregated collections would be to copy all photos from individual collections to them. It would be nice to "Add all photos from Collection X to Collection Y". That is what this Shortcut does.

**Add [Micro.blog Collection Copier](https://www.icloud.com/shortcuts/431a91e189ab46f19a3483caed61484e) Shortcut**

### Collection Viewer

The viewer collection I don't use a ton because it doesn't do anything different than just looking at the collection on micro.blog. But I do like having the ability to quickly index into a collection and just verify what is in there so I’m keeping it around too. It was also the first Shortcut I wrote for this to figure out how to get into the API and see the responses.

**Add [Micro.blog Collection Viewer](https://www.icloud.com/shortcuts/b67334c08d304fa38e9a9cfd49d0382e) Shortcut**


[^1]: The API method to add images to a collection was made much faster but it still takes about a second per image. This gives you a better indicator of where you are in the process. Think of it like a status bar.
[^2]: I find it odd that in Shortcuts I cannot seem to retrieve the HTTP status code for an API call. I can access the body of the response, but not the status code. I now have the shortcut check the body of the API call to add the image to a collection and if there is any content there log a warning. I wish I could check for a 200 but it doesn't seem possible.
