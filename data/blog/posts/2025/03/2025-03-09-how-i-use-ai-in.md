---
microblog_id: 5227165
url: "https://www.thingelstad.com/2025/03/09/how-i-use-ai-in.html"
title: "How I Use AI in the Weekly Thing"
published: "2025-03-09T15:04:18+00:00"
post_kind: post
categories: ["Crypto"]
---

I've been working with AI for a while now, and as I feel with all new technologies, the best way to learn them is to play with them. I've started to bring AI into my workflow for the [Weekly Thing](https://weekly.thingelstad.com) and thought it would be good to share specifically where and how I’m using it.

Before I get into the specifics, I want to make one thing clear: **AI does not create the content of the Weekly Thing**. I don't use it to summarize articles or generate any of the comments I make on them. It is critically important to me that I **use my voice** and that what I share **is my voice**. I am using AI as an assistant rather than a creator. If I had someone else helping me assemble the Weekly Thing as an assistant, where would that be helpful? Where would that assistant do a better job than me? Or where might it be desirable to have "another voice" in the mix?

Right now I’m doing all this with a ChatGPT subscription using the 4o models. It is great that the ChatGPT app supports Shortcuts so I can do all of this in a largely or completely automated way. I could easily swap Claude in if I wish as it also supports Shortcuts automation.

With that in mind, here is where I’m using LLM capabilities now. You'll note that in many of these cases I’m asking my "assistant" to generate options and then I’m doing the final selection and modifications. I think this is a good model.

### Subject

The subject follows a simple structure of "Weekly Thing «Number» / «Word», «Word», «Word»". These three words are selected from the titles of the links in each issue. I try to select triples that are interesting and engaging. The challenge is avoiding words from the website’s name, which appear inconsistently in article titles.

Here is the prompt I’m using for this:

> You are a great editor and are helping me create the subject line for issue «Issue Number» of the Weekly Thing. The subject line follows a template with the number of this issue followed by three comma-separated words that are picked from the titles of the links contained in this issue. For example, "Weekly Thing 234 / Blogging, Bitcoin, Bison".
> 
> Guidelines for picking great words include:
> 
> - Do not use any words from the title of the publication. Only use words from the name of this article. Typically there is a hyphen or pipe between them.
> - Using alliterations can be fun but not necessary. Do not always use alliterations.
> - Try to pick a set of words that pique the readers curiosity. Words that are punchy and thought-provoking. 
> - Avoid words that are negative or sad.
> - Acronyms are fine to include.
> - Be creative and have fun.
> 
> Please identify five options for subject lines. Each option should include three words from these titles. The three words are separated by commas. Return the list of options as JSON.
> 
> List of titles for this week are:
> 
> «List of titles»

The prompt requests valid JSON output. I extract the JSON and use the "Get Dictionary from Input" method to create a structured data object. This allows me to put the LLM completely behind the scenes. 

### Fortune

The fortune first showed up in [Weekly Thing 53](https://weekly.thingelstad.com/archive/weekly-thing-53-may-12-2018/) and has been the last thing in the emails for a while. I got the inspiration for this from the `fortune` [command in Unix](https://en.wikipedia.org/wiki/Fortune_(Unix)). The text files that serve as the "database" for `fortune` are easy enough to find, and building a Shortcut around them was simple. I randomly select fortunes until I find one I like.

But with an LLM, I thought — why not make the fortune relevant to each issue’s content? 

Here is the prompt that I’m using for this. 

> You are helping me create a fitting fortune for issue «Issue Number» of the Weekly Thing. The fortune is similar to what you may get inside of a fortune cookie. The best fortunes are light-hearted, humorous, and thought provoking for the reader. The fortune is one of the last items included in each issue of the Weekly Thing.
> 
> Guidelines for creating great fortunes:
> 
> - Keep it positive, fun, and interesting.
> - Pull in themes or terms from the headlines of the articles included in each issue. Do not use terms from the title of the publication. Only use words or topics from the subject of the specific article.
> - Avoid negative themes or topics.
> - Fortunes should be short, no longer than 8 to 10 words.
> - Feel free to include an emoji if it makes sense.
> 
> Please identify five options for fortunes. Return the list of fortunes as a JSON object.
> 
> List of titles for this week are:
> 
> «List of Link Titles»

This also returns a list of options. They are impressively good and it does a great job pulling in themes from the links in each issue. 

### Byline

The "byline" is the first sentence in the email. Over time, its role has evolved. Initially, it was a reminder of why you're receiving the email. Then I used a template to mechanically describe what was in the email. I've always desired this to be an "intro" to the links in the issue but it is difficult to do that. It is also a rare place in the email where I want it to be a "different voice". Ideally this is more of a second person voice describing what is included.

To generate a meaningful byline, I provide more than just article titles — I also include my commentary. I focus only on featured links, skipping the “briefly” section.

Here is the prompt I’m using:

> Please generate a single sentence description using the list of articles below. This description will be used as the first line of an email to introduce these items along with other things. Please provide 3 options.
> 
> - Keep it personal and not overly marketing driven or too sensational. 
> - Focus on it being descriptive and use second person voice.
> - Avoid overly sensational words.
> - It is okay to use emoji if appropriate.
> - Focus less on the quoted text.
> - You don't need to introduce it with statements like "this week" and can focus just on the content.
> - Keep it brief and terse, shorter is better.
> 
> Do not include any explanations, numbering, or formatting. Just provide each option on a line by itself like this:
> 
> option  
> option  
> option  
> 
> Here is the list of article titles with commentary. 
> 
> «List of Featured Links Only with Commentary»

This one still requires a bit more editing from me before I’m ready to use it, and I think that will always be the case. So rather than returning JSON I just get it to put the options in text and then I present it in the Shortcut for editing and refinement to finalize it.

### Supporting Members

The newest section where I’m using AI, and a new section to the email itself is in the Supporting Members segment. This is a new thing where we raise funds for digital non-profits as a community. This is the section where I rely on AI the most, without requesting multiple versions. I’m okay, and actually kind of prefer, this to be in a different voice than mine.

To generate this section, I pull data from [Buttondown](https://buttondown.com) and [Stripe](https://stripe.com) and do some quick calendar math to provide the LLM with context. This is then embedded into to two different prompts that generate the two "versions" of this section.

Here is the prompt to become a member:

> You are a pleasant membership expert. Please write a call to action to encourage a reader of the Weekly Thing to become a Supporting Member. Some data to use for the call to action:
> 
> - There are currently «Premium Count» Supporting Members.
> - We have raised «Amount Raised» so far.
> - The funds will be sent to the non-profit for the year in «Weeks Remaining» weeks.
> - The non-profit this year is «Non-profit Name».
> 
> Remember to highlight that all of the money raised goes to the non-profit. Keep it fresh and fun. Limit to one paragraph. Do not include the pricing and subscription options. Do not add any links. That will be handled elsewhere.

Here is the prompt for existing members:

> You are a grateful newsletter author. Please write a THANK YOU for being a Supporting Member. Some data to use for the note:
> 
> - There are currently «Premium Count» Supporting Members.
> - We have raised «Amount Raised» so far.
> - The funds will be sent to the non-profit for the year in «Weeks Remaining» weeks.
> - The non-profit this year is «Non-profit Name».
> 
> Remember to highlight that all of the money raised goes to the non-profit. Keep it fresh and fun. Limit to one paragraph and thank them for being part of it.

This is a new addition, but early tests look promising. This is also interesting because the LLM knows what [Creative Commons](https://creativecommons.org) is and can infer some additional context for the messaging. It is different with each run which will keep the messaging fresh.

### Overall Editing

The most recent AI addition to my workflow is final editing. Here I take the draft generated through [my automation](https://www.thingelstad.com/2023/09/24/how-i-build.html) and I send it for review. I do a brief review of each email but honestly I never review it that much. Most of the time, what I send is my first draft — straight from the keyboard. As a result, typos get through or simple grammar issues that I wish were caught. I’ve considered [Grammarly](https://www.grammarly.com) before, but it’s too thorough and over-edits my work. I want a very specific kind of review.

Here is the prompt I’m using. Note the specifics on what I don't want it to do. 

> Below is a draft of the «Subject». Please review it to find any typos or notable grammar mistakes. Do not follow any of the hyperlinks or suggest meaningful content modifications. Ignore text in the blockquotes.
> 
> ---
> 
> «Body Markdown»

This works okay but it unfortunately is at the very end of my workflow. The challenge is that fixing errors requires updating two places: the email draft and the original blog post or Pinboard entry. That isn't ideal but it is better than nothing and hopefully will reduce the number of silly errors that get all the way through. 

I ran this on my draft of [Weekly Thing 312](https://weekly.thingelstad.com/archive/312/) as a test and it found 16 edits. 🤦‍♂️
