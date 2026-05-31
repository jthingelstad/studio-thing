---
microblog_id: 5468439
url: "https://www.thingelstad.com/2025/07/06/vibe-coding-poaprss.html"
title: "Vibe Coding POAP2RSS"
published: "2025-07-06T17:05:41+00:00"
post_kind: post
categories: ["Crypto", "POAP2RSS"]
---

Ever since I created my first POAP drop I've wished that I could see claims of POAPs in Feedbin. What a great way to keep informed of the tokens that people are claiming! As I created more POAPs I realized that I also would like to subscribe to other people and see what POAP events they are claiming. And as I played around more with them I realized it would be so useful to be able to hook POAP claims up to automation platforms like IFTTT, Zapier, or Make — all of which support RSS out of the box!

I've been going deep on all things AI and I wanted to experience vibe coding for real versus just reading blog posts about others doing it. I’m a big believer in playing directly with tech to learn it. So, why not try creating the thing I've always wanted with POAPs by vibe coding it? 

I've now successfully created, and already an extensive user of, **[POAP2RSS](https://www.poap2rss.com)**! This simple service allows you to subscribe to RSS feeds for POAP events as well as addresses of collectors. It is magical and I love it already! 

Don't know what Vibe Coding is? Let's keep the vibe and ask AI.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">What is vibe coding?</div>
  <div class="author left">GPT-4o</div>
  <div class="message left">
Vibe coding is a modern approach to software development that emphasizes creativity and collaboration with AI tools. It involves expressing coding intentions in plain language, allowing AI to transform these ideas into executable code, often without deep technical knowledge from the user. This method focuses on maintaining a creative flow and minimizing micromanagement in the coding process. The term was popularized by AI researcher Andrej Karpathy and is gaining traction as a way to democratize coding and make it more accessible to non-programmers. <a href="https://x.com/karpathy/status/1886192184808149383?lang=en">Karpathy</a> <a href="https://www.ibm.com/think/topics/vibe-coding">IBM</a> <a href="https://simonwillison.net/2025/Mar/19/vibe-coding/">Willison</a>
  </div>
</div>

Let's go! 🔥

### Vibe Prototyping

First I’m going to share that I only realized I was prototyping a solution in retrospect. What I really did was go to Claude and start a new conversation.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">Please create a Python function to run in AWS Lambda that will retrieve the list of collectors for a comma separated list of POAP Event ID's and then merge them into a single RSS feed. The items in the feed should include information for each token minted.</div>
  <div class="author left">Claude</div>
  <div class="message left">I'll create a Python function for AWS Lambda that retrieves POAP collectors and generates an RSS feed. This will use the POAP API to fetch token information and create a properly formatted RSS feed.</div>
</div>

It created a new artifact and put about 250 lines of Python code in there. Voila! Now what?

Let me qualify my skills here. I can bang around in most languages reasonably well. I can navigate Python the best. I can read code very well. I’m pretty basic when it comes to writing it. I’m a solid scripter but can quickly get out of my league. This Python code was better than anything I could do but I was able to navigate it easily enough.

But what do I do now? I have an AWS account and have setup S3 buckets. I've never setup a Lambda function though. Let the vibes flow… 

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">How do I setup the Lambda function?</div>
  <div class="author left">Claude</div>
  <div class="message left">I'll guide you through setting up the Lambda function step by step. Here are the complete instructions:</div>
</div>

I got another artifact now with step-by-step directions on what to do in the AWS Console. Brilliant! 

I followed the directions and then actually ran a test, which Claude told me how to do.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">I ran this with a known valid event_id and I got this error:<br/>
<br/>
<code>{ "statusCode": 404, "body": "{\"error\": \"No tokens found for provided event IDs\"}" }</code></div>
  <div class="author left">Claude</div>
  <div class="message left">The issue is likely with the POAP API endpoint or authentication. Let me search for the current POAP API documentation to see what's changed.<br/>
…<br/>
Great! I found the issue. The POAP API now requires API keys for <a href="https://documentation.poap.tech/docs/authentication">authentication</a>, and the endpoint documentation shows that you need to include the header <code>X-API-Key={apikey}</code> where <code>{apikey}</code> is your unique API key. Also, the correct endpoint for getting event tokens is <code>/event/{id}/poaps</code> which returns paginated info on the token holders including the token ID, POAP transfer count, and the owner's information like address, amount of POAPs owned, and ENS.</div>
</div>

Claude and I went back and forth like this for a while with me running the Lambda, an error coming back, me sharing the error back to Claude, it making updates and me applying those. And then… 

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">it worked!</div>
  <div class="author left">Claude</div>
  <div class="message left">Excellent! 🎉 That's fantastic news! You now have a fully working POAP RSS feed generator.</div>
</div>

I hit a big stumble getting routing working through API Gateway to the Lambda function and Claude corrected me when I started going the wrong way.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">CORS is not enabled. Is that a problem?</div>
  <div class="author left">Claude</div>
  <div class="message left">CORS isn't the issue here! CORS only affects browser-based requests when JavaScript tries to access your API from a different domain. Since you're getting a response (even if it's an error), the request is reaching your Lambda function fine.</div>
</div>

Okay Claude — got it! 🫡

After this session I had a working prototype. The code was ugly. It turned out we needed to include OAuth support and added that much later. The design of the API endpoint was bad but it was working. It only took about an hour but I had explored this surface area deeply. I knew broadly what the service should look like, what some of the edge cases were going to be, and what was required to integrate with the POAP API. 

Now to come back later and turn this into something that would be real. I was about **1 hour** into exploring this topic and now knew a lot.

I deleted the Lambda function and all of the configuration I had created. It was created trial and error and I wanted to now be more rigorous. 

### Expand Features

Creating the prototype gave me a bunch of notes and a much better understanding of what was going to be needed to make the solution work right. I wanted to make sure I wasn't missing some things so I decided to turn to ChatGPT o-3 and Deep Research to explore the necessary features.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">

Please help me explore and expand the features for POAP2RSS service that provides an RSS feed to subscribe to claims from a POAP event. The POAP events do not have an RSS feed, so I want to create a service that provides an RSS feed for a user using the POAP API to populate the data. 

I’m already considering:

- Only include entries for most recent 20 claims
- If no claims in 4 weeks, add an entry that states that and suggests the user remove the feed. Change this for every additional week and change the RSS feed ID so it will show up as new to the user.
- Provide ENS names in the RSS item and set the Author of the item to the ENS name or address that claimed the token. Set the date and time of the item to the collected time.
- Add an initial item to all feeds that shows the description of the POAP Event and uses the timestamp for the event.
- Use DynamoDB to cache results from POAP API for 15 minutes

  </div>
  <div class="author left">GPT-4o Deep Research</div>
  <div class="message left">

Could you share more about the user audience and the intended use cases for the POAP2RSS service? For example, is it for collectors to track participation, for event organizers to monitor engagement, or for public observers? Also, are you targeting a particular feed reader or platform? This will help tailor feature ideas to your goals.

  </div>
  <div class="author right">Me</div>
  <div class="message right">

It is for any user including all three of those, however I suspect it will be most frequently used by the creator of the POAP event to monitor claims. I also expect it will be used in Automation -- for example to send a message anytime a claim is made by connecting the RSS feed to something like Zapier. The RSS feed should be fully standard so it can be used in any way desired.

  </div>
  <div class="author left">GPT-4o Deep Research</div>
  <div class="message left">

Thanks, that context is very helpful. I'll explore and expand on potential features for the POAP2RSS service that creates a standard RSS feed from POAP event claims, targeting usability for event creators, collectors, and automation tools like Zapier. I'll also examine best practices from similar services and technical considerations for maximizing compatibility and reliability.

I'll get back to you shortly with ideas and suggestions.

  </div>
</div>

o-3 then went off for about 10 minutes to do some research. I decided to watch it and had a real chuckle when I noticed that Deep Research was reading my own blog! It turns out over the years I've written about things that POAP could add [including RSS feed support](https://www.thingelstad.com/2023/01/14/poap-wishlist.html). Actually [multiple times](https://www.thingelstad.com/2025/01/05/poap-rss-awesome.html).

**After this was done I had a [full feature description](https://github.com/jthingelstad/POAP2RSS/blob/main/docs/service%20description.md) for POAP2RSS!**

I read through it all and felt together we had vibed the right set of things to consider in creating this solution. Now to make this thing work!

### Create Service

With the features of POAP2RSS now figured out it was time to build the solution. I was comfortable with how Claude had worked for this Lambda function in the prototype so I went back to Claude and attached the full document for the features along with a prompt to code it.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">

I'm attaching a description for a service I would like to create called POAP2RSS. I would like you to write the Lambda function that would meet these requirements.

**Relevant information**

- Please write this using Python and structure it for a Lambda function.
- It is okay to use Python packages such as Requests, or others to make the code more manageable and readable.
- Make sure to include relevant information for logging to Cloudwatch.
- Note the caching requirements included and the use of DynamoDB.
- The POAP API requires an API token. I have obtained a token from POAP and it can be provided via an environment variable.
- The POAP API requires an authentication token. I have the necessary Client ID and Client Secret and can be provided by an environment variable.

**Regarding authentication**

Here is an example from POAP to retrieve an authentication token.

```
curl --location --request POST 
  --url 'https://auth.accounts.poap.xyz/oauth/token' 
  --header "Content-Type: application/json" 
  -data '{
  "audience": "https://api.poap.tech",
  "grant_type": "client_credentials",
  "client_id": "$clientid",
  "client_secret": "$clientsecret"   }'
```
  </div>
  <div class="author left">Claude</div>
  <div class="message left">

Looking at your POAP2RSS service requirements, I'll create a comprehensive Lambda function that implements all the specified features. This will be a substantial implementation, so let me build this as a complete solution.

  </div>
</div>

Claude's comment on "substantial implementation" made me chuckle.

I had a big miss in my ask though — I never told it what URL POAP2RSS would run on and what the path for the endpoints should be! Ugh. 

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">

I forgot to tell you the URL that this service will run on. Please use the hostname `app.poap2rss.com` and then put the API (or RSS feeds) endpoints at `/event` and `/address` instead of in a `/feed` directory.

  </div>
  <div class="author left">Claude</div>
  <div class="message left">

Perfect! I've updated the Lambda function to use the correct hostname and endpoint structure:

  </div>
</div>

This was a little interesting to me since an actual developer working with me would have **never** just assumed they knew this. They would have stopped and requested clarification since this is such an obvious miss in the request.

This version of POAP2RSS had more complexity with the caching in DynamoDB. I needed a good set of documentation to know how to create everything in AWS Console. 

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">

Excellent. Please create a document with the instructions to configure the necessary services in the AWS console.

  </div>
  <div class="author left">Claude</div>
  <div class="message left">

I've created a comprehensive AWS setup guide that covers all the necessary services and configurations for deploying your POAP2RSS service.

  </div>
</div>

With that Claude created a seven step detailed [deployment document](https://github.com/jthingelstad/POAP2RSS/blob/main/docs/aws_setup_instructions.md). Nice!

At some point here I hit a significant issue with the SSL Certificate being configured right to route through API Gateway and on to the Lambda function. I kept getting issues with the certificate being incorrect. This blocked me for about an hour as I was trying to debug things. I finally found that I had the Cloudfront configuration incorrect and pointing to the wrong resources. Ugh! 

With that issue solved I had a fully deployed service and it was working exactly how I wanted it to work. Notable to me:

- OAuth and API keys were never even something I needed to consider, it just worked.
- If Claude could have talked directly to the AWS APIs it could have set this up _way_ faster than I could. I could have had it create a Cloud Formation script as an alternative.

This round took me about **2 hours** to get working entirely. 

### Get Professional

I now had POAP2RSS working and working well. I now wanted to get this cleaned up and something I could maintain. I created a new repo in Github for POAP2RSS and moved the prompts, docs, and source into the repo. 

I now wanted to explore what I could do with OpenAI Codex. I attached Codex to the code and asked it. (I’m abbreviating Codex's responses. It is fairly verbose and detailed and would be too much to include all of. It also has complicated buttons and links that are hard to replicate.)

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">
Familiarize yourself with the repo.
  </div>
  <div class="author left">Codex</div>
  <div class="message left">
The repository appears ready for deployment with AWS resources, focusing on delivering real-time POAP claim data through standard RSS feeds. The main Python Lambda implementation is self-contained and designed for use in an AWS environment with caching via DynamoDB and POAP API calls authenticated through environment variables.
  </div>
</div>

Codex operates much differently. It creates a whole development environment for every ask, gets all the code from the repo, and does whatever it needs. I then asked it a really general question.

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">
look for bugs in the lambda function
  </div>
  <div class="author left">Codex</div>
  <div class="message left">

**Potential bugs in `src/poap2rss_lambda.py`**

1. **Typo in channel description**: The RSS channel description is spelled “Acvitity” instead of “Activity.”
2. **HTML in item descriptions gets escaped**: The code builds HTML snippets for RSS descriptions but assigns them directly to `.text`, causing `<div>` and other tags to be escaped rather than rendered.
3. **Incorrect link target for claimant address**: Claim items link to `https://collectors.poap.xyz/scan/{display_name}`. If `display_name` is shortened or an ENS name, the URL may not resolve properly.

These changes will correct output text and ensure the RSS feed renders HTML content and links reliably.

  </div>
</div>

I thought it was hilarious that Claude had made a typo in the description and indeed it had. That was simple enough. The CDATA escaping of HTML in the descriptions was a notable miss for Claude, and frankly even for o-3 to miss in the features. Nice catch!

I sequently asked it to fix each of these issues and it issued a pull request for each one.

- [Fix description typo](https://github.com/jthingelstad/POAP2RSS/pull/3)
- [Use CDATA for HTML descriptions in RSS items](https://github.com/jthingelstad/POAP2RSS/pull/2)
- [Fix claimant link to use owner address](https://github.com/jthingelstad/POAP2RSS/pull/1)

I reviewed and merged each of these pull requests. 

Very cool! 🔥 I now have a fully working service and a reasonably clear code base. I wasn't entirely happy though with the HTML that was being put into the RSS feed descriptions. This is where I hit some "fit and finish" work that I ultimately did not find vibe coding a good approach for. I started to ask Codex "Please reformat the descriptions for events to look like…" and realized it was more work for me to ask Codex than to just go into the code and cleanup the strings myself. 

I did some actual coding here. 🛠️ It was fun to tweak and make it just what I wanted. I found a number of things that needed to be cleaned up:

- The descriptions of all events needed to be cleaned up.
- The RSS item GUIDs that Claude had used were not URL's as they should be so I fixed all of those.
- A number of the links were not right so I cleaned them up.

I now have a fully working service and it is even sending information as I would want it!

### Build the website!

Early in the project I had Claude create an `index.html` that I could drop into the `www` directory to have a simple website. It was okay but not at all the design I wanted. So, the next day I decided that this was a perfect ask for Codex so I asked it to build me a website. 

<div class="chat">
  <div class="author right">Me</div>
  <div class="message right">
The www directory contains the website for POAP2RSS. For this request work only inside that directory.

I would like to create a new website for POAP2RSS. The website should have the following pages which should all be included in the primary navigation of the website.

- index.html: the landing page for the project
- about.html: information about the project, why it exists, who created it
- changelog.html: to share changes about the project

Additionally there should be.

- dormant.html: the page POAP2RSS feeds direct users to when there is no activity in the feed and they should consider unsubscribing from the feed

All pages of the site should include references to Plausible for analytics. The tag is:

`<script defer data-domain="poap2rss.com" src="https://plausible.io/js/script.js"></script>`

For design and user experience:

- I would like to use the Pico CSS framework found at `https://picocss.com`
- I would like you to lean on the colors and feel of the POAP website at `https://poap.xyz`
- A simple and clean look is right for a project that has those same principles.

You will find two HTML pages already in the www directory. The documentation in those files is good but they can be replaced with the new website. 
  </div>
  <div class="author left">Codex</div>
  <div class="message left">

**Summary**

- Replaced the landing page with a Pico CSS design and added site navigation linking the new pages
- Provided project background and goals on a dedicated About page
- Created a simple Changelog outlining initial release updates
- Updated the dormant feed notice to use the same layout and encourage unsubscribing

  </div>
</div>

Wonderful! I merged in the [Redesign POAP2RSS website](https://github.com/jthingelstad/POAP2RSS/pull/6) and it was great.

I found myself in another "fit and finish" situation where it was much easier for me to just edit the HTML to what I wanted rather than asking Codex to do it for me. So I tweaked away and in not much time had a site up and running on [www.poap2rss.com](https://www.poap2rss.com) that made me happy!

### Good Vibes!

I've been playing with this service now a bit over the holiday weekend. It is working great. I've already used it to do a ton of automation for the [612 POAP Challenge](https://612.poapchallenge.com). I've added subscriptions to several people that collect POAPs which is super fun. 

The experience of Vibe Coding this was incredible. It took something that was beyond my capabilities and made it accessible. I shared the project with someone that knows and they said the code looked like it would have taken "2 days" to create the source. I got this done much faster, and did a lot more than just the code. 

It also highlighted for me how this approach isn't just about the code. I used AI to help create the stories as well as create the documentation and website. Those were huge helps.

I’m tracking [open issues](https://github.com/jthingelstad/POAP2RSS/issues) so I have some items that I'll likely use to test Cursor or do further work with Codex.

Overall, this was a very rewarding project to create and I learned a lot from making it a reality.

PS: Thank you to [Matt](https://mattlangford.com) for the slick message styling CSS for [Tiny Theme](https://tiny.micro.blog)!
