---
microblog_id: 3561901
url: "https://www.thingelstad.com/2023/09/23/smaller-images-for.html"
title: "Smaller Images for Weekly Thing"
published: "2023-09-23T22:35:01+00:00"
post_kind: post
categories: ["Kubb", "Weekly Thing"]
---

In the Journal section of the Weekly Thing I include any blog posts that I've made for that week. To keep things easy, I've always just linked to the same image files that are used on my blog. That has never been ideal since those images are much larger than what you would ideally include in an email.

I decided to try and solve this problem in Shortcuts and the amazing [S3 Files](https://s3files.app). The basic approach I take to getting blog posts into the Weekly Thing is:

1. Retrieve the RSS feed for www.thingelstad.com
2. Find items in feed that are within the time period of this issue
3. Convert each post to markdown and do some post processing to make it work in the newsletter better

To do this I would add another step after 3 to detect my own images in the posts, and do the following:

1. Detect any URL's that are uploads into my blog, and make sure to not grab any others.
2. Retrieve the image file at that URL
3. Resize it to 1,200 pixels on the "long edge"
4. Add to S3 bucket for files.thingelstad.com in the right directory for this issue
5. Replace the original image URL with the new URL

It wasn't too hard to make all this work. After tweaking the regular expressions, and making sure that the replacement worked right it was working great.

Here is a snippet from my logs.

- Add [www.thingelstad.com/2023/09/2...](https://www.thingelstad.com/2023/09/20/teamsps-kubb-tournament.html) from Sep 20, 2023 at 9:30 PM. (Count 1)
    - Detected [www.thingelstad.com/uploads/2...]([www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/img-7928.jpeg).)
        - Resized img-7928.jpeg (1.9 MB to 518 KB)
        - Replacing [www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/img-7928.jpeg) with [files.thingelstad.com/weekly-th...](https://files.thingelstad.com/weekly-thing/262/journal/img-7928.jpeg.)
    - Detected [www.thingelstad.com/uploads/2...]([www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/6334e1ac32.jpg).)
        - Resized 6334e1ac32.jpg (2.3 MB to 597 KB)
        - Replacing [www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/6334e1ac32.jpg) with [files.thingelstad.com/weekly-th...](https://files.thingelstad.com/weekly-thing/262/journal/6334e1ac32.jpg.)
- Add [www.thingelstad.com/2023/09/2...](https://www.thingelstad.com/2023/09/20/i-love-that.html) from Sep 20, 2023 at 8:09 PM. (Count 2)
    - Detected [www.thingelstad.com/uploads/2...]([www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/198c1c9be7.jpg).)
        - Resized 198c1c9be7.jpg (227 KB to 219 KB)
        - Replacing [www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/198c1c9be7.jpg) with [files.thingelstad.com/weekly-th...](https://files.thingelstad.com/weekly-thing/262/journal/198c1c9be7.jpg.)
    - Detected [www.thingelstad.com/uploads/2...]([www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/0b1754ade2.jpg).)
        - Resized 0b1754ade2.jpg (297 KB to 276 KB)
        - Replacing [www.thingelstad.com/uploads/2...](https://www.thingelstad.com/uploads/2023/0b1754ade2.jpg) with [files.thingelstad.com/weekly-th...](https://files.thingelstad.com/weekly-thing/262/journal/0b1754ade2.jpg.)

When I ran this to the Journal images in [Weekly Thing 262](https://weekly.thingelstad.com/archive/262/) it was able to resize **28 images** from an original size of 43 MB to 12 MB, **saving 31 MB** of download data!

This is a big win in two ways. First, when you open the Weekly Thing from 263 on your device will download way less data and need to use way less memory. Also, some email services apparently dislike it if emails reference images that are longer than 1,200 pixels on the longest side. Hopefully this little efficiency will also get finicky mail servers to be nicer to my emails.

This was only possible with the revamp I've been doing to my automation, and the ability to add this step in was a great result of those changes. 

_This post is part of the [Shortcuts Collection](https://www.thingelstad.com/collections/shortcuts/)._
