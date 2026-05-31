---
microblog_id: 1074748
url: "https://www.thingelstad.com/2016/03/13/workflow-for-meeting.html"
title: "Workflow for Meeting Management in Email"
published: "2016-03-13T06:00:00+00:00"
post_kind: post
categories: []
---

I'm not sure why it took me a couple of decades to come up with this but I've had these mail rules in place for a little over a year, and they are great! After putting these in place, I was able to streamline my processing of meeting related notices and more importantly take action on the important messages.

### Folders

Create three folders in your mailbox like this:

<pre>
Meetings
├── Affirmative
└── Review
</pre>

The rules below will route mail into those three folders.

### Rules

Note that my email rules are for Office 365 and Exchange Online. These
would work directly in any Exchange environment, but I suspect that the
spirit of these rules could be put in place in any email/calendar system
with translation.

**Invitations**

My workflow for accepting meeting invites is completely unrelated to processing my email inbox. The first thing I want to do is get all meeting requests out of my inbox so I can deal with them while I'm planning out my day and week. I route these into my "Meetings" folder.

> **Rule:** Meeting Invitation
> 
> **After the message arrives and...**  
> the message is Meeting Request.
> 
> **Do the following...**  
> move the message to folder 'Meetings'  
> and stop processing more rule on this message

Typically first thing in the morning I process all items in this Meetings folder acting upon each request as appropriate.

**Actionable Items**

I want to take note of and possibly act upon three kinds of responses to meetings. These three rules catch these and places them in the "Review" folder. I review this folder right after going through the Meetings folder.

**Decline**

Action is required when people decline meetings. Declines are what made me evaluate how I process meeting notifications. The most common one for me is a repeating 1:1 with a declined occurrence. I would miss these declines and not cancel on the occurrence as the meeting owner. Then I would be waiting for the person to show up only to realize that they had declined the meeting weeks ago due to a planned vacation.

This rule will capture these declines so you can process them appropriately. By catching declines I'm able to make sure that all necessary people I've invited to a meeting are there, and we can have a productive session.

Note that this rule includes a forward as well. If you have someone who helps manage your schedule, forward these to that person as well so that they can take action on your behalf.

> **Rule:** Meeting Declines
> 
> **After the message arrives and...**  
> the message is Meeting Response.  
> and the message includes specific words in the subject 'Declined:'
> 
> **Do the following...**  
> forward the message to 'John Doe'  
> and move the message to folder 'Review'  
> and stop processing more rule on this message

**New Time Proposed**

Sometimes people don't decline but suggest a new time. Now I need to visit my calendar and see if this alternative time works for me and possibly everyone else. I put these in the "Review" folder and also forward a copy to anyone that may help me with this.

> **Rule:** Meeting New Time Proposal
> 
> **After the message arrives and...**  
> the message is Meeting Response.  
> and the message includes specific words in the subject 'New Time
> Proposed:'
> 
> **Do the following...**  
> forward the message to 'John Doe'  
> and move the message to folder 'Review'  
> and stop processing more rule on this message

**Forward**

Meeting forwards don't require revisiting the schedule, but I do want to know about it. It's worthwhile to know that someone decided to add another person to the conversation. Possibly we'll need a different room, or we may need to adjust the agenda.

> **Rule:** Meeting Forward
> 
> **After the message arrives and...**  
> the message includes specific words in the subject 'Meeting Forward
> Notification:'
> 
> **Do the following...**  
> forward the message to 'John Doe'  
> and move the message to folder 'Review'  
> and stop processing more rule on this message

**Meeting Acceptances**

Meeting acceptances are complete noise. The rules above make sure I see only actionable responses. These notifications I 'mark as read' and put in the "Affirmative" folder. I then delete them when a large number pile up. I could just as easily get rid of the folder and just delete these upon arrival, but I do like to see them there for some reason.

*It is critical that this rule is last!* If you put this rule ahead of the others, it will intercept important notices, and you'll miss them!

> **Rule:** Meeting Acceptance
> 
> **After the message arrives and...**  
> the message is Meeting Response.
> 
> **Do the following...**  
> mark the message as Read  
> and move the message to folder 'Affirmative'  
> and stop processing more rule on this message

### Optimize Schedule and Decrease Distractions

By using these rules I've been able to:

1.  Optimize my process for accepting meeting invitations,
2.  Completely ignore meeting acceptances, and
3.  Never miss that someone was unable to join a meeting and have a broken calendar when the necessary people aren't there.
