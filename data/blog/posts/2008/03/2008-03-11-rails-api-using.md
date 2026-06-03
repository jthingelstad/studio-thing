---
microblog_id: 1075917
url: "https://www.thingelstad.com/2008/03/11/rails-api-using.html"
title: "Rails API using Fluid SSB"
published: "2008-03-11T05:00:00+00:00"
post_kind: post
categories: []
---

I've been diving big into Ruby on Rails this week with this class I'm taking. One of the things I found right away is you need to have the Rails API documentation very handy. The main site is [api.rubyonrails.com](http://api.rubyonrails.com/), and frankly it's horrible. Luckily there is a great alternative at [RailsBrain](http://www.railsbrain.com/) that uses AJAX and all sorts of spiffy fun to make the API so much more usable. Today though I was getting frustrated because I had a slow internet connection and things were taking forever. Enter the solution, a [site-specific browser](https://www.thingelstad.com/2008/03/11/fluid-and-sitespecific.html).

My friend [Kent](http://www.thetangens.net/) came up with this idea, so credit to him for it, but I know he'll never blog about it and I want to share the love. RailsBrain allows you to download the API documentation as a zip file. It is simply a collection of files and can be served without a web server.

Unzip the files to a location of your liking and then launch fluid. Here is the setup window. For extra fun, I took the [logo image off of RailsBrain](http://www.railsbrain.com/rails_brain.png) to use as the application icon.

<img src="https://www.thingelstad.com/uploads/2020/ccd742aae0.png" alt="Fluid app dialog for creating a site-specific browser, with fields showing a local file URL, the name Rails API, Applications as the location, and rails_brain.png as the icon." style="max-width: 399px; " />

After doing this hit create and you've got a brand new shiny application that runs local, will work offline, is never going to be slow, and can be launched easily via your launcher of choice.

<img src="https://www.thingelstad.com/uploads/2020/233341260a.png" alt="Quicksilver launcher window showing Rails API.app selected, with a cartoon face icon wearing glasses, and the path /Applications/Rails API.app displayed below." style="max-width: 374px; " />

Plus, you can now alt-tab to it easily. Wow! Great idea Kent! This is really great, and it is blistering fast!
