---
microblog_id: 1074984
url: "https://www.thingelstad.com/2012/03/26/mediawiki-template-get.html"
title: "MediaWiki Template Get Hostname"
published: "2012-03-26T05:00:00+00:00"
post_kind: post
categories: []
---

I was working on a template for one my personal wikis and needed to get the hostname for a given URL. Using the capabilities of the [Parser Functions extension](http://www.mediawiki.org/wiki/Extension:ParserFunctions) for [MediaWiki](http://www.mediawiki.org/wiki/MediaWiki) I whipped up this template. I figured others may find this useful so here it is. The first version has a bunch of spaces and newlines added to make it more readable.

```
{{#vardefine: hoststart | {{#expr: {{#pos: {{{1|}}} | // }} + 2 }} }}
{{#vardefine: hostend | {{#pos: {{{1|}}} | / | {{#expr: {{#pos: {{{1|}}} | // }} + 2 }} }} }}
{{#vardefine: hostlen | {{#expr: {{#var: hostend }} - {{#var: hoststart }} }} }}
{{#sub: {{{1|}}} | {{#var: hoststart}} | {{#var: hostlen}} }}
```

To put it in your own MediaWiki, copy this version that removes the spaces and newlines.

To use this template put it on a page like
`Template:Get hostname` and then call it in your
pages as

```
{{Get hostname|https://www.thingelstad.com/another-reason-you-need-to-use-a-password-manager/}}
```

which will return `www.thingelstad.com`.
