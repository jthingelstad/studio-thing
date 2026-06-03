---
microblog_id: 1074741
url: "https://www.thingelstad.com/2017/02/15/sending-email-to.html"
title: "Sending Email to OmniFocus Using Flow in Office 365"
published: "2017-02-15T06:00:00+00:00"
post_kind: post
categories: []
---

_This workflow is mainly for people that use Office 365 and are looking for an easy way to selectively put emails into OmniFocus or another task management system that can receive tasks via email._

I'm always looking for easier ways to move an email from my Inbox into [OmniFocus](https://www.omnigroup.com/omnifocus). I only put a small number of emails into OmniFocus, but I'd like it to be nearly automatic. Some emails I always want to send to OmniFocus, and for those I [use a mail rule](https://www.thingelstad.com/2016/03/16/email-rule-to.html) to automatically route. I also use [Sanebox](https://www.sanebox.com)'s [SaneFwd](https://support.sanebox.com/hc/en-us/articles/212617528-What-is-SaneFwd-and-how-to-use-it-) feature to do something similar. But those are only good when it is a sender that you *always* want to go to OmniFocus. What about when you selectively want to grab a couple emails?

I started wondering if I could do something with [Microsoft Flow](https://flow.microsoft.com/). For those that don't know, Flow is very similar to [Zapier](https://zapier.com) and is in the same category as [IFTTT](https://ifttt.com). I would put it closer to Zapier since it handles much more complex workflows with loops, conditionals and also connects to more complicated systems than IFTTT. Flow was [launched less than a year ago](https://flow.microsoft.com/en-us/blog/welcome-to-microsoft-flow/).

Mail rules can only fire on a mail activity, such as an email being received. Once it's received and in your mailbox mail rules don't have a trigger event. Flow, since it is directly integrated into Office 365, can see a bit more and has a trigger for "When an email is flagged". That caught my eye right away and within a couple of minutes I had this workflow for sending things to OmniFocus by flagging them in my Inbox. The "To" address should be your [OmniFocus Mail Drop](https://support.omnigroup.com/omnifocus-mail-drop/) address.

<img src="https://www.thingelstad.com/uploads/2020/1fc3a3dae0.png" alt="Microsoft Flow workflow with three steps: trigger on flagged Inbox email, get Office 365 user profile using From field, then send email to an OmniFocus sync address with Display name and Subject as" style="max-width: 509px; " />

Look at the 2nd step in the workflow to "Get user profile". I'd like these items to be associated with who the email came from, and my pattern for that is to prepend the persons name to the task seperated by a colon. Since Flow is part of Office 365, it can talk to Active Directory and get things like the "Display name" of the sender. I could also include their phone number or any other data that was in Active Directory as well.

I did also set two advanced options to avoid getting raw HTML in the OmniFocus task.

<img src="https://www.thingelstad.com/uploads/2020/3cb69e7819.png" alt="Two form fields in Microsoft Flow: Importance set to Normal, and Is HTML showing a dynamic content token labeled Is HTML." style="max-width: 509px; " />

This workflow works really well. It triggers quickly and is as frictionless as I think I can get. I also really like that Flow gives some extensibility if I wanted to pull in other data related to the person or message. Most of my limitations there are related to what Mail Drop can interpret.

Couple things about Flow:

1. While Flow allows you to author workflows on the iOS app I found it really clumsy. I'd do the authoring on a web browser and computer.
2. There are some really interesting options that can tie Office 365 with Azure Functions using Flow. You can see there is some brilliance here on how this is implemented.
3. If you like IFTTT and are in an Office 365 environment at work, you definitely should look at Flow. It has some powerful automation options.
