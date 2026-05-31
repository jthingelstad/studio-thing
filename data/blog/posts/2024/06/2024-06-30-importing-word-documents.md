---
microblog_id: 4180550
url: "https://www.thingelstad.com/2024/06/30/importing-word-documents.html"
title: "Importing 240 Word Documents to Micro.blog"
published: "2024-07-01T02:29:44+00:00"
post_kind: post
categories: []
---

This weekend I helped get my cousin Josh setup [Rambling Josh](https://www.ramblingjosh.com?ref=thingelstad.com), a [new website](https://www.thingelstad.com/2024/06/30/rambling-josh.html) to host the column he's been writing for 20 years. He knew I used micro.blog and was game to use that. I suggested he get a domain name at NameCheap which he did. I got in and twiddled some settings and I had the site up and running easy enough.

The challenge here was going to be the content. He had shared some documents with me earlier and it seemed like he wrote each column in Microsoft Word. They were very minimal on formatting (like almost none) since the target is a printed newspaper. In the end he had 240 Word documents, each representing an article, that we needed to get into Markdown and posted to the Micro.blog API.

I figured there were two steps:

1. Convert these files to Markdown
2. Post the Markdown to Micro.blog

### Converting to Markdown

I've used [Pandoc](https://pandoc.org) for this kind of thing before so knew it should handle this pretty easily. I tried with one file passing the source DOCX file and it did good with the MD file. However, it was word wrapped at 72 characters. I did a similar use of Pandoc when I imported content into my website at one time and didn’t realize the word wrapping was happening and now I have hundreds of posts that are word wrapped at 72 characters. In reality, nobody but me ever will see the Markdown so it has no impact. But it still bugs me. I found `--wrap=none` and was happy with the output.

A quick bash loop did the rest:

```bash
#!/bin/bash

for FILE in docx/*.docx; do

  # Extract the filename without the extension
  filename=$(basename -- "$FILE")
  filename="${filename%.*}"

  echo "Processing $filename...";

  pandoc -s "$FILE" \
    -t markdown \
    -o "md/$filename.md" \
    --wrap=none

done
```

### Posting to Micro.blog

So now I had a new directory with 240 Markdown files. First step done. Luckily Josh used a standard approach to each document. The files had names like:

```
The Wall 3-20-2019.md
Coach2-2-11.md
Boxed Out 1-18-2017.md
Fantasia 11-15-2017.md
Brooklyn Bound 10-16-2019.md
Memories 6-17-2020.md
Genius 4-19-17.md
Mirror Mirror 4-18-2018.md
Floored 3-6-2019.md
Good Man7-19-2017.md
```

So I had a fairly good way to get a title as well as a publish date from the filename.

Inside of each file he had the title, byline, and date as well at the top of each article. These had less conformity so I decided to ignore those and just use the filename for metadata.

As I put each article into Micro.blog I wanted to:

1. Make sure the title was set right.
2. Make sure the publish date was the original publish date, not now.
3. Add a static category. 

I started to whack away at this script and then decided to ask my friend [ChatGPT](https://chatgpt.com) 4o to give me a hand. I could have written what it helped me with, but it did it about 10x faster. It also had an easier time frankly handling the fact that not all the years had 4 digits. 🤓

```bash
#!/bin/bash

# Your Micro.blog token and API endpoint
MICRO_BLOG_TOKEN="SECRET TOKEN HERE"
API_ENDPOINT="https://micro.blog/micropub"

# Directory containing the markdown files
MARKDOWN_DIR="md"

# Function to post a markdown file
post_to_microblog() {
    local file="$1"
    local filename=$(basename -- "$file")

    # Extract the title (all characters before the date)
    local title="${filename%%[0-9]*}"

    # Extract the date part (all characters from the first digit to the last dot)
    local date_part=$(echo "$filename" | grep -oE '[0-9]{1,2}-[0-9]{1,2}-[0-9]{2,4}')
    local month=$(echo "$date_part" | cut -d'-' -f1)
    local day=$(echo "$date_part" | cut -d'-' -f2)
    local year=$(echo "$date_part" | cut -d'-' -f3)

    # Format the year to 4 digits (assuming 20xx)
    if [ ${#year} -eq 2 ]; then
        local year_formatted="20$year"
    else
        local year_formatted="$year"
    fi

    # Format the date to Y-M-D
    local timestamp_formatted="$year_formatted-$month-$day"

    # Set the time to midnight Central Time (CT)
    local timestamp_ct="${timestamp_formatted}T12:00:00-06:00"

    # Read file content and remove the first three paragraphs
    local content=$(awk 'BEGIN{RS="";ORS="\n\n"} NR>3' "$file")

    # Post to Micro.blog
    curl -X POST "$API_ENDPOINT" \
        -H "Authorization: Bearer $MICRO_BLOG_TOKEN" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "h=entry" \
        -d "name=$title" \
        -d "published=$timestamp_ct" \
        -d "category[]=Ramblings" \
        -d "content=$content"
}

# Iterate over markdown files in the directory
for file in "$MARKDOWN_DIR"/*.md; do
    if [[ -f "$file" ]]; then
    	echo "Processing $file..."
        post_to_microblog "$file"
        echo "\n"
    fi
done
```

I was impressed that ChatGPT had no issue knowing the signatures for the micro.blog API. It isn't a super common API but it didn’t miss a beat. The regular expression on the filename was the same approach I would have used. I always forget about `cut` but it was a smart use to pull apart the date. The part I would have struggled with was ignoring the first three paragraphs (not necessarily lines) in the file itself. These had the title, byline, and date. I just wanted to ignore it. I know a little `awk` but not enough to have it do that for me. 

I ran this and voila I had 240 blog posts from all those Markdown files. I was honestly surprised it didn’t take me longer. ChatGPT probably saved me a couple of hours of banging around at different approaches. 

There were a couple of bugs. 
- Articles that contained an ampersand caused problems with `curl`. The content after the first ampersand was lost. There were only eight or so articles that had that (thanks `grep`) so I remedied that by hand.
- I didn’t like what Pandoc did with superscript. Because Josh had written these in Word every occurence of 7th or 20th had superscript. There were a number of \^ that needed to get erased. I used [MarsEdit](https://redsweater.com/marsedit/) to both find the posts that had that, and do a quick find and replace with nothing. I wish that was a batch operation in MarsEdit but you have to do it one-by-one, but it is fast.
- Pandoc also littered a bunch of backslash characters attempting to do some formatting. I had to fix those by hand too.

It is entirely possible if I spent more time with the Pandoc testing I could have avoided the last two. Pandoc doesn't have command line flags for those but it does have multiple Markdown targets and some of them may have made more suitable Markdown for me. Either way it only took about 10 minutes to clean up thanks to MarsEdit.

### Wrapping up

I was pretty happy that I go this all going and even completed in just a couple of hours. The rest of the archive will be less easy to get, but with this we got a great start!
