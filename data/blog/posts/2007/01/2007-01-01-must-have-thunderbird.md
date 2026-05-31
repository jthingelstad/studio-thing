---
microblog_id: 1076110
url: "https://www.thingelstad.com/2007/01/01/must-have-thunderbird.html"
title: "Must Have Thunderbird Add-Ons"
published: "2007-01-01T06:00:00+00:00"
post_kind: post
categories: []
---

I'm not one of these folks that scours the internet for Firefox
extensions only to make my web browser slower and crash more often.
However, I've recently been really frustrated by some shortcomings in
[Thunderbird](http://www.mozilla.com/en-US/thunderbird/) (email client)
and thought I would share some findings.

I use Thunderbird on five different computers popping in and out all the
time. My mail server is IMAP-based so that is fine, the same messages
are there no matter what computer I use. However, not the address book!
This has been driving me nuts. **[Addressbook
Synchronizer](http://www.ggbs.de/extensions/AddressbooksSynchronizer.html)**
has come to the rescue however! This great extension allows you to copy
your address book to a network location (including an IMAP folder which
is great!) and get the updated one on startup. I now have 5 different
address books and they are completely in sync, including the two
built-in to Thunderbird. If you use Thunderbird on multiple machines,
you need this extension.

There are two other extensions that are immensely useful. **[Contacts
Sidebar](https://addons.mozilla.org/thunderbird/70/)** restores a
feature that Outlook Express had but Thunderbird lacked. It shows your
address book in a pane on the left side of your message window. Nice to
drop notes to people in your address book. Also look into **[Duplicate
Contact Manager](https://addons.mozilla.org/thunderbird/2505/)**, it
does a great job of chugging through your address book and culling out
"dups" for you.

Also, in case you are interested [I did setup an LDAP
server](https://www.thingelstad.com/2005/09/11/ldap-coming-soon.html) using
[OpenLDAP](http://www.openldap.org/) and try to just have all my mail
clients use the LDAP repository. I got the LDAP server setup, but there
were huge problems. A little hidden secret of most personal mail
clients, including Thunderbird, is that it can read an LDAP repository
but cannot modify or add to it. This is a non-starter.
