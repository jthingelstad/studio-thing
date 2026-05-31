---
microblog_id: 1084819
url: "https://www.thingelstad.com/2020/05/02/importing-jekyll-site.html"
title: "Importing Jekyll site to micro.blog"
published: "2020-05-02T13:43:07+00:00"
post_kind: post
categories: []
---

I successfully migrated my blog archive from [Jekyll](https://jekyllrb.com) to [micro.blog](https://micro.blog). I haven't seen much written about this, so let me share how I did it. This definitely requires a bit of hacking but the result worked very well. I followed the general pattern that [Manton Reece](https://www.manton.org) shared in his [Timetable migration to micro.blog](https://www.manton.org/2018/11/12/timetable-migrated-to.html) post.

You can grab the code and use it as a starting point. The script won't win any prizes for elegance, but it only needed to work once. Here is the [Python code](https://gist.github.com/jthingelstad/70ddb03da863f53c5ec622297c123db1) as well as the [Jekyll template for JSONFeed](https://gist.github.com/jthingelstad/e5ea874fcca7ff96b15fd84031211b81) that I used.

### Get Content Ready

Technically Jekyll is just a collection of Markdown files and image assets. it seems like it should be easy. However, Jekyll markdown files all have a variety of [Front Matter](https://jekyllrb.com/docs/front-matter/) metadata that is only meaningful to Jekyll. You almost certainly have [Liquid Tags](https://jekyllrb.com/docs/liquid/) in the content as well. So, let's make Jekyll do the work of helping us out of its issues.

I already had a [JSON Feed](https://jsonfeed.org) endpoint. I removed the post limit from it so it would generate a JSON Feed with all blog posts instead of just the most recent 10. I then told Jekyll to generate the site `jekyll build` and I was pretty much ready. I now had a full JSON Feed file with every blog post with no Liquid Tags either. 

I didn’t want to bring categories or tags over, but if you did you could easily add that to the JSON Feed export and catch it in the import.

### Content is in HTML

The JSON Feed file is great, but the content is in HTML and I need Markdown to give to micro.blog. [Pandoc](https://pandoc.org) and [pypandoc](https://pypi.org/project/pypandoc/) did an awesome job at this. I created a Python 3 script to open the JSON Feed file as a JSON object and then iterate through the posts. I used Pandoc to convert each `content_html` element into Markdown. Note I for sure would use Python 3 for the sensible handling of [UTF-8](https://en.wikipedia.org/wiki/UTF-8).

This one line of code just made me gleeful.

`md = pypandoc.convert_text(i['content_html'], 'md', format='html')`

### Images

Now that I had Markdown I was getting really close but I have thousands of linked images to import as well. I need to get the images uploaded to micro.blog, and then I need to update the URLs.

I created a regular expression (magic!) match to all image links that pointed to my own website. I could key this off a well defined path, `/assets/`. Since I was working out of a generated static site those images were all on the local file system so I parsed out the path from the URL, checked to make sure the file was found and uploaded it to micro.blog. I then used the generated URL returned from micro.blog to update the old one in the Markdown. Markdown made this a lot easier without all the HTML cruft. 

`urls = re.findall(r'(?:https://www.thingelstad.com)?(/assets/[\.\w\d\/\_\-]+)', md)`

Testing if the file exists was a good validator. I found a few issues with my regular expression and a couple of badly formatted blog posts that failed and was able to fix the formatting before importing. Also, since I only needed to run this once for some of the issues it was easier to fix the JSON Feed source instead of coding around it.

### Import!

With all posts successfully converting via Pandoc, and all images matching on the file system, I ran the script with a polite `sleep(2)` wait in the loop to make things easier for micro.blog servers and it all worked like a charm. Imported over 1,600 posts and 800MB of images.

I still have broken links internally. I don't think there would be any way for me to fix internal links between posts because everything is changing for those, but I'll use [Integrity](https://peacockmedia.software/mac/integrity/free.html) to scan for broken internal links and fix them manually.
