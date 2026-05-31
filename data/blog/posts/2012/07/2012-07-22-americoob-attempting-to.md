---
microblog_id: 1074947
url: "https://www.thingelstad.com/2012/07/22/americoob-attempting-to.html"
title: "Americoob Attempting to Siphon Traffic from USA Kubb"
published: "2012-07-22T05:00:00+00:00"
post_kind: post
categories: ["Kubb"]
---

I recently went to `usakubb.com` forgetting to use `.org` to go to `usakubb.org`, the website for the [US National Kubb Championship](http://usakubb.com/). USA Kubb got this site registered and setup this winter. The domain information shows it was registered on Feb. 26, 2012.

```
Domain ID:D164823449-LROR
Domain Name:USAKUBB.ORG
Created On:26-Feb-2012 01:23:56 UTC
Last Updated On:26-Apr-2012 03:50:06 UTC
Expiration Date:26-Feb-2014 01:23:56 UTC
```

When I put in usakubb.com though I was surprised that I got redirected to Americoob!

```bash
% curl --head http://usakubb.com/
HTTP/1.1 301 Moved Permanently
Date: Sun, 22 Jul 2012 19:11:49 GMT
Server: Apache/2.2.21 (Unix) mod_ssl/2.2.21 OpenSSL/0.9.7a mod_auth_passthrough/2.1 mod_bwlimited/1.4 FrontPage/5.0.2.2635 mod_fcgid/2.3.5
Location: http://www.americoob.com
Content-Type: text/html; charset=iso-8859-1
```

The same happens for usakubb.net.

```bash
% curl --head usakubb.net
HTTP/1.1 301 Moved Permanently
Date: Sun, 22 Jul 2012 19:12:18 GMT
Server: Apache/2.2.21 (Unix) mod_ssl/2.2.21 OpenSSL/0.9.7a mod_auth_passthrough/2.1 mod_bwlimited/1.4 FrontPage/5.0.2.2635 mod_fcgid/2.3.5
Location: www.americoob.com
Content-Type: text/html; charset=iso-8859-1
```

That seemed super lame. I knew USA Kubb wasn't sending traffic to Americoob. So I looked up the registration information for usakubb.com:

```bash
Domain Name: USAKUBB.COM
Registrar: GODADDY.COM, LLC
Whois Server: whois.godaddy.com
Referral URL: registrar.godaddy.com
Updated Date: 31-mar-2012
Creation Date: 31-mar-2012
Expiration Date: 31-mar-2014
```

...and usakubb.net:

```bash
Domain Name: USAKUBB.NET
Registrar: GODADDY.COM, LLC
Whois Server: whois.godaddy.com
Referral URL: registrar.godaddy.com
Updated Date: 31-mar-2012
Creation Date: 31-mar-2012
Expiration Date: 31-mar-2013
```

Americoob registered these domains about a month after USA Kubb registered the proper .org domain name. So Americoob bought these two domains that are completely unrelated to them so that they could siphon traffic away from people who think they are going to the USA Kubb website. Now people that forget to type the domain all the way will be sent to Americoob, the manufacturer of a plastic game similar to Kubb, but **isn't even Kubb**! 5 batons and 4 baseline Kubbs? Made of plastic?

This is **incredibly lame** on Americoob's part. I think people should clearly communicate to Americoob that they should hand these domains over to USA Kubb as soon as possible. Americoob is owned by Short Productions and can be reached at (215) 699-2328 and you can email them at <info@americoob.com>.

To make it easier, here is an email you can copy and paste to them:

> Americoob,
> 
> Your organization recently registered the domains usakubb.com and usakubb.net and are redirecting visitors to those domains to your website at www.americoob.com. I would like to request that you turn these domains over to USA Kubb, the owners of usakubb.org and the organization behind the US National Kubb Championship.
> 
> Your attempt to siphon visitors to USA Kubb that do not put in the full domain is bad for the very sport that you are  attempting to be part of and profit in. Please do the right thing and turn the usakubb.com and usakubb.net domains over to USA Kubb.
> 
> Thank you,
> 
> \[name\]

*Please note, I'm purposefully not adding any hyperlinks to Americoob so I don't send any traffic to them.*
