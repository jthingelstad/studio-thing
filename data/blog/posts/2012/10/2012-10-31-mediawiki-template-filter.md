---
microblog_id: 1074928
url: "https://www.thingelstad.com/2012/10/31/mediawiki-template-filter.html"
title: "MediaWiki Template Filter Title"
published: "2012-10-31T05:00:00+00:00"
post_kind: post
categories: []
---

I was recently doing some cleaning on our [Read/Write Book Club](http://rwbookclub.com/) website and ran into an interesting challenge. All of the books in the wiki are in a couple of categories, but I wanted them sorted right ignoring A, An and The beginning of the title. MediaWiki supports this in the category tag allowing you to specify `[Category:Book|Sort Title]` and early on in the wiki I had a second field in the form for Sort Title asking the person editing the book to do this.

The result was nobody did it and all the books with "The" in the beginning of the title were all under T. Shouldn't this be easy to just deal with in the wiki itself?

Well, it turned out to be much harder than you would think in large part because MediaWiki doesn't honor spaces in template tags. My first attempt to do this was rather brute force, simply look for the three cases that I want to get rid of in the title and chop it off.

```
<includeonly>
{{#if:{{{1|}}} | {{#vardefine:title_filter_temp|{{{1}}} }}
{{#if: {{#pos:{{#var:title_filter_temp}}|The }} | {{#ifexpr: {{#pos:{{#var:title_filter_temp}}|The }} = 0 | {{#vardefine:title_filter_temp| {{#sub:{{#var:title_filter_temp}}|4}} }} }} }}
{{#if: {{#pos:{{#var:title_filter_temp}}|A }} | {{#ifexpr: {{#pos:{{#var:title_filter_temp}}|A }} = 0 | {{#vardefine:title_filter_temp| {{#sub:{{#var:title_filter_temp}}|2}} }} }} }}
{{#if: {{#pos:{{#var:title_filter_temp}}|An }} | {{#ifexpr: {{#pos:{{#var:title_filter_temp}}|An }} = 0 | {{#vardefine:title_filter_temp| {{#sub:{{#var:title_filter_temp}}|3}} }} }} }}
{{#var:title_filter_temp}}
| No parameter passed to [[Template:Filter title]]. }}</includeonly>
```

This worked in many cases, but not all. A book like [Antifragile](http://rwbookclub.com/wiki/Antifragile) got in trouble with this approach since the "An" matched it got sorted in "T". You would think this would be an easy fix right? Don't look for "An" but instead for "An ", including the space in the match. Unfortunately it is nearly impossible to pass a space into a MediaWiki template. MediaWiki effectively trims all template inputs of spaces so a space by itself becomes, effectively, null. A different approach was needed.

After some consideration I came up with this approach that uses the [Arrays extension](http://www.mediawiki.org/wiki/Extension:Arrays). I like it a lot more than the first attempt! The basic idea is to break the title into an array of strings on the space (note that `#arraydefine` allowed me to use a regex pattern to avoid the problem of not being able to pass in a space). I then check if the first element in that array matches a set of targets (in the `#switch` statement). If it does, set the index to 1, otherwise 0, and build a **new** array from that index offset. Like this:

```
<includeonly>{{
#arraydefine:filter_title_temp|{{{1|No title was provided}}}|/\s/}}{{
#switch: {{#arrayindex:filter_title_temp|0}}
 | A | An | The = {{#vardefine:filter_title_i|1}}
 | #default = {{#vardefine:filter_title_i|0}}
}}{{
#arrayslice: filter_title_new | filter_title_temp | {{#var:filter_title_i}} }}{{
#arrayprint: filter_title_new | _ | @@@@ | @@@@ }}{{
#arrayreset:filter_title_temp|filter_title_new}}</includeonly>
```

This works great with one exception. I still get confounded with the space problem when assembling the new title in the `#arrayprint` method. I decided to print the new title with underscores where the spaces were. Since this is used for the sorting condition, this is fine. The end user never sees the title and the wiki will sort right if given Title\_of\_the\_Book.

Now the sortable titles are all generated and the [Book Category](http://rwbookclub.com/wiki/Category:Book) page looks awesome.
