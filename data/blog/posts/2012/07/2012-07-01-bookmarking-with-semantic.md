---
microblog_id: 1074970
url: "https://www.thingelstad.com/2012/07/01/bookmarking-with-semantic.html"
title: "Bookmarking with Semantic MediaWiki"
published: "2012-07-01T05:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/c8641ec8d5.png" style="width: 160px; float: right; margin-left: 10px; " />

I have been doing a lot of exploration using [MediaWiki](http://www.mediawiki.org/wiki/MediaWiki) and the [Semantic MediaWiki](http://semantic-mediawiki.org/) suite of extensions. I've deployed a number of wikis doing a wide variety of things. For a few months I had been pondering the idea of hosting my own bookmarking site using Semantic MediaWiki. I decided to give it a try and put together links\_thing.

First a quick primer. Semantic MediaWiki is an extension that lets you store and query data in wiki pages. Wikis have been awesome at dealing with documents and text for a long time. But if you wanted to put a table of data in a wiki that didn't work very well. And if you wanted to query that table of data? Well, that was just crazy. Semantic MediaWiki gives you the ability to associate properties with pages and then query them. So, for my bookmarks each wiki page in the category bookmark is a bookmark and has a number of properties, including things like Has URL, Created at, Has excerpt. You get the idea. You put all this logic into the Templates that the wiki uses, making them into Semantic Templates and even the data entry can be made user friendly using Semantic Forms to create fancy forms with a variety of standard controls.

### Making it

Building this wiki was pretty easy. I mostly just thought for a while about the properties that a bookmark has. I wanted to get it right since I could use the scaffolding that Semantic MediaWiki has to create a "class" and template out all the basic stuff. It's easy enough to add after the fact too. After making the class for Bookmarks there was only one real thing I needed to prove. I had to be able to have a Bookmarklet that would automatically populate the URL, Title and Excerpt for a bookmark. Of course the timestamp needed to be done to but I knew how to do that.

After some digging I figured out how to pass parameters into the Forms to pre-populate fields and also how to tell Semantic Forms to name the page based on a field in the form (namely, the TItle of the bookmark). After proving that out I was ready to go.

### Importing

I wasn't willing to lose any data, and I knew it was just a matter of shoveling. I used Pinboard's JSON export and then whipped up a little Python program to turn that into a CSV that could be imported using the [Data Transfer](https://www.mediawiki.org/wiki/Extension:Data_Transfer) extension. I easily imported just under 4,000 links and had all my data there.

### Fun Stuff

I've been using my new Bookmark wiki exclusively for the last few weeks and I'm absolutely loving it. Here are just some of the reasons why:

1. It is mine. Put simply, I don't need to rely on anyone else to keep it working of me. For an archive, this feels reassuring.
2. This seems simple, but it's so helpful to be able to do regular expression driven find and replace through all my bookmarks. I've probably done 50 of these cleaning things up. For example, I didn't like that a lot of bookmarks had a title that ended in " - Home" or " - My Super Cool Blog". A quick search and replace and they are gone.
3. I thought it would be interesting to see my bookmarks on a calendar. Seems like a simple thing but I don't think any bookmarking service does it. So I made a calendar view.
4. Wouldn't it be nice to be able to see YouTube and Vimeo videos I bookmark without having to go to the video pages one at a time? I made a video view.
5. I really want my bookmarking tool to have URL Checking. I hate short URL's because I suspect they will go away. I also don't like analytics tags being bugged into my URLs. I have a Check URL Template that checks for these in my wiki, and a bot that cleans them up.
6. I thought it would be cool to see statistics on my bookmarks so I created a Bookmark Statistics view.

This is just the beginning. I'm sure I'll be adding a lot of other tweaks over time.

### What's next?

I've now building a little Python application called LinkBot. LinkBot runs on a schedule and validates URL's for me. I'll write up about that application separately.

I would love to share this suite of templates and properties with anyone else. It's easy to export the pages off of my wiki and import them into your own. If you are interested I have cloning information and feel free to connect.
