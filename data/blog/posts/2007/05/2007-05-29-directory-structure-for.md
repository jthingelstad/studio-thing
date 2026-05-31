---
microblog_id: 1076044
url: "https://www.thingelstad.com/2007/05/29/directory-structure-for.html"
title: "Directory Structure for Digital Photos"
published: "2007-05-29T05:00:00+00:00"
post_kind: post
categories: []
---

It seems that a lot of people have a hard time settling on a file structure to use for their digital photos. There are a number of different approaches, and the tools that you use will heavily influence this but I think it's important to settle on something independent of your tools since those will change over time.

There are a couple of things you want to make sure to accomplish with the directory structure that you use for your photos.

1.  *Consistency* is important. You want to make sure that regardless of camera, subject or any other variable there is a consistent way to find a photo.

2.  *Uniqueness* of photo name is important. Even though the directory structure would allow for multiple files with the same name, you should guarantee that every file is unique and "fully qualified" for each individual photo.

3.  *Backup management* is handled most simply through your file structure. I don't like to rely on fancy backup programs to know what has been backed up or not, I like to be able to achieve this through chronology.

I've been using the following structure for over 5 years and I've found it to work very well. I've used it with a number of different photo management programs, including my current favorite, Adobe Lightroom. It is inherently driven off of the timestamp of the photos.

<img src="https://www.thingelstad.com/uploads/2020/a662276a78.png" style="max-width: 437px;" />

Let me highlight the five critical sections of this (cross-reference to numbers above, sorry Tufte).

1.  Your photos live in a *root directory*. This could be anywhere and just identifies the home of all photos.

2.  Start your directory structure with the *year*. There should be a year for every year you have photos. This cascades into months and finally days.

3.  The *"day directory"* itself is typically auto-created by your importing software but it likely won't have the a title for it (e.g. "Around House"). I add this myself, and I have an additional trick in that I don't add that text until I'm done doing post-processing on those photos (purging, keywords, metadata, etc). The other reason to add a title is to give you some visibility on what you are looking at when you are just looking at your directory structure.

4.  The *filename* itself is really simple. I always use YYYYMMDD (year, month, day), dash, HHMMSS (hour, minute, second), dash, and lastly the serial number of the photo from the camera. The serial number is important since you may take photos in burst mode and have more than one in a second. Or, if you are shooting with multiple people and multiple cameras, and happen to take a photo in the same second, you are still unique. I could put more here (camera serial number, ISO, etc. but I've never found it necessary). The completeness of the timestamp inside the filename is great. I can always figure out the full path to any file just using it's filename.

5.  The last _"Other"_ is a catch all. Sometimes I get copies of photos that other people take. I don't typically interleave these with my photos, and instead just drop them in the Other directory. This is a catch-all for such photos, sometimes even having directories inside other like "Bob's Trip to Alaska", that is all grouped together. The other directory is last which is helpful for backup.

The backup strategy for this structure is a simple top-down flow. I never backup a month until it's completed. The great thing here is that once the time has passed, the directory and files in those directories are not changed so you don't have to worry about going backwards in time. (Note, I also mirror files every night, and this is automated to other discs.)
