---
microblog_id: 1074997
url: "https://www.thingelstad.com/2012/02/08/shutting-down-some.html"
title: "Shutting Down Some Websites"
published: "2012-02-08T06:00:00+00:00"
post_kind: post
categories: []
---

I recently decided to prune some websites that I was hosting, mostly ideas that I set up and then never took anywhere. Tammy had also decided to take her blog, Smaller Than a Redwood, down. I could have just deleted them but I wanted to be a good "net.citizen" and not give people "404 Page not found" errors but instead the more appropriate "410 Gone" message. Here is a simple way to do this with [nginx](http://nginx.org/).

First, I catch the websites main configuration which I keep in a file for each site in `/opt/etc/nginx/sites-available`. I try to keep these configurations really simple, just handling the URLs, ports and then doing the application configuration in an include.

```
# Redirect to non-www hostname
server {
  listen 80;
  listen [::]:80;
  server_name www.roadsignwordplay.com;
  rewrite ^ [roadsignwordplay.com](http://roadsignwordplay.com)$request_uri? permanent;
}

server {
  listen   80;
  listen   [::]:80;
  server_name roadsignwordplay.com;
  include /opt/etc/nginx/site-gone;
}
```

The include line then pulls in this configuration. I pointed this at a new directory in `/srv/www` so that any files that the site used to have could be left wherever they are. I also turn on an access log so I can easily see how many people are still going to the website. I still do a `try_files` because I have a robots.txt to help search engines know to go away. The important part is returning a 410 status and not a 404. The 410 is then handled by the `@site-gone` rule.

```
# this config is loaded into sites that are dead
root /srv/www/site-gone/public_html;
access_log /srv/www/site-gone/logs/$host-access.log;
error_log /srv/www/site-gone/logs/error.log ;

location / {
  try_files $uri =410;
}

error_page 410 @site-gone;
location @site-gone {
  rewrite ^(.*)$ /site-gone.html break;
}
```

Voila! Site is now "gone". I whipped up a simple HTML page to serve so people would know that the site was no longer available. And with that I wish Smaller Than a Redwood, Road Sign Wordplay, Road Sign Bingo, MediaWiki Cookbook, Sandbox Wiki and thinglesBot farewell!
