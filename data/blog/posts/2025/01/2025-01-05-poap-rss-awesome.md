---
microblog_id: 4573939
url: "https://www.thingelstad.com/2025/01/05/poap-rss-awesome.html"
title: "POAP + RSS = Awesome?"
published: "2025-01-05T15:43:54+00:00"
post_kind: post
categories: ["Crypto", "POAP2RSS"]
---

**Update: I created [POAP2RSS](https://www.poap2rss.com) to fill this gap!**

I’m a [big fan](https://www.thingelstad.com/lists/poap-events/) of [POAP](https://poap.xyz), and I’m a big fan of [RSS](https://en.wikipedia.org/wiki/RSS). Sadly, these two things don't know about each other, yet! This blog post is my take on a great start for RSS and POAP. Maybe there is a chance that the amazing folks at [Open RSS](https://openrss.org) could bridge this gap in the meantime!

First, why should POAP add RSS? I think there are dozens of use cases, but some examples…

1. As someone that issues POAPs a lot I would love to subscribe to the RSS feeds for each of my events and see via the feed when a new token is claimed.
2. It would be powerful to use automation on claims along by connecting the RSS feed for an event to [IFTTT](https://ifttt.com/explore) or any of the hundreds of services to take an action when an RSS feed is updated.
3. There are several friends that are active in the POAP ecosystem and I can aggregate a feed of all their claims in the [POAP Home](https://home.poap.xyz) app, but I would rather subscribe to an RSS feed of each of their addresses and get updates that way.

There are two items that RSS feeds would be useful for: **Events** and **Collectors**. There is a [POAP API](https://documentation.poap.tech/docs/getting-started) that would make both of these pretty simple to get, and avoid any screen scraping. An API key would be needed but I think that would be [easy to get](https://documentation.poap.tech/docs/api-access). These use cases are all read only as well.

### Events

Anybody can create an event the RSS feed would be specific to that event. Events have a simple ID, and there is a [Token Event API](https://documentation.poap.tech/reference/geteventpoaps-2) method for `/event/{id}/poaps` that would get exactly what is desired. The URL's for an event are `https://poap.gallery/drops/{eventid}`, my [53rd Birthday](https://poap.gallery/drops/183305) POAP is at `https://poap.gallery/drops/183305` is an example.

In this case, the `eventid` is easily found and using the API could get the data to populate the RSS feed. 

### Addresses

Getting an RSS feed for new tokens that people claim is centered around a wallet address. Here we are looking for an address or ENS name. An example of this is [my collection](https://collectors.poap.xyz/scan/0x111accebf9d70d9c06de2d38f9392522e82ecf29) at `https://collectors.poap.xyz/scan/0x111accebf9d70d9c06de2d38f9392522e82ecf29`. This can also be accessed via the ENS name at `https://collectors.poap.xyz/scan/poap.thingelstad.eth`. 

The [Token Scan API](https://documentation.poap.tech/reference/getactionsscan-5) method `/actions/scan/{address}` returns the list of tokens for that address and could build the RSS feed.
