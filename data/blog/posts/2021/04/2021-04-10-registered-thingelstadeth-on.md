---
microblog_id: 1299336
url: "https://www.thingelstad.com/2021/04/10/registered-thingelstadeth-on.html"
title: "Registered thingelstad.eth on ENS"
published: "2021-04-10T12:34:00+00:00"
post_kind: post
categories: ["Crypto"]
---

In my continuing exploration and learning about [Ethereum](https://ethereum.org/en/) I decided to setup what would be my usual entry on the [Ethereum Name Service](https://ens.domains) (ENS). The same way the [Domain Name Service](https://en.wikipedia.org/wiki/Domain_Name_System) (DNS) converts names like `thingelstad.com` into something computers can use, ENS can convert `thingelstad.eth` into the wallet address I prefer for Ethereum, and other crypto as well. 

ENS is a companion to DNS. Mostly it holds addresses for crypto destinations. It also can hold additional metadata like pointers to your Twitter and Github profiles, as well as your website, email address, and profile image. ENS is completely decentralized like all things on Ethereum. It is operated and governed via a series of smart contracts.

The process is super easy, as one might expect. You simply connect to your wallet. I use [Rainbow](https://rainbow.me/) for all my Ethereum dapps connections. To buy the domain name you execute a series of two transactions on the blockchain. In fact, all changes to your ENS entries are changes on the blockchain. Some of them have fees, and all of them cost Ethereum gas. After registering the domain, you have to set your resolver. The resolver is saying which contract should requesters ask for information from. Think of this as your DNS host records. You can then add any number of crypto addresses to your entry. I setup Ethereum (of course), Bitcoin, Litecoin, Cardano, and Filecoin. It is unclear to me that there is any benefit in setting up all of them, but that was the list I thought may get used. 

The last step is to create a reverse entry for your wallet. That is just like your Reverse DNS entry. Doing that allows dapps to show your friendly `thingelstad.eth` entry instead of the address. This is another transaction. 

You can [see the records for thingelstad.eth](https://app.ens.domains/name/thingelstad.eth), it is all setup. I also have the [reverse record set](https://app.ens.domains/address/0x2BdA946a7740b1dDB0fd5C226819170c4DD15720).  To test, [Etherscan Name Lookup for thingelstad.eth](https://etherscan.io/enslookup-search?search=thingelstad.eth) works as does the [reverse lookup](https://etherscan.io/enslookup-search?search=0x2bda946a7740b1ddb0fd5c226819170c4dd15720). Nice! 🙌

It was fun to do this and another opportunity to get familiar with dapps and Ethereum. Unfortunately this type of experimentation is extremely expensive right now due to gas prices being so high. The actual costs of doing all of the above are very low, but the gas prices to execute the transactions were more than 10x the cost of the thing itself. Right now this is like buying a $10 item on eBay and spending $100 to have it shipped to you.

Lastly, the ENS service operates as a token. My address, thingelstad.eth, is a token that only I own. It is kind of neat that it now shows up in my wallet as well!

<img src="https://www.thingelstad.com/uploads/2021/2bee890f39.png" width="375" height="274" alt="" />
