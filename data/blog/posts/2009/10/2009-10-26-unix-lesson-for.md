---
microblog_id: 1075370
url: "https://www.thingelstad.com/2009/10/26/unix-lesson-for.html"
title: "Unix Lesson for Today"
published: "2009-10-26T05:00:00+00:00"
post_kind: post
categories: []
---

Learned after much difficulty today that `find` doesn't actually spawn a shell, and as a result trying to use backticks doesn't work in a find exec parameter. However, you can tell find to invoke a shell to get around it. This works.

```bash
find . -name "*.DBF" -print -exec sh -c 'dbf2mysql -h localhost \
  -d mydatabase -t $(basename "$1" ".DBF") -c -v \
  -P password -U username $1' {} {} \;
```
