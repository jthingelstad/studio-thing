---
microblog_id: 807314
url: "http://micro.thingelstad.com/2012/02/25/why-mediawiki-needs.html"
title: "MediaWiki Templates"
published: "2012-02-25T12:33:00+00:00"
post_kind: post
categories: []
---

Why [MediaWiki](https://www.mediawiki.org/wiki/MediaWiki) needs [Lua](https://www.lua.org): 

```
{{#vardefine:
 time_delta|{{#expr:
  {{#timel: U|2/24/12}} - 
  {{#timel: U|{{#time: Y-m-d }} }}
 }}
}}
```
