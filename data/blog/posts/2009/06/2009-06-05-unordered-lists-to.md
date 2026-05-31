---
microblog_id: 1075508
url: "https://www.thingelstad.com/2009/06/05/unordered-lists-to.html"
title: "Unordered Lists to Comma Separated List"
published: "2009-06-05T05:00:00+00:00"
post_kind: post
categories: ["Family"]
---

I was tweaking some layout in Tumblr today and I really wanted to take a list of tags and display them with proper grammar. For example, I wanted to have commas in the right places and to use the proper singular and plural forms as needed. My goal was something like.

*At 9pm with tags Mazie, Baseball and St. Paul Saints.*

Or, if there was only one tag.

*At 9pm with tag Mazie.*

The trick is that Tumblr only provides a way to iterate through the list of tags and you can't do any funky logic in there. This is actually a benefit, since it forced me to figure out the right way to do this with CSS. After a little searching I found a really old post from 2005 [explaining comma-separated list elements](http://milov.nl/2883) that was pretty close to what I wanted. I did some tweaking on it and came up with the following CSS block to do exactly what I wanted.

```html
/* Styling for a comma separated list of values from a ul */
ul.comma-separated { display: inline; list-style: none; margin: 0; padding: 0; }
ul.comma-separated li { display: inline; }
/* Put the correct label in front, this should be plural for multiple tags */
ul.comma-separated li:first-child:before { content:"tags "; }
/* The comma we are looking for. */
ul.comma-separated li:before { content: ", "; white-space: pre;}
/* The last element should not have a comma and should be followed with a period. */
ul.comma-separated li:last-child:before { content:" and "; white-space: pre;}
ul.comma-separated li:last-child:after { content: "."; }
/* Special case required to handle a ul with only one item. */
ul.comma-separated li:only-child:before { content:"tag "; }
```

This will take a block of HTML like this

```html
<ul class="comma-separated">
  <li>Mazie</li>
  <li>Baseball</li>
  <li>St. Paul Saints</li>
</ul>
```

and display it exactly how I want.

This was a great exercise. I'm not a CSS guru and I don't tend to look to CSS to solve this type of problem. I immediately wanted to start working some magic inside of a loop in the code and handle the logic there. This is much simpler, and has the huge benefit of being able to modify the contents after page load with Javascript and have the formatting dynamically adjust as needed.

Now I just need to move this super smart CSS into my WordPress site as well.
