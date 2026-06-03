---
microblog_id: 1075271
url: "https://www.thingelstad.com/2010/12/13/good-passwords-with.html"
title: "Good Passwords with 1Password"
published: "2010-12-13T06:00:00+00:00"
post_kind: post
categories: []
---

This morning I read the news about [Gawker having 1.3 million passwords taken from their servers](http://www.readwriteweb.com/archives/twitter_spam_attack_tied_to_gawker_security_breach.php). These passwords were attached to email addresses. What do you need to login to Amazon again? Email, got it. Password, probably have that to.

I read this article with a bit of smugness. I'm certainly a proficient user of the Internet and I know all the risks of sharing passwords, but until a couple of months ago I was as guilty as the worst offenders out there. I had three passwords, one that was really sloppy for sites that I didn't care so much about. Another for semi-secure sites. And a third that I used for stuff that mattered. But even that bit was sloppy and not really managed well. The password was short, could be brute forced, etc.

<img src="https://www.thingelstad.com/uploads/2020/e0e209f97d.jpg" alt="Circular app icon featuring a silver key overlaid on a blue glossy lock face with a metallic ring border" style="width: 170px; float: right; margin-left: 10px; " />

Then I decided to take the plunge and do passwords right. I had meant to do it forever, but just didn't get around to it. In fact, I'm a bit embarrassed to admit that even [having my PayPal account hacked](https://www.thingelstad.com/2009/10/23/unauthorized-transacations.html) didn't get me to "see the light" when it came to passwords. I knew I couldn't do this on my own, I needed a tool to help. I had bought 1Password forever ago in the first [MacHeist](http://www.macheist.com/) so I looked into the product again, liked what I saw, bought an upgrade to the newest version and was off.

### How to do it?

It's simple really. Here is what I did. I installed [1Password](http://agilewebsolutions.com/onepassword) on all my machines. I told it to ask me to save credentials, which it did very nicely in any browser I used. It synchronized everything between multiple machines and iPhones and iPads using [Dropbox](https://www.dropbox.com/referrals/NTE0NTQ5OQ?src=global). Great. Now just start saving passwords.

<img src="https://www.thingelstad.com/uploads/2020/5ce99ea632.png" alt="1Password sidebar showing three groups: Unfiled with 235 items, Bad Passwords, and High Security with 108 items." style="max-width: 188px; " />

I then set up a Smart Folder in 1Password and told it to filter anything that used a known bad password. As I was creating accounts this folder started getting full of insecure credentials. This gave me my to do list. I would then separately go to that folder and go to those sites and change my password to a unique, randomly generated string. In most cases I'm using a **very secure** 20 character random string.

To create this folder I just selected *File* and then *New Smart Folder* and saved the criteria as shown below. Note that it is critical to change the criteria to "any" of the following are true. The default is "all".

<img src="https://www.thingelstad.com/uploads/2020/98a62f3d81.gif" alt="Edit Smart Folder dialog titled Bad Passwords showing six rules with Password conditions, five set to is with redacted values, one set to begins with" style="max-width: 646px; " />

### Success!

I just did this for a month. Looping through, changing passwords. It wasn't that laborious actually. The biggest challenge is dealing with logins on the iPhone. 1Password has a really nice universal app that works on all iOS devices and synchronizes wonderfully thanks to Dropbox. Copy and paste as well as fast application switching is the critical bit here, without it the thing would fail. When I need credentials I double-tap to activate fast app switching and go to 1Password, copy the password, use fast app switching again, paste. All done!

As I write this I now have 196 logins to various websites, with 196 unique and very strong passwords. This makes me feel very comfortable with the security of my accounts.

### Other Benefits

I've found other benefits with 1Password. It turns out to be a great place to store software licenses. I now have 115 software serial numbers in 1Password that I can easily get to. I also like the Wallet section and have put the critical information that is in my leather wallet there for safe keeping. Lose my wallet? No worries, it's in 1Password.

### Passwords to Remember

All in I really like this solution. There are however two passwords that I found I cannot just throw random characters at because I have to remember them.

First, my Dropbox is the backdoor to getting at my 1Password information. If I'm on some foreign computer and I need to get a password, I can go to Dropbox and load my information using a great HTML hack that 1Password does. However, this means I need to remember my Dropbox password. So, this one I had to commit to memory with a special mnemonic.

I also found that my iTunes password needed to be committed to memory. It however ended up being 32 characters long, so I even tend to go to 1Password and copy and paste it. However, in a pinch I do know what it is and can laboriously type it in on an Apple TV for example.

Everything else is just stored away.

### Do it!

The web is not a safe place, and it's not a safe place to leave your buying capabilities protected with the password "password". I think most people don't really connect the dots that if one system, like Gawker, is compromised, that leads to a chain of further compromises that share those same credentials. Is it a pain at times to do this? Sure. But I have complete control over my accounts. Another side benefit to this is that you actually have an inventory of all the websites you have accounts at! I was amazed just how many websites I even have logins at, nearly 200! Time to delete some accounts!
