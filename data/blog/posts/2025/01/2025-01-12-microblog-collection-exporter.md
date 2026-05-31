---
microblog_id: 4593004
url: "https://www.thingelstad.com/2025/01/12/microblog-collection-exporter.html"
title: "Micro.blog Collection Exporter"
published: "2025-01-12T20:23:55+00:00"
post_kind: post
categories: []
---

I’m adding one more Shortcut to my [Micro.blog Collections Shortcuts](https://www.thingelstad.com/2025/01/11/microblog-collections-shortcuts.html). One of the concerns I've had with collections is making sure that I have some way of undoing them. If I move to another blog service and it doesn't support these I need to know which photos are in those collections. This is gracefully handled by micro.blog when you export your blog. It will replace them all at that time and your good to go.

However, I’m a bit of a "belt and suspenders" person and I'd like more than just that. Also, what if I just wanted to undo a single collection and I’m not exporting my whole blog? I'd like to be able to get at this data easier. Add to that that for very large blogs micro.blog export doesn't work today due to file size limitations. I wanted another way.

This Shortcut gets a list of all your collections, then iterates through that list building a JSON data object that contains all your Collection names along with an array of the photos in that collection. 

It can take a bit to run, and Shortcuts in general isn't great with loops of loops and building larger data sets. Give it some time and it will finish just fine. It takes about 15 seconds to run for my over 60 collections.

**[Add Micro.blog Collection Exporter](https://www.icloud.com/shortcuts/3eb1c3034bd440e48345d53995523563)**

The output of this Shortcut will give data like this:

```json
{
    "Collections": {
        "Coffee": [
            "https://www.thingelstad.com/uploads/2021/31d369a8f6.jpg",
            "https://www.thingelstad.com/uploads/2021/c41923433b.jpg",
            "https://www.thingelstad.com/uploads/2021/015df1a057.jpg"
        ],
        "Iceland": [
            "https://www.thingelstad.com/uploads/2022/799a9cb53a.jpg",
            "https://www.thingelstad.com/uploads/2022/1822276426.jpg",
            "https://www.thingelstad.com/uploads/2024/24df887cc9.png"
        ],
        "Italy": [
            "https://www.thingelstad.com/uploads/2023/020261c875.jpg",
            "https://www.thingelstad.com/uploads/2023/269481db10.jpg",
            "https://www.thingelstad.com/uploads/2023/43c4de5c52.jpg",
            "https://www.thingelstad.com/uploads/2024/054ebe3a4d.jpg"
        ]
    }
}
```
