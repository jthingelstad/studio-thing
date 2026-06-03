---
microblog_id: 1077241
url: "https://www.thingelstad.com/2020/04/21/using-api-credentials.html"
title: "Using API Credentials in Shortcuts"
published: "2019-01-22T05:00:00+00:00"
post_kind: post
categories: []
---

Shortcuts on iOS can do incredibly powerful things, and with a little bit of extra magic you can connect to most API's as well. Pulling data from API's, manipulating it, and extending your shortcuts is really powerful. However, you need to have a good way to manage the authentication tokens and secrets for those APIs.

Most Shortcuts I have seen use a Text variable and put the token in that variable. It’s then used throughout the Shortcut. This works, but it exposes problems if you share that Shortcut. It also has issues if you use the same API in multiple Shortcuts. You are now copying that token in numerous places.

Another approach that I prefer is to create Shortcuts that do nothing but return those tokens. You can then call those Shortcuts from another Shortcut to get the token. I prefix these Shortcuts with the prefix "Secret".

<img src="https://www.thingelstad.com/uploads/2020/672df60364.png" width="375" height="199" alt="Four red iOS Shortcut tiles labeled Secret/Pinboard Token, Secret/MailChimp, Secret/Toggl API Token, and Secret/Working Copy Key, each showing a padlock icon." />

Then when I need to use an token for an API I call the Shortcut and then reference the magic variable returned from it. You can even hide the execution of that second Shortcut.

<img src="https://www.thingelstad.com/uploads/2020/2752e42cae.png" width="375" height="491" alt="Apple Shortcuts editor showing three actions: Ask for Input asking How many links with default 10, then two Run Shortcut actions calling Secret/Pinboard Token and Secret/Working Copy Key." />

In addition to reuse, you also get other benefits from this approach. Your Secret Shortcut can have some logic. For example, I access [Working Copy](https://workingcopyapp.com) from Shortcuts and it does so with a local URL call, protected with a random key. That key is specific to each iOS device. So, rather than try to synchronize the keys I have the Secret shortcut return whatever key is right for the device that is running.

<img src="https://www.thingelstad.com/uploads/2020/db83c65f76.png" width="374" height="464" alt="iOS Shortcuts editor showing three chained actions: Get Device Details set to Device Name, a Dictionary mapping two device names to secret keys, and Get Dictionary Value retrieving a value by Device" />

I do a similar thing with MailChimp's API token that requires some encoding be applied to it.

I find this a better way to manage these secret tokens, get reuse, and make it easier to change them. 👍

_This post is part of the [Shortcuts Collection](https://www.thingelstad.com/collections/shortcuts/)._
