---
microblog_id: 1074874
url: "https://www.thingelstad.com/2014/05/11/keybase-and-mediawiki.html"
title: "Keybase and MediaWiki"
published: "2014-05-11T05:00:00+00:00"
post_kind: post
categories: []
---

I'm really intrigued by what Keybase.io is doing with identity. The ability to cryptographically prove your identity on the web without a centralized party like Twitter or Facebook owning the approval process is a needed function. I setup my profile and you can now prove on your own that I am who I say I am on Twitter, Github and five of my domains.

I'm trying to figure out how this could be extended to MediaWiki. I would love to be able to prove that my user account is me at:

-  <[wikiapiary.com/wiki/User...](https://wikiapiary.com/wiki/User:Thingles)>
-  <[www.mediawiki.org/wiki/User...](https://www.mediawiki.org/wiki/User:Thingles)>
-  <[en.wikipedia.org/wiki/User...](http://en.wikipedia.org/wiki/User:Thingles)>

This seems really hard. The method used on Github is to public a Gist, and you could certainly have a wiki user publish something on their user page, but that can also be edited by anybody.

But if we could do this, it would be a great way to allow Wikipedia editors to claim ownership with proof of their identities (if they wish) and would benefit thousands of self-hosted MediaWiki websites.

I think something more like the Twitter proof could work. How?

1. Have the user in question edit their User page. The contents of the edit don't matter, the **Summary** field is what will be looked at. (Limited to 255 characters)
2. MediaWiki websites have a permanent revision history attached to each page. (This would be like a Tweet, [see my change on May 11 2014](https://wikiapiary.com/w/index.php?title=User:Thingles&action=history))
3. This information is accessible via the MediaWiki API, and there is a revid attached to each revision.
4. This revision ID can be used to pull the proof forward for keybase.io.

Here are the last 5 revisions for my User page on WikiApiary ([API call](https://wikiapiary.com/w/api.php?action=query&prop=revisions&titles=User:Thingles&rvlimit=5&rvprop=ids|timestamp|user|comment&format=json)).

```json
{
  "query": {
    "pages": {
      "43": {
        "ns": 2,
        "pageid": 43,
        "revisions": [
          {
            "comment": "This is my message for keybase.io to prove I am who I am!",
            "parentid": 884728,
            "revid": 904406,
            "timestamp": "2014-05-11T13:10:17Z",
            "user": "Thingles"
          },
          {
            "comment": "remove gittip button",
            "parentid": 569866,
            "revid": 884728,
            "timestamp": "2014-04-30T02:55:26Z",
            "user": "Thingles"
          },
          {
            "comment": "",
            "parentid": 569864,
            "revid": 569866,
            "timestamp": "2014-02-21T01:56:28Z",
            "user": "Thingles"
          },
          {
            "comment": "added badge",
            "parentid": 552628,
            "revid": 569864,
            "timestamp": "2014-02-21T01:54:59Z",
            "user": "Thingles"
          },
          {
            "comment": "add babel box (needs templates and styles)",
            "parentid": 528928,
            "revid": 552628,
            "timestamp": "2014-02-15T19:36:51Z",
            "user": "Thingles"
          }
        ],
        "title": "User:Thingles"
      }
    }
  },
  "query-continue": {
    "revisions": {
      "rvcontinue": 528928
    }
  }
}
```

Now that we have the revid we can find the information for this revision to continue to claim proof ([API call](https://wikiapiary.com/w/api.php?action=query&prop=revisions&titles=User:Thingles&rvstartid=904406&rvlimit=1&rvprop=ids|timestamp|user|comment&format=json)). The key is that the title of the page "User:Thingles" matches with the user that made the change "Thingles".

```json
{
  "query": {
    "pages": {
      "43": {
        "ns": 2,
        "pageid": 43,
        "revisions": [
          {
            "comment": "This is my message for keybase.io to prove I am who I am!",
            "parentid": 884728,
            "revid": 904406,
            "timestamp": "2014-05-11T13:10:17Z",
            "user": "Thingles"
          }
        ],
        "title": "User:Thingles"
      }
    }
  },
  "query-continue": {
    "revisions": {
      "rvcontinue": 884728
    }
  }
}
```

And now I've proven my identity. The only trick is that the comment must contain all the data, and that should be easy since keybase already does something similar for Twitter.

And here is another example of me making a proven comment on my user page on Wikipedia (en) ([API call](https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=User:Thingles&rvstartid=608054849&rvlimit=1&rvprop=ids|timestamp|user|comment&format=json)).

```json
{
  "query": {
    "pages": {
      "14604697": {
        "ns": 2,
        "pageid": 14604697,
        "revisions": [
          {
            "comment": "Here is my message for Keybase from Wikipedia.",
            "parentid": 551074105,
            "revid": 608054849,
            "timestamp": "2014-05-11T13:56:25Z",
            "user": "Thingles"
          }
        ],
        "title": "User:Thingles"
      }
    }
  },
  "query-continue": {
    "revisions": {
      "rvcontinue": 551074105
    }
  }
}
```
