---
microblog_id: 1075791
url: "https://www.thingelstad.com/2008/10/07/lightroom-bit-printing.html"
title: "Lightroom 2 64-bit Printing"
published: "2008-10-07T05:00:00+00:00"
post_kind: post
categories: []
---

I was doing some printing in Lightroom recently and was struggling. The prints were coming out really badly, and when looking for the quality controls for the Canon S900 I couldn't find any of the normal settings. This is what it should look like, with options for the type of printing.

<img src="https://www.thingelstad.com/uploads/2020/cdec6e874c.png" alt="Canon S900 print dialog showing Quality and Media settings with Printing a composite document selected under Print Mode">

But instead I was getting this, with a big crossed out option and an incompatibility over "architecture".

<img src="https://www.thingelstad.com/uploads/2020/ba3d190410.png" alt="Mac OS X Print dialog showing Canon S900 printer with a QualityMedia483 bundle error stating it cannot load due to incompatible architecture.">

I was pretty confused why this wasn't working and figured I needed to reinstall my drivers, but didn't want to restart at that point so left it. I kept noodling this over and that word "architecture" was bugging me. Then it hit me!

I've posted before about how great [Lightroom is in 64-bit mode](https://www.thingelstad.com/2008/07/29/lightroom-in-bit.html). It dawned on me that I was running a "64-bit architecture" and the printer driver was probably only 32-bit. I checked the box for Lightroom to run in 32-bit mode and launched it again and the printer settings worked great! It sure would be nice if the error message just said "this doesn't work in 64-bit mode".

Lesson learned! Run Lightroom in 64-bit, unless you want to print, then restart in 32-bit. If anyone knows what printers have 64-bit driver support it would be great to have a list.
