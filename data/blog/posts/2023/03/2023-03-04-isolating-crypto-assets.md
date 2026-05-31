---
microblog_id: 1825186
url: "https://www.thingelstad.com/2023/03/04/isolating-crypto-assets.html"
title: "Isolating Crypto Assets and Access"
published: "2023-03-04T19:44:49+00:00"
post_kind: post
categories: ["Crypto", "POAP"]
---

For the last couple of years I've done all of my Ethereum activities using my thingelstad.eth address with the associated identity. I've used this for storing value, holding NFTs, collecting POAPs, and everything else. I decided that it was time to create some isolation of access and identity.

I’m still using **[thingelstad.eth](https://rainbow.me/thingelstad.eth)** as my primary address and means of authenticating with various services. It also holds a number of my NFTs and crypto assets. But I've also now created two activity-specific addresses.

**[mint.thingelstad.eth](https://etherscan.io/address/0x2b364d520481b732f5aecf67a5f32b0bacd40b17)** is the address that I’m using specifically just to mint NFTs. When you mint NFTs you have to authenticate with a new smart contract and usually provide some form of limited access to your assets. By using a dedicated address just for minting I can limit the risk of a malicious smart contract.

**[vault.thingelstad.eth](https://rainbow.me/vault.thingelstad.eth)** is the reverse of the minting address. This address is specifically to hold NFTs or other assets that I have no intent of selling or transferring. This address will never be used to authenticate to any website. All activities here will be done using wallet transfers.

Additionally, I decided to create some specific addresses for applications that I use a lot. This was inspired in part from [Vitalik's conclusion](https://vitalik.ca/general/2023/01/20/stealth.html):

> That said, it is my view that wallets should start moving toward a more natively multi-address model (eg. creating a new address for each application you interact with could be one option) for other privacy-related reasons as well.

I love the idea of wallets automatically associating a unique address with each application. I do this today by using a masked email addresses with [Fastmail](https://www.fastmail.com) and passwords managed by [1Password](https://1password.com).

**[ens.thingelstad.eth](https://rainbow.me/ens.thingelstad.eth)** is the address I’m using to hold my [Ethereum Name Service](https://ens.domains) registrations. ENS has built in capability for one address to register a name, and the control of that name to be delegated. So all of my 21 registered ENS names are now owned by this address, and control of them is delegated to thingelstad.eth. The only app that will ever connect to this address is ENS itself, which protects my name registrations from malicious actors.

**[POAP.thingelstad.eth](https://app.poap.xyz/scan/poap.thingelstad.eth)** is an address I've made just for collecting [POAP](https://poap.xyz) tokens. I currently hold 90 different POAP tokens in this address. This allows me to have a specific identity and address just for POAP usage. Most activity for this address is on [Gnosis Chain](https://www.gnosis.io) since that is what POAP uses natively.

**[niftyink.thingelstad.eth](https://nifty.ink/holdings/0xb009e269060c0d6e652176c166c96c97965ca19f)** is an address just for using [Nifty Ink](https://nifty.ink/). I've collected 736 "inks" on this site and now I have them isolated into an address that I only use for that purpose. 🤩 This is again a way to limit access from a malicious smart contract. 

Technically I also have **[reddit.thingelstad.eth](https://etherscan.io/address/0x2c30f7b24caf8026a092bbe5e08c32fa31533f34)** but was created by necessity since Reddit Vaults are managed differently. However, it serves the same pattern as the other application specific addresses.
