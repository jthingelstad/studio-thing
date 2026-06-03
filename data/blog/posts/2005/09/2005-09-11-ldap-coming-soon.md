---
microblog_id: 1076263
url: "https://www.thingelstad.com/2005/09/11/ldap-coming-soon.html"
title: "LDAP Coming Soon"
published: "2005-09-11T05:00:00+00:00"
post_kind: post
categories: []
---

I spent a few hours today playing around with LDAP (Lightweight Directory Address Protocol). Why? Well, it frustrates me that my webmail application and Thunderbird don't share address books. To add insult to injury, if Tammy has an email address of someone I can't just find it. And, while I've moved all email to the IMAP server so I can't lose anything on a client machine, that proverbial address book still sits there, not backed up, on each computer in the house. It's a mess.

So, I got a binary distribution of [OpenLDAP for Windows](http://lucas.bergmans.us/hacks/openldap/) and went to town. The installation parts of this whole project went fairly well, but learning the in's and out's of LDAP will take some further work. I installed [OpenLDAP](http://www.openldap.org/) and it seemed to be working, but how would I know? Turns out there aren't very good tools for working with LDAP directories. [phpLDAPAdmin](http://phpldapadmin.sourceforge.net/) came to the rescue! (Thank you [SourceForge](http://sourceforge.net/)!) I installed this great toolkit and was able to see my LDAP server for all of it's glory. As an aside, I had to have PHP:LDAP support which I didn't, so I upgraded to [PHP5](http://www.php.net/) with LDAP and all sorts of other goodies and then broke my [SquirrelMail](http://www.squirrelmail.org/) 1.4.5 install. Luckily I was saved by the not-really released SquirrelMail 1.4.6cvs tree which works (at least so far) with PHP5.

After all this, I added some LDAP schemas for things like [inetOrgPerson](http://www.faqs.org/rfcs/rfc2798.html) and started creating an address book. First thing I tried to do was create a record in [Thunderbird](http://www.getthunderbird.com/). Bzzt! Little known dirty secret, while Thunderbird can *read* from an LDAP store, it cannot write to one. I even installed the 1.5b1 release and it too cannot write to an LDAP directory. After cursing the people's email client briefly I found this was also true of the Address Book application in Mac OS X "Tiger". And while SquirrelMail works with LDAP, it also is read-only.

I'm going to stay the course though and find a web-based address book manager that uses LDAP as the back-end. There are a couple. (Yes, I could use phpLDAPAdmin but it is more for administration than daily use.) Then I will just have my email programs query the LDAP store for information as needed.

I started to think of all the stuff you can do with an LDAP server though -- anyone up for a recipe book using LDAP?
