---
microblog_id: 5584227
url: "https://www.thingelstad.com/2025/09/21/use-apple-intelligence-models-in.html"
title: "Use Apple Intelligence Models in Shortcuts"
published: "2025-09-21T14:00:00+00:00"
post_kind: post
categories: []
---

Shortcuts on OS 26 got a big new feature with the ability to use Apple Intelligence models directly. I've already had a taste of this by using OpenAI API calls in Shortcuts to add LLM capabilities. You can see [how I’m using AI in the Weekly Thing](https://www.thingelstad.com/2025/03/09/how-i-use-ai-in.html) for some examples. **Accessing LLM capabilities from Shortcuts is a very powerful capability for various automations.** I love how easy this now is with Apple Intelligence.

To compare, this is how I did it with direct calls to the OpenAI API. 

<img src="https://www.thingelstad.com/uploads/2025/shortcut-openai.png">

There is a lot of fussy stuff to do to get keys, pass dictionaries around, get the specific values, etc. And actually this is hiding the hardest of it all. If you expand that Get Contents of URL action you'll see this.

<img src="https://www.thingelstad.com/uploads/2025/shortcut-openai-api.png">

No way anyone without programming background is going to do this successfully. On top of it, my method for doing this is really brittle and prone to errors. I’m not catching all the possible API responses and if there is a problem it will just bail.

I’m also just kind of hoping that the response is JSON and I can marshal it into a variable. It works, but the prompt has to be right and you'll see I’m handling that in the API call. 

So, how about with Apple Intelligence and the built-in integration? Night and day difference. 

<img src="https://www.thingelstad.com/uploads/2025/shortcut-apple-intelligence.png">

Of course it is easier but it is so much easier. And one of the big wins is the output format. You can just tell it what you would like to get back. This avoids a ton of prompt engineering and parsing.

The only thing I lose with all this complexity is the ability to do a system message. For all of my use cases this hasn't mattered at all. I just merged the system message into the prompt.

This is so easy I would encourage a lot of experimentation to pull AI into your automation.
