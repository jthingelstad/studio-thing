---
microblog_id: 2964305
url: "https://www.thingelstad.com/2023/05/21/bitcoin-lightning-fun.html"
title: "Bitcoin Lightning: Fun, Fast, and Free-ish"
published: "2023-05-21T21:01:49+00:00"
post_kind: post
categories: ["Videos", "Crypto"]
---

I've been casually investigating [Bitcoin Lightning](https://lightning.network) for a while. Lightning is a Layer 2 network on-top of Bitcoin and promises nearly free instantaneous transactions. Apps like [Strike](https://strike.me) and [Cash](https://cash.app) support Lightning, but I got frustrated with them because it wasn't clear where Lightning was doing the work. Perhaps a good thing for normal use, but not great for learning the tech.

As [Bitcoin 2023](https://b.tc/conference) approached one of the objectives I had was to get first-hand experience with Lightning. ⚡️ I did some digging before getting to Miami and had [Wallet of Satoshi](https://www.walletofsatoshi.com) installed, and via [Strike](https://strike.me) transferred 100,000 or so Satoshis.

Before going further, a Satoshi is the smallest unit of Bitcoin and it is named after the creator of Bitcoin. 1 bitcoin = 100,000,000 satoshis. At current market 1 Satoshi is worth $0.00027, and $0.01 is worth 37 Satoshis. Satoshis are often referred to as "Sats". Sometimes people will say "Stacking Sats" which is to imply slowly building value in Bitcoin with small dollar purchases.

### First Transaction 

We arrived at the Miami Beach Convention Center early on Friday and desperately needed coffee. We queued up and noticed that they (and we would realize all vendors here) had [IBEX](https://www.poweredbyibex.io) terminals to accept Bitcoin payment using Lightning.

A little background, in 2015 I had gone on a [mission to buy something](https://www.thingelstad.com/2015/02/23/030629.html) with Bitcoin in Minneapolis. I couldn't find any merchant selling anything that would accept Bitcoin. I've long felt that Bitcoin is a great store of value, but have many times said that you would never use Bitcoin for day-to-day purchases. Transaction fees are high, and block times are not deterministic so you can’t confirm payment immediately.

<video controls="controls" playsinline="playsinline" src="https://www.thingelstad.com/uploads/2023/6ad3d2cf3b.mov" width="640" height="640" poster="https://www.thingelstad.com/uploads/2023/df8b0cde25.png" preload="none"></video>

**Lightning proved me totally wrong.** Thanks to Kerry for whipping out his phone to catch my very first Lightning purchase for some coffees and empanadas on video. 

The payment is instantaneous, and the fees are nearly free. The merchant put in the total amount I owed on their device, it generated a Lightning "invoice" that I scanned with my wallet, and after confirming payment it was done in a flash.

Amazing. 🤩

### Nostr & Damus

So how is it that I showed up in Miami with Wallet of Satoshi setup and ready to make Lightning transactions? 

- I knew Nostr was particularly popular in the Bitcoin world and thought it may be a good way to communicate at the event.
- Some micro.blog folks were playing around in Nostr using Damus on iOS, and Damus looked very polished.
- Damus connects with Lightning to allow "Zaps" on posts so you can "zap" some amount of Satoshis to other peoples posts.

Setup was pretty simple actually. I downloaded Damus and it walked be through getting my Nostr public and private keys setup. Damus had a list of Lightning wallets that worked with it and Wallet of Satoshi was the best rated in the App Store. And then I stumbled a bit but finally figured out how to send some Satoshis from Strike to Wallet of Satoshi. 

Off to the races! 🏇⚡️

**This is the first application experience I've ever used where micropayments really work.**

This is truly exciting to me as a potential way to fix the Original Sin of the Internet — building everything off of a surveillance economy funded by advertising! Traditionally micropayments are far too cumbersome to work. Zaps powered with Bitcoin Lightning are completely friction free. 

At the show Damus was selling (for 27,800 Sats) "Zap Me" buttons with an embedded NFC chip. When you bought it they associated the chip with your profile so people could tap the button with their phone and automatically be brought to your profile where they could send you a Zap! ⚡️

_PS: I’m planning to add Lightning options to thingelstad.com and the Weekly Thing to encourage folks to experiment._

### Login and Signing

Finally, Lightning also brings some functionality to Bitcoin that I've enjoyed for a long time with Ethereum. You can use your Lightning wallet to authenticate with a service, as well as signing messages. 

Over dinner I was able to authenticate and provision a Bitcoin mining unit just by signing in with Lightning.

Moving beyond passwords, and digital signatures to prove validity of content, are going to increase in significance over time and it is great to see Lightning bring that capability to the Bitcoin ecosystem.

---

During the 2 days of Bitcoin 2023 I relied almost exclusively on Bitcoin to pay for lunches, coffees, and anything else I wanted. I also took the opportunity to send Satoshis to some of the speakers and people that I met at the event. It was incredible. It gave me all the privacy and benefit of cash, along with all the benefit of digital money. 

<img src="https://www.thingelstad.com/uploads/2023/0970d6fabf.png" width="213" height="600" alt="Bitcoin Lightning wallet transaction history showing multiple sent and received payments in satoshis dated May 20 2023">

So my earlier assertion that Bitcoin is a store-of-value but not useful for day to day purchases? Wrong.

In fact I’m on the hunt to get a Lightning coin machine like the [one at the event](https://www.thingelstad.com/2023/05/20/this-bitcoin-atm.html) to have in my house. I'd love to be able to have people come over and get their first Bitcoin experience by installing a free Lightning Wallet, putting a quarter in a box and scanning a QR code to leave with 1,000 satoshis! 🥳
