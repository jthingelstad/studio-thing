---
microblog_id: 1075357
url: "https://www.thingelstad.com/2010/02/06/showing-your-kid.html"
title: "Showing Your Kid to Program"
published: "2010-02-06T06:00:00+00:00"
post_kind: post
categories: []
---

My friend [Jim](http://www.jimbernard.net/) and I were talking the other day and he asked me for some recommendations on a way to introduce his son to computer programming. I have shared, *probably multiple times*, with Jim how I learned BASIC when I was around 6 years old and how important I felt that was. My very first computer was a [TI-99/4A](http://en.wikipedia.org/wiki/Texas_Instruments_TI-99/4A) with a cassette tape adapter to store my programs on. After a summer of mowing lawns I added an [Extended BASIC](http://en.wikipedia.org/wiki/TI_Extended_BASIC) cartridge to it. My mother bought me the computer when Texas Instruments decided to stop making computers. If I remember right it cost $99 at JC Penney's including the RF adapter to plug it into your TV. How many computers can you buy today for $99? The great thing about that computer was that you turned it on and it did nothing. It just sat there flashing a cursor at you waiting for some instructions. It had a built-in BASIC interpreter and I was off to the races after my uncle Tim, who took one BASIC class in college (1978!) while becoming a carpenter, showed me some ropes. By current standards it sounds horrible, but it was simply awesome. It was like getting an infinite number of crayons and all the paper you could fill with drawings.

Back to the question at hand. Today's machines are so much more powerful, and the languages are more advanced, but that doesn't do a lot for a 5-year-old kid that wants to play around with for loops and print statements. My answer came pretty quickly.

I decided to write this up in a blog post because I think the topic is interesting. However, I'm also very interested in what other people would suggest. I suspect a biased answer from my experiences. I also expect that, sadly, my age may show in my answers as well.

### BASIC

Nobody will ever write a line of [BASIC](http://en.wikipedia.org/wiki/BASIC) code for anything real. However, I don't think any future geek of my generation got through high school without going to Radio Shack and typing

```basic
10 PRINT "JAMIE ROCKS!"
20 GOTO 10
```
Just being able to do simple conditionals, loops and control statements in the simple world of Basic is an amazing thing. Sure even a 5-year-old can pick up an iPhone and do some cool things with various programs. But that is "user land". Those two lines above are not in "user land", they are in programmer world, and that is different.

For a kids 4 to 8 years old Basic can still be a lot of fun. Plus, they will learn the horrors of GOTO and realize that even though some modern languages accommodate `GOTO` it should never be used.

<img src="https://www.thingelstad.com/uploads/2020/97975ae164.png" style="width: 64px; float: right; margin-left: 10px; " />

Even though your modern machine will come with a ridiculous wealth of software it will not come with a BASIC interpreter. Open source software to the rescue with the [Chipmunk BASIC interpreter](http://www.nicholson.com/rhn/basic/). I downloaded the Mac version and spent a little while reliving memories just now.

### Logo

<img src="https://www.thingelstad.com/uploads/2020/b1cc65a60e.jpg" style="width: 100px; float: right; margin-left: 10px; " />

The complement to showing young minds BASIC and all the text-based fun is a Logo interpreter. Logo is a fun little language where you move a "turtle" around on a canvas and place a pen up and down to create graphics. It's a wonderful little language that you can make pictures in. How great for kids to see the result of their code!

Logo interpreters were never bundled with machines but you can download [ACSLogo for Mac OS X](http://www.alancsmith.co.uk/logo/) that works well and is a free download.

### What Else?

As I thought about these two selections they felt right. For kids interested in learning more about programming starting with BASIC and Logo just felt right. I did some searching on the topic and I found a number of other languages that are specifically designed for kids to learn to program. The ones I looked at seemed either [too much "user land"](http://www.greenfoot.org/about/screenshots.html), clicking and dragging to me or they were simply [overly verbose and silly](http://www.sjbaker.org/steve/software/hiccup.html).

Of course if your kid is ready for something even more interesting, give them the really old beat up computer you have in the basement and install Linux on it and let them dive into the heart of the kernel. We live in amazing times! Maybe the crucial thing is to give your aspiring programmer the junky hardware to force creativity?
