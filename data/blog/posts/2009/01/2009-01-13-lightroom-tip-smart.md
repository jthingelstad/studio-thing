---
microblog_id: 1075704
url: "https://www.thingelstad.com/2009/01/13/lightroom-tip-smart.html"
title: "Lightroom Tip: Smart Collection for Pictures Without Location"
published: "2009-01-13T06:00:00+00:00"
post_kind: post
categories: []
---

Lightroom 2 introduced a badly needed feature, Smart Collections. I was ecstatic about using Smart Collections to assist with workflow. One of those workflows I've been working on has been adding IPTC location data to my photos, essentially setting the Country, State, City and Location for photos. It would be great to create a Smart Collection that included all photos that do **not** have location details and then just work through it with photos automatically being removed after adding the information. You can try this by creating a Smart Collection like this:

<img src="https://www.thingelstad.com/uploads/2020/dacb28a2e6.png" alt="Lightroom Create Smart Collection dialog with Name set to Null Location and one rule showing Location is with an empty value field" style="max-width: 500px;" />

But, it won't work. Lightroom doesn't have an operator "is blank". The next best thing is to just do "is" and set the value to nothing, but Lightroom doesn't honor this and just assumes you made a mistake. I stopped here for a long time and just assumed what I wanted to do wasn't possible. However, then I came up with this workaround:

<img src="https://www.thingelstad.com/uploads/2020/afa37c0041.png" alt="Create Smart Collection dialog named Null Location with a rule set to Location doesn't contain all alphabet letters a through z" style="max-width: 500px;" />

And this works perfect! Create a smart collection using "doesn't contain" for each letter in the alphabet and you will get the desired result, all photos that do not have anything in their location. Great!
