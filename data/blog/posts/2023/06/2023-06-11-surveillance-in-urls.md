---
microblog_id: 3160722
url: "https://www.thingelstad.com/2023/06/11/surveillance-in-urls.html"
title: "Surveillance in URLs"
published: "2023-06-11T12:50:21+00:00"
post_kind: post
categories: []
---

The [Uniform Resource Locator](https://en.wikipedia.org/wiki/URL) is the glue of the web. Mostly we don't think about URLs unless you create content on the web. Some browsers have even started to "simplify" the URL display worried that people might get confused. Or are they hiding it on purpose? URLs are however, a place where you can be tracked and surveilled right in the open. There are a myriad of ways to make URLs completely unique so that you are the only person in the universe that has it and whoever created that link can specifically know that you, or someone you shared it with, clicked on it. They also know when, where, and on what device. Every time.

I don't think that is acceptable.

I curate and collect URLs and am always on the lookout for tracking information in them. It is usually easy to spot and remove. I got really excited when I saw that [iOS 17 automatically removes tracking parameters from links](https://9to5mac.com/2023/06/08/ios-17-link-tracking-protection/). Unfortunately the feature is far too limited. It is nice that it works in a variety of applications, including Mail. However it only removes the unique tracking, and doesn't get rid of the rest of the surveillance. And it **only** activates in Safari Private Browsing mode.

This is what URL surveillance looks like from a link I recently received from a friend. The link itself was a slight 28 characters. The surveillance was 302 characters. Over 90% of the information in the URL was to surveil and track the users of the link. I've changed the specifics so this isn't a valid link, but here is what it looks like split onto multiple lines for readability.

https&colon;//abcdefg.com/a/123456  
?utm_source=Instagram_Stories  
&amp;utm_medium=ad_story_smartly  
&amp;utm_campaign=123456_msp  
&amp;ad_id=123456789012  
&amp;utm_term=987654321098765  
&amp;fbclid=PAAaZnG…5kyWFFJ

The person that sent me this got it from Instagram, apparently in an Instagram Story. They were advertised with a `utm_campaign` focusing on "msp", our nearest airport code. The creepiest parameter is `fbclid` which specifically identifies the click event for this paid content and will track the specific link of humans that this goes through. Letting the originator know that my friend also shared it with other people, and all of their metadata too.

The good news is you can just delete everything after the `?` and it works great. Which is the thing I do a lot. **A truly privacy aligned feature for a browser would be to strip all URLs of all surveillance parameters.** There is a corollary too. Browsers that hide URL parameters are assisting in the surveillance of users.

As a user, **you can significantly improve your privacy and fight surveillance by being aware of the tracking parameters placed routinely in URLs and removing them.** Remove it before you share it. Remove it before you create a bookmark. You often can just delete anything after the `?`. Doing this helps your privacy, and helps protect the privacy of those you send links to.
