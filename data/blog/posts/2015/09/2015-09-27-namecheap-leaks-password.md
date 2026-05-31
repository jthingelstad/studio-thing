---
microblog_id: 1074767
url: "https://www.thingelstad.com/2015/09/27/namecheap-leaks-password.html"
title: "Namecheap Leaks Password in Security Notification"
published: "2015-09-27T05:00:00+00:00"
post_kind: post
categories: []
---

**Please make sure to see UPDATE section at end of this post.**

This isn't good at all. I have security notification alerts enabled in Namecheap because I want to know when something is changed related to my domains, just to make sure I'm always the one that initiated it. Today I changed my password and got this:

<pre>
Notification For     : PASSWORD
Date                 : 9/27/2015 4:15:28 PM  
IP Address           : 66.41.226.251
Username             : my-username
Domain (if relevant) : N/A

Old Details
-----------
my-old-password-in-plaintext

New Details
-----------
my-new-password-in-plaintext

Additional Information
----------------------
N/A     
</pre>

I've replaced the passwords that were in the email because they were my passwords, sent in plaintext, in email. This is pretty much terrible.

1.  Of course email isn't encrypted so now anyone that has sniffed that email knows my password, and my username is handily referenced as well (I changed it as well in this copy).
2.  This is evidence that Namecheap is storing my password in plaintext somewhere. They should only be storing the hash of it using something smart to protect it. Double bad!

The only good news is I have the optional two-factor authentication enabled that uses an SMS message to my phone so I at least have that to fall back on but this is a terrible security practice that I'm shocked Namecheap is doing.

**Please fix this immediately!**

*PS: After fixing this, can we get a real two-factor solution instead of SMS?*

### UPDATE (Sept 28)

Within minutes of sharing this post on Twitter I got a [response from @Namecheap](https://twitter.com/Namecheap/status/648344264724770816), and 17 minutes after that they [confirmed that they fixed this](https://twitter.com/Namecheap/status/648348503484162048).

Given how fast they fixed it I have to assume that what they fixed was issue #1, that they are suppressing the email notification for "PASSWORD" events. That is good and will keep the password from leaking into email, however I would really like to know if they are storing passwords in plaintext somewhere. It should be impossible for a service to tell you what your password is, they should only know some form of a hash derived from your password.
