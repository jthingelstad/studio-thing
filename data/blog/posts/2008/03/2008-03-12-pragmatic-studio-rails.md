---
microblog_id: 1075916
url: "https://www.thingelstad.com/2008/03/12/pragmatic-studio-rails.html"
title: "Pragmatic Studio: Rails Studio Day 3"
published: "2008-03-12T05:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/3094970c5e.png" alt="The Pragmatic Studio logo in gold and white text on a dark green background" style="width: 203px; float: right; margin-left: 10px; " />

Today was the last day of [Rails Studio](http://pragmaticstudio.com/rails/). [Dave](http://pragdave.pragprog.com/) and [Mike](http://www.clarkware.com/) took us through the finish line with a packed syllabus. We took our event application all the way through deployment.

Our final day was a little rushed. I would guess we had fallen about an hour behind the agenda. We covered the final leg of Rails stuff including completing the ActiveRecord discussion through to many-to-many relationships, the magic of filters and a great overview of using partials and AJAX in our applications.

Probably the only oversight in the class was the coverage of testing in Rails. Due to schedule, we had to cover all of the `rake test` world in _an hour_. An hour isn't a lot of time to cover what is really a pretty complete and powerful test environment that is built right into Rails. The oversight here was more pronounced, as early on testing was highlighted as one of the critical things you have to do in your app. We really didn't get enough coverage of this. I wouldn't want a fourth day in the class, which is likely what would be required to cover testing well, so I guess a hurried overview to get you started is probably the best that can be done.

To end the class we deployed the application via Capistrano to a production server. The Capistrano system really impressed me as being elegant and extensible.
