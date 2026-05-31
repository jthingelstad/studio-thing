---
microblog_id: 3328723
url: "https://www.thingelstad.com/2023/07/08/preserving-your-writing.html"
title: "Preserving your Writing on the Web Forever"
published: "2023-07-08T13:56:30+00:00"
post_kind: post
categories: []
---

I suggested to some friends that I wanted to do everything I could to keep my websites and online writing around well after I’ve died. One of them asked how I was approaching this, and what I was doing today to make this happen. 
  
What am I doing to make it so my content online lives for as long as possible? It may be easiest to start with what I’m **not** doing. 

1. I am not writing and publishing into a corporate database that I cannot own my words. [Not your domain, not your words](https://www.thingelstad.com/2022/12/17/not-your-domain.html). 
2. I am [not writing for a timeline](https://www.thingelstad.com/2023/02/05/not-writing-for.html). Mostly in this context this means my writing should stand on its own. I try to avoid implying current context that a future reader will not know.
3. I am not using a database or other software at runtime to display my writing. My writing is rendered from markdown to HTML and then published. The markdown is plenty readable on its own if need be.

Now what I **am** doing.

1. I’m publishing with micro.blog because it meets all of my criteria, and then some. It even goes beyond. For example, when I link to an external site, micro.blog grabs an archive of that link so in the future I could reference that archive instead of the live site.
2. I publish the Weekly Thing with Buttondown which uses easy Markdown to publish.
3. I export my entire blog archive from micro.blog every 3 months to my local storage.
4. I export my Buttondown archive of the Weekly Thing every 3 months to my local storage.
5. I download my entire Pinboard archive every month. This is the source markdown that is also included in Buttondown, but this is indexed by link.

Problems to solve still.

1. All of my content can be served with any static HTTP endpoint. This could be done easily with AWS S3. However, paying for an AWS account after your death is not obvious. Possibly you can prepay for decades, but then you rely on a company. A small trust could be created that has funds to renew domain names and pay the content hosting fees for decades. That trust could be funded by future generations if they continue to see interest.
2. The solution I like the most is distributed storage with IPFS paid for via Smart Contract. I can fund a Smart Contract that can hold my ENS asset, and pay the IPFS hosting fees to maintain the data for as long as there are funds. This avoids a legal trust, and can easily receive funds via anyone on the web. You could have a simple way to keep your own archive alive.
3. Adding this content to Internet Archive is good, but I don't want to only rely on that.
4. I consider the idea of printing all of this onto paper, or eBook, and distributing it broadly. I think that is a good backup method as well.

In short.

1. Control all aspects of what you create.
2. Keep is simple, no runtime requirements.
3. Durable hosting and figure out economonics.
