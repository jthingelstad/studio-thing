---
microblog_id: 1075537
url: "https://www.thingelstad.com/2009/05/12/introducing-velotweets-the.html"
title: "Introducing VeloTweets - The Pulse of the Peloton"
published: "2009-05-12T05:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/7a1c5b0688.png" alt="VeloTweets logo with tagline Pulse of the Peloton and a small cycling icon on a light blue background" style="width: 187px; float: right; margin-left: 10px; " />

A couple of months ago I started to notice that there were a lot of professional cyclists that were getting on [Twitter](http://twitter.com/). [Lance Armstrong](http://lancearmstrong.com/) ([@lancearmstrong](http://twitter.com/lancearmstrong)) was really active, as were a couple of dozen other riders. I was interested in what they had to say, but I also didn't want to have thirty or more new feeds in my Twitter stream. So, I decided to just subscribe to the [RSS](http://en.wikipedia.org/wiki/Rss) feeds of these riders and put them in [Google Reader](http://www.google.com/reader/).

As I read these feeds I started to see some really cool trends. When the early spring classics were happening you could get a sense from other riders on how they thought the races went down. You could see a *first person view into what was going on in the peloton*.

It hit me that there was something interesting here and that if these Twitter streams were put together with the right display as well as some additional [metadata](http://en.wikipedia.org/wiki/Metadata) it could be a really interesting way to experience the sport from a never before seen perspective. **The idea of [VeloTweets](http://www.velotweets.com/) was born!**

### The Team

I liked the idea, but I knew I wouldn't be able to do this on my own. [Luke Francl](http://justlooking.recursion.org/) and I had chatted about cycling and I knew he was into it. Luke approached [Norm Orstad](http://norm0.com/) about the project and Norm was into it. I asked my friend [Chris Hatch](http://buriedpleasure.blogspot.com/), who is a rabid cycling fan, if he would help with some editorial work. Everyone was in, and we had a team with no budget and limited time. The best way to hit a side project. :-)

<img src="https://www.thingelstad.com/uploads/2020/ab4509fc44.png" alt="VeloTweets website screenshot showing a grid of profile photos and tweets from professional cyclists during Stage 4 of the Giro d Italia" style="max-width: 500px; " />

Luke put together all the code, Norm did the designs and Chris did the research while I played sweeper behind everyone and helping out on the edges in all the areas I could.

If you curious how the application was built, you should read Luke's [Rail Spikes post about VeloTweets](http://railspikes.com/2009/5/10/announcing-velotweets).

### Why is this cool?

The utility around VeloTweets comes from aggregating the Twitter streams together and then applying a thin layer of metadata on top of that. Team affiliations and nationality are the ones that we added in the first release. We really wanted to add jersey counts to show how many jerseys a rider held by each type (yellow, green, polka dot, white) but we couldn't find a free source for that data.

The point was to level the playing field and provide the insight that someone who knew the sport well would have to those who did have that background.

After our first of 2 days getting together to build the site I was struggling because I felt it looked too much like Twitter. A stream of status updates, not really adding much value. As we discussed this we had a breakthrough that helped a lot. Norm suggested the analogy of a baseball card and we quickly came up with the idea of having a grid where each rider is only shown once, with their most recent message.

<img src="https://www.thingelstad.com/uploads/2020/9f9ad6c14c.png" alt="Four social media posts from professional cyclists including Lance Armstrong and others discussing the Giro stage race and weather." style="max-width: 490px; " />

This was a winner right away and solved a bunch of problems. Now the group was equalized. If you were really active or not, you would only show up once in the grid. The grid gave us a dynamic layout that we could use in any instance. For example, maybe we just want to see the [information for Team Astana](http://www.velotweets.com/teams/1).

<img src="https://www.thingelstad.com/uploads/2020/15a339e2cd.png" alt="Four social media post panels from Team Astana cyclists grouped under a Team Astana header with profile photos and timestamps" style="max-width: 490px; " />

This view gives the reader the ability to quickly scan the breadth of the group, without getting stuck in the depth of any one rider.

We also started to dive into the information in the messages. We tackled pictures sent with the messages, specifically TwitPics and aggregate those into [VeloPics](http://www.velotweets.com/photos). Now we can do something that you can't do with any other client or feed mashup and show the aggregated set of pictures from the group (or team) in a grid to browse. There are bound to be some awesome shots of bikes and other riders in there and this aggregation lets you see them all.

<img src="https://www.thingelstad.com/uploads/2020/b0abf6f3a0.png" alt="Collage of eight cycling event photos showing riders racing, people on a ferry with bikes loaded on vehicles, and small groups of people outdoors" style="max-width: 490px; " />

We also put a "Message of the Day" on the site so that you instantly know what is going on that day. If there is a grand tour going on, it will highlight the stage for the day. And, most of the time (no guarantees) it is even updated to reflect the outcome of the race. This is a great grounding point to understand the context of the messages from the group.

We also have integrated a race calendar so we can show when races are. We'd love to add some other data sources over time, we'll see. All part of being the **Pulse of the Peloton**.

### Thanks!

My huge, huge thanks to Luke, Norm and Chris for their help getting this launched. It was enormously fun to work with these guys and to see what we could get done with the limited time available.

If you want to stay tuned on updates to VeloTweets follow [@VeloTweets](http://twitter.com/VeloTweets) on Twitter!

Now, back to the Giro...
