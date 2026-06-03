---
microblog_id: 1825217
url: "https://www.thingelstad.com/2023/03/04/transferring-nfts-in.html"
title: "Transferring NFTs in Bulk"
published: "2023-03-04T20:49:29+00:00"
post_kind: post
categories: ["Crypto"]
---

After I [created additional Ethereum addresses for specific applications](https://www.thingelstad.com/2023/03/04/isolating-crypto-assets.html), I wanted to move existing assets to align with that. 

### Ethereum Name Service

Moving ENS names is a special case. The ENS address is itself an NFT, but you cannot just send these to another address. You can move them, but you have to do it in the ENS application. For each of the 21 ENS names I have I did an on-chain transaction to move them to ens.thingelstad.eth. It was easy to do, and even though there was no bulk operation it wasn't hard to do. Each move incurred some gas fees.

### POAPs and NiftyInks

With over 70 [POAPs](https://poap.xyz) to move I really didn’t want to do these by hand. And with over 730 [Nifty Inks](https://nifty.ink/) it was out of the question to do it by hand. I looked at how to move POAPs and the FAQ recommended [uNFT Wallet](https://unftwallet.xyz). I connected my wallet via Gnosis Chain and uNFT Wallet already had the contract address for POAP and Nifty Ink. I was able to move most of my POAPs with [one transaction](https://gnosisscan.io/tx/0x47c8508461847499bc2ad221f80884b56037d6b5f1939d2997f02fdd683e48be) and a [second](https://gnosisscan.io/tx/0xf0ae5a20ac5c73f1877b8ec975b086e431a5699a7aab4e3fb2310a563c0b0c9c) after doing a [test](https://gnosisscan.io/tx/0x0552967068a5fd0fb5dca939e32c13db3dcdfe14f27693b2ad76fcb892318c0f). They are now in [POAP.thingelstad.eth](https://app.poap.xyz/scan/poap.thingelstad.eth).

I had never transferred POAPs between accounts and it is interesting that these now show on POAP as have 2 transactions. Some POAP apps like [Salsa](https://salsa.me) no longer show the same connections after doing this. I think that is fine, but it is worth noting. 

It was less simple with Nifty Ink since I was moving over 730 NFTs. uNFT Wallet refused to even try and move all of them in one go, and there wasn't a way to select 100 NFTs at a time. So I had to click groups of 60-90 of them and do a transaction each. After doing several of these, there were a handful of stragglers left that I actually used Nifty Ink to send to the other wallet. They are now all in [niftyink.thingelstad.eth](https://nifty.ink/holdings/0xb009e269060c0d6e652176c166c96c97965ca19f)! 🎨

### Thanks uNFT Wallet

There is no way I could have done this without a bulk tool like [uNFT Wallet](https://unftwallet.xyz). It was an easy choice to buy one of their Limited Edition supporter NFTs to help support the project.

<img src="https://www.thingelstad.com/uploads/2023/1dc0908513.png" alt="Colorful hedgehog-shaped NFT logo with zigzag spines, labeled xDAI Limited Edition ERC721, on a white background.">
