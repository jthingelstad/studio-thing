---
microblog_id: 1696130
url: "https://www.thingelstad.com/2022/10/29/sign-a-message.html"
title: "Sign a Message to Verify an Ethereum Address"
published: "2022-10-29T16:28:24+00:00"
post_kind: post
categories: []
---

Cats Will Eat You posed a [question on Twitter](https://twitter.com/catswilleatyou/status/1586383014052757504) that I found interesting:

> What’s the easiest/free way to validate someone owns a wallet address?

Easiest way to do this that I know is to have the person sign a message with the address and send it to you. I used [MyCrypto Sign Message](https://app.mycrypto.com/sign-message) to connect to my wallet and sign a message. This gives a signature:

```json
{
  "address": "0x2BdA946a7740b1dDB0fd5C226819170c4DD15720",
  "msg": "This message is from thingelstad.eth!",
  "sig": "0x0827e88dce80cc03769aa34005f1d693be0247aecd433b49d6fa068df9965bde20047da38ac4aa0e51b6b914fd39b225843fa938817a0ced0a04b47a55b8b99e1c",
  "version": "2"
}
```

Take that message and use the [Verify Message](https://app.mycrypto.com/verify-message) tool and confirm that it was signed by that wallet. 🪄
