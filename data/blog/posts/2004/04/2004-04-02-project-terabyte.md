---
microblog_id: 1076527
url: "https://www.thingelstad.com/2004/04/02/project-terabyte.html"
title: "Project Terabyte!"
published: "2004-04-02T06:00:00+00:00"
post_kind: post
categories: []
---

A couple of months ago, not that long after I decided I needed [gigabit networking at home](https://www.thingelstad.com/2004/02/13/got-gig.html), I decided that I also needed a terabyte of storage at home. My reasons for this were:

-   I have my entire music collection, some 600+ CDs, stored as MP3
    files on my network and use it all the time. (And I'm not talking
    128kb MP3 here, I'm talking lame -alt-preset insane.

-   I have been taking digital photos now for 5 years and it's starting
    to take up real space. And similar to the music, my new Canon
    Digital Rebel is taking 7-10MB per raw image.

-   **Most importantly,** it seems that it's relatively easy now and I
    wanted to try it. (This is where I was wrong.)

When we remove limitations from systems it is amazing to me what we discover we are able to do. Given more processor, we find ways to use it. Given more bandwidth, it gets used. Applications march onward. And I'm curious to consider the applications possible if we can assume that every household has a terabyte of disk just sitting there. I actually believe strongly that an industry will form around this concept, but that is another posting for another day. Back to my Geek Fest.

I started this Geek Fest as many are started with too little information and a bliss that it would just be easy (as a friend of mine joked, "just like every other IT project eh?"). I wanted a terabyte of storage and it needed to be RAID. I also decided that PATA would not be acceptable, I wanted SATA. After looking around I decided there was a clear winning combination for me in the [3ware Escalade 8506-8](http://www.3ware.com/products/serial_ata8000.asp) card combined with 6 [Western Digital 200GB SATA](http://www.westerndigital.com/en/products/products.asp?DriveID=58) drives.

<img src="https://www.thingelstad.com/uploads/2020/7dc1973c98.jpg" alt="Six PATA hard drives laid out on a wooden table alongside a RAID controller card in its box, orange SATA cables, and power connectors, with bookshelves in the background." style="width: 199px; " />

<img src="https://www.thingelstad.com/uploads/2020/eee2715630.jpg" alt="Green PCI RAID controller card with multiple chips including a prominent Promise Technologies controller chip." style="width: 300px; " />

I ordered this up and waited for it to arrive thinking how easy this will be and why doesn't everyone have this stuff!? This is when my hubris was revealed.

I got the equipment and I knew that mounting it in the case was going to be a challenge. But when I grabbed the Escalade card I saw an immediate problem, the slots didn't match up. Yes, I had purchased a PCI 64-bit 66 Mhz card and my reasonable motherboard only had PCI 32-bit 33 Mhz. This was *minor hiccup number one*.

I started to look high and low for a solution but there are *very* few motherboards with PCI 64-bit 66 Mhz interfaces that are *not* server boards (there are a handful of 33 Mhz ones). All of a sudden I found myself facing a new motherboard, err, server board and to add some joy to the situation none of these boards took a P4 CPU, they were all Xeon, in fact, even better, they were all dual Xeon (yes, I realize you can just put one in, but it's not as cool!).

I sat on this for a couple hours as I debated and tried to decide how to convince my wife that in addition to the Escalade and the drives I now needed a new motherboard and a CPU, or two!

I decided to go all the way with this project and for the first time I was going to build a **real** server for home. None of this leftover desktop server, this was going to be a machine I could use for the next 3 years (or so I told my wife!). I decided that I would go with the [Asus PU-DL](http://usa.asus.com/products/server/srv-mb/pu-dl/overview.htm) motherboard and trick it out with 1GB of ECC RAM and two (what the heck!) Xeons at 2.4 Ghz. One of the selling points was the dual Gb ethernet on-board, including one of the ports which has a PCI-X 133 Mhz connection so I could actually transmit a full Gbps. Not to mention hyper-threading support so Windows would see 4 CPUs. This thing was going to scream. I was wary of one issue, the case. So I assured myself this was going to be fine since this was an EATX motherboard and my Antec case supports EATX form factors. Or so I thought...

This introduced *minor hiccup number two*. I eyed out the motherboard and it seemed like it would fit and indeed (however it sure had acreage!), it seemed to be okay. However, the dual Xeons which stand almost 5 inches off the board were in the way of the drive bays! To add further insult, it turns out my new server board requires a 24 pin ATX power supply connection and that great new 12V connector that came with the P4? Well, I need an 8pin version of that for the dual CPUs. I went to **literally** every mom and pop techie shop in town looking for cases and came up totally dry.

I did some searching online and I realized that I was going to need to make yet another investment in my Geek Fest, a new case. Now, cases are supposed to be simple, but not for this project. I ended up going with a [SuperMicro SC742T-550 Chassis](http://www.supermicro.com/products/chassis/4U/742/SC742T-550.cfm?PID=TWR). While I wasn't anticipating this, I have to admit I'm pleased that I went with this chassis. It was more money than I would have liked, but the integrated SATA hot-swap bays and the rack-mount capability is a nice thing to have in the future.

<img src="https://www.thingelstad.com/uploads/2020/6c2d12506d.jpg" alt="Large beige tower PC case with side panel open revealing multiple drive bays loaded with hard drives, sitting on a light wood floor." style="width: 225px; " />

<img src="https://www.thingelstad.com/uploads/2020/25d6afe698.jpg" alt="Open computer tower case viewed from above, showing power supply, bundled cables, and multiple empty drive bays on the right side." style="width: 300px; " />

<img src="https://www.thingelstad.com/uploads/2020/2e98a26a2f.jpg" alt="Open tower PC case with motherboard, expansion slots, two large case fans, and drive bays visible, partially assembled on a carpeted floor." style="width: 300px; " />

Just when you think my story is going to come to an end, along comes *minor hiccup number three*. I got the new case, sniffed it and took it to my waiting motherboard and drives. Now, I've built my share of machines and I have to admit this is the first time I've ever really felt over my head. Dealing with the cabling, all the cooling, the crazy jumpers on the server board was all a bit much. This wasn't your standard gamer box being put together. It gave me some renewed appreciation for the internal design that goes into those crazy 1U servers we buy.

Let me take a moment to talk about the processors. Mounting Xeons is an interesting chore. The chip requires you to bolt it's cooling assembly all the way through to the case because it is too heavy for just the motherboard. The heatsink is gigantic, and it comes with a plastic enclosure that makes the air more efficient as it goes over it. Pretty impressive. Asus also gave their own cooling assemblies that would have been easier to work with the motherboard, but they were noticeably smaller than the Intel ones so I opted for the OEM parts.

<img src="https://www.thingelstad.com/uploads/2020/edeb211417.jpg" alt="Two CPU coolers with fans mounted on red heatsinks installed side by side on a computer motherboard inside a PC case." style="width: 300px; " />

<img src="https://www.thingelstad.com/uploads/2020/4ee57edbf7.jpg" alt="Hand holding a small electronic component over a computer motherboard with fans and colorful heatsinks visible in the background." style="width: 300px; " />

After a few hours (really!) of getting everything right. I was ready to experience the magic. However, my wonderful 24pin ATX power connectors and 8pin CPU connector was 6 inches too short! I couldn't plug them in! Aargh!

So now starts *minor hiccup number four*. I needed to find extension cables to get these things to the server board. I searched and found a ton of 24pin to 20pin adapters. But found very few 24pin extenders. I finally found some online and was confused to find "orange cables" and "green cables". I figured this was up there with the glow-in-the-dark cables and fans with LEDs on them and just ordered the orange ones and thought nothing of it. To my great discontent I found out that [orange and green indicate different power standards](http://www.amtrade.com/pc_power/eps_wtx_ges_power_supply.htm) (link courtesy Chris Tersteeg)! The machine wouldn't power up when I connected it and when I inspected the cables I found the 24pin extension wasn't a straight-through. Wires were going every which way and some didn't go through at all!

I called the company and did some more research and found I just needed a straight through. They sent me that instead while I worried that I had fried my server board with the wrong power connector. Our story however ends with a happy ending as I plugged in the extender and the server roared (literally! 4 fans and 7 hard drives!) to life.

<img src="https://www.thingelstad.com/uploads/2020/8a7a2be7fb.jpg" alt="Open tower PC case with side panel removed, showing motherboard, red and gray ribbon cables, and multiple hard drive bays in a home office setting." style="width: 300px; " />

It's been running now for a couple of weeks. I've got 1.4 terabyte of disk in it formatted out in different ways to around 1 terabyte of usable storage. Everything has been working awesome and the RAID is performing great. The verdict of my project though is that a terabyte isn't reasonable yet for the average home user. However, I still think it will be there in say, 2 years.
