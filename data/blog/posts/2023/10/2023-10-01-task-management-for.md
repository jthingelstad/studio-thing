---
microblog_id: 3573157
url: "https://www.thingelstad.com/2023/10/01/task-management-for.html"
title: "Task Management for the Weekly Thing"
published: "2023-10-01T15:18:19+00:00"
post_kind: post
categories: ["Crypto", "POAP", "Weekly Thing"]
---

I’m often asked about how I create the [Weekly Thing](https://weekly.thingelstad.com/) and how I've been doing it for over **six years**. People are usually curious about how I find things to write about or [how I build the Weekly Thing](https://www.thingelstad.com/2023/09/24/how-i-build.html). However, there is a critical part that is invisible to others but key to the consistency of sending every week for 262 issues — project management!

With the recent rebuild of my automation I needed to update my project template which seemed like a good time to share how I do this. I’m a [Getting Things Done](https://gettingthingsdone.com) practitioner, and my tool of choice for as long as I can remember has been [OmniFocus](https://www.omnigroup.com/omnifocus/). Everything here is in OmniFocus or supporting automation.

A detail to share on dates and times for the publishing schedule. My target for sending the Weekly Thing is Saturday at 7:00 am CT. If I miss that it’s fine, I can shift things. However, the content cutoff is actually Thursday at 11:59 pm CT and that never changes. This allows me a window from Thursday night to Saturday at 7:00 am CT to publish. One odd side effect of this is that a blog post I publish on Friday will not be in that issues Journal on Saturday, but will wait for the following week. Nobody seems to notice this and it is necessary for me to have the time to do the publishing.

### Project

Here is what the project to send Weekly Thing 264 looks like in OmniFocus. The two dates on the right are the defer and due dates. Defer dates are critical for me since they keep things off my plate until they need to be. Note everything in gray is deferred. You can see that right now, there are only three tasks available. I've expanded select tasks so that you can see the helper links and text that make things a bit faster for me.

<img src="https://www.thingelstad.com/uploads/2023/weekly-thing-project-template-expanded.png" width="600" height="539" alt="">

There are four major steps to publishing each issue:

1. **Creating Content**: Most notable activities here include writing the introduction, adding any "Currently" topics, taking and setting the picture for the week. Some of these I can do immediately, others I defer until a few days into the week. The writing is done in [Drafts](https://getdrafts.com).
2. **Curating Links**: I try to curate links and various points through the week, but I have two "deadlines" for the publishing cycle. Links are curated in [Pinboard](https://pinboard.in/).
3. **Building and Sending**: Content and Links are done, time to build and send. I've automated this to be pretty simple. See [how I build the Weekly Thing](https://www.thingelstad.com/2023/09/24/how-i-build.html) for more.
4. **Finalizing**: After the issue is sent and in peoples mailboxes, I need to do some final activities and most importantly create the project for the next issue.

All of these steps are sequential. And the tasks in them are sequential, except for Creating Content which can be done in any order.

### Repetition

This project is **not** a repeating project. That is the reason for the last step in the project, to create the next project. Why not repeating? 

1. **Changes**: Not having it repeating means I can change and alter any given instance however I like. I might add a special task to one issue, like adding a POAP for the anniversary issue. Or a special section I’m only doing that time.
2. **Schedule**: I may move the due dates for one step or another and I love knowing that will not persist to the next iteration.

So how do I get the repeating project without doing all the work? Plus, there are tons of date references that need to be calculated, where does that come from? This is where [TaskPaper](https://www.taskpaper.com) and [project templates](https://www.thingelstad.com/2017/05/19/using-project-templates.html) come to the rescue. 

TaskPaper allows me to have a template for sending the Weekly Thing that I can "run" via a Shortcut. You can see the [Send Weekly Thing Taskpaper Template](http://files.thingelstad.com/posts/2023/send-weekly-thing.taskpaper) for all the details. Take note of two special "tokens" in the template: «Issue» and «Date». These are not part of TaskPaper, but instead two "variables" I handle.

Before I hand OmniFocus the TaskPaper to create the project, I’m going to process those two tokens using a Shortcut. My [Send Weekly Thing shortcut](http://files.thingelstad.com/posts/2023/Send%20Weekly%20Thing.shortcut) will get the "Publish Date" and "Issue Number" from [Data Jar](https://datajar.app). It will set those "variables" in the TaskPaper and the rest of the data offsets are [magically handled by OmniFocus](https://support.omnigroup.com/omnifocus-taskpaper-reference/). Most critical thing here is making sure I format the «Date» as `yyyy-MM-dd hh:mm aa` so that OmniFocus understands it.

The Shortcut also puts a time block on my calendar for Thursday night to send the issue. This is a nice benefit of combining Taskpaper and Shortcuts together.

<img src="https://www.thingelstad.com/uploads/2023/shortcut-send-weekly-thing.png" width="600" height="594" alt="">

### Summary

Creating the Weekly Thing isn't a single "Send Weekly Thing" task on my list. Instead I've focused on "next action thinking" to try and make each component a simple task. Overall this works really well for me. It doesn't solve writers block, but frees me up to focus on the creative aspects instead of the tasks.

You might be curious how this works when I take my summer or winter breaks? In those cases, I still create the next project for the issue when I come back from break, but then I set the defer date for the whole thing to the week before that issue publishes. I also usually add a housecleaning task to the beginning of that issue to clean out my Safari Reading list and Pinboard Unread links.
