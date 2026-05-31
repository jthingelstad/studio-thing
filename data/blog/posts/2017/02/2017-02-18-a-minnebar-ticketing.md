---
microblog_id: 1074737
url: "https://www.thingelstad.com/2017/02/18/a-minnebar-ticketing.html"
title: "A Minnebar Ticketing Proposal"
published: "2017-02-18T23:00:00+00:00"
post_kind: post
categories: ["Minnestar"]
---

I've recently put some thought into how tickets are managed for [Minnebar](http://minnestar.org/minnebar/) and [Minnedemo](http://minnestar.org/minnedemo/). I've been very close to these events for a long time, and on the board for several years now, while our ticketing process has remained *relatively* unchanged over that long time.

### The Problems

Why spend cycles thinking about the ticketing issue? I think there are some large problems with the way that tickets are managed.

**Timeliness**

The ticketing process encourages people to act immediately upon issuance and get tickets since they will all be taken immediately. Often people will take a ticket before they have even made sure they can attend. This timeliness requirement unfairly penalizes people that are occupied and not watching Twitter at that exact moment.

**Understanding Churn**

The current process reduces our ability to understand how many people have stopped going to our events. We routinely see a high number of "first-time" attendees, and along with that a high amount of churn. Is the churn because people weren't ready the second that tickets came out, or because they don't want to come?

**Redemption**

Many tickets go unused. We manage around this by predicting what percentage of tickets will be unused, but it is more art than science. The rushed nature of ticketing may decrease redemption rate as people just jump on tickets as quick as possible.

**Quantify Demand**

All of these events "sell out" (to the extent a free event can sell out) within minutes. This removes our ability to know the true demand for the events. If 800 tickets are picked up within 15 minutes of release, how many people wanted to go? 900? 3,000? That is anyone's guess.

### Limitations

When considering how to better manage tickets, it is important to consider some limitations.

**Identity Is Unknown**

There are numerous ways to manage ticket redemption that would focus on reputation. Mainly this is a means to solve redemption and put rules in place such as not being allowed a ticket if you don't use the last three tickets.

**Cannot Be Complex**

We've entertained some options that avoid identity and reputation but encourage careful assignment of tickets. The most commonly referenced one is to use some form of a cash deposit. For example, you would pay $5, $10 or $20 to get your ticket to the event and that money would be refunded back to you when you show up at the event. This would certainly reduce the number of unused tickets but at the cost of managing a significant amount of complexity and risk.

### Requirements

Before looking at the proposal let's recap from above what our requirements are:

1. The solution must not require managing identity. You cannot know a ticket holder from one event to another.
2. The solution would ideally allow us to understand how many people would like to come to an event.
3. The solution would be able to manage preferential access for certain groups.
4. The solution would allow for improving the precision of "no shows".

**It is important to note that while "no shows" are something to consider, I believe it is a lesser problem than understanding the true demand for the events, churn and making the ticketing process more equitable.**

### Proposal

Taking these objectives into place, I propose the following ticketing process.

**Phase 1: Get in line!**

First thing, get in line. Rather than distributing tickets in groups we propose everyone get in a line (or list) to attend. This line opens up at a prescribed date and time, and anyone and everyone that wants to come to the event would then get in line. The line will close at another prescribed time, but as long as the line is open more and, more people can get in line.

This line dampens the urgency to take immediate action. Please note though that Phase 3 does reward people for getting in line early. It is valuable to the organization to get a sense of demand quickly, so getting people in line sooner is a good thing. However, no matter when you get in line you may get a ticket.

**Phase 2: Priority Access**

Once the line is complete and closed we then deal with priority access. There are some groups that get priority access to the events and are guaranteed a ticket:

- **Volunteers**: Anyone volunteering at the event.
- **Community Supporters**: Individuals (not companies) in the community that have donated $100 in the last 12 months.
- **Sponsors**: Packages get different numbers of tickets. If you are in line under one of those slots you get a ticket.
- **Students**: We look to encourage high school students to attend our events, and wish to give them priority access.

Once these special groups have priority access, we've used some of the tickets and now have a smaller line.

**Phase 3: Ticketing Groups**

The remaining line is now divided into groups. This is where some further math and heuristics could be applied to better manage tickets over time. For now, just assume that all these numbers are potential variables and you could optimize the solution over time.

Take the remainder of the line, let's say there are 1,000 people still left, and for easy math put them in 5 groups of 200 people.

Each one of these groups is then ticketed. Remember that these groups are in the order they got in line, so the early people are in the front and the last person to get in line is at the end in position 1,000.

We also at this point know how many tickets were assigned to priority access groups and can make a determination about their "no show" rate. Likely those groups have a very high redemption rate, so assume most are used. The remaining tickets will be assigned to the five groups of 200 people in a decreasing percentage. All of the people in group 1 get tickets. 70% of the people in group 2 get tickets. 40% of the people in group 3 get tickets and so on until we get to something like 10% of people in group 5 getting tickets.

Over time these groups may be able to provide more accurate data on redemption, and we may know that Group 1 people redeem tickets at a higher rate than Group 5 so we can assign more tickets in Group 5 knowing more will go unused.

Additionally, it is important that any tickets that get returned before the event, when people realize they cannot come and notify us of that, should be returned to the group it was assigned to. So, if a person in Group 3 returns there ticket, it should go to another random person in Group 3. This could be managed by creating different classes or types of tickets for each group. If there are no people left in that group without a ticket, like Group 1, then flow the returned ticket to the next group in line.

### Summary

This may seem complex at first, but I think the implementation could be reasonable. Eventbrite could still be used to get in line but getting a "Line Ticket". The list of registered email addresses could then be manipulated with a small program to do the rest.

I do think that this would meet our goals of:

1. Understanding true demand for the events.
2. Allowing special access to some groups.
3. More fairly assigning tickets to the remaining people.
4. Minimizing the urgency around ticketing.
5. Optimize "no show" management over time.

Very importantly this would also help us understand people that stop coming to events. If you get in line we know you want to come, but if you don't get in line many times in a row you are deciding our events aren't worthwhile and we'd like to know that.

If you have suggestions or comments contact me. If you would like to help solution this that would be great too!
