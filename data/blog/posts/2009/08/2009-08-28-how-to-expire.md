---
microblog_id: 1075419
url: "https://www.thingelstad.com/2009/08/28/how-to-expire.html"
title: "How to Expire Tweets on Twitter"
published: "2009-08-28T05:00:00+00:00"
post_kind: post
categories: []
---

A lot of people consider [Twitter](http://twitter.com/) a [microblogging](http://en.wikipedia.org/wiki/Microblogging) platform. I don't really agree with that. I think [Tumblr](http://tumblr.com/) and [Posterous](http://posterous.com/) are great examples of microblogging platforms. Twitter, to me, is much more like a "micromessaging"platform. As such I think it has more in common with email and instant messenger than [WordPress](http://www.wordpress.org/) and Tumblr.

I've been thinking more recently about the digital trails we all leave and it struck me that Twitter really should be managed more like messaging applications. In those applications, I tend to have an expiration date for things. To be formal about it, there is a retention policy for that content. Twitter needs a retention policy. Do I really care to have archived forever the Tweet about lunch from three years ago? No. Does Google need to index it? No. The only practical use I can think of for a long history on Twitter is to be able to profile me for advertising better. No thanks.

I did a little looking and couldn't find anything to do this, so whipped up a Ruby program with the handy Twitter4R library to do what I want.

This script requires [Ruby](http://www.ruby-lang.org/en/), the [Twitter4R](http://twitter4r.rubyforge.org/) library and is intended to be ran on a schedule with a utility like cron. Edit the code to use your login credentials and set the days that you want to expire tweets after. This program will then repeatedly look at your timeline and **delete status messages that occur more than the number of days** you specify ago.

```ruby
#!/usr/bin/ruby
#
# Get requires out of the way
require('rubygems')
gem('twitter4r')
require('twitter')
require('time')

# Configuration parameters
twitter_username = "YOUR_USERNAME"
twitter_password = "YOUR_PASSWORD"
delete_after_days = 14

# Let's get a Twitter Client created
client = Twitter::Client.new(:login => twitter_username, :password => twitter_password)

# Expire deadline
expire_before = Time.now - (delete_after_days * 60 * 60 * 24)
expire_ids = []

puts "Expiring all Twitter updates prior to #{expire_before.to_s}."

# Iterate through timeline
# Purposefully get a large number of updates. As written, if your delete_after_time does not
# occur within the number of updates this script will never see an update that is old
# enough and never delete anything. It would be nice if we could request the timeline from
# the oldest tweet forward, but I cannot find a way to do that with Twitter4R. (The :since
# parameter does not seem to do anything for a :me request)
# If you have problems with this scripte set the count to something like the number
# of tweets you would create in delete_after_time days.
# Using the defaults, if you Tweet more than 200 times in 14 days this will never expire
# anything. If you try to use an expire length that is very long, like 365, this many not
# work at all.
timeline = client.timeline_for(:me, :count => 200) do |status|
  if status.created_at < expire_before
    puts "Queueing delete status ID #{status.id} created at #{status.created_at}  (#{status.text})."
    expire_ids.push(status.id)
  end
end

# Now we'll sort the array, this will have the affect of putting the oldest items first in
# the list to be deleted.
expire_ids.sort!

puts "Deleting #{expire_ids.length} tweets."

# Now let's delete the stuff
# The Twitter4R library delete method seems to be completely broken. So, rather than a simple
# client.status(:delete, delete_status) we are going to go right to the API methods on Twitter
# this is ugly, but we are just going to spawn curl to do this work for us. And I'm sure I
# could do this without execing curl in the shell, but, whatever...
# Note: the delete method is not rate limited.
expire_ids.each do |delete_status|
  puts "Deleting #{delete_status}..."
  `curl -s -u #{twitter_username}:#{twitter_password} --http-request DELETE [twitter.com/statuses/...](http://twitter.com/statuses/destroy/#){delete_status}.xml`
end
```

This script does not do **any** checks to make sure the delete commands succeeded. Consider yourself warned. I don't think it matters much since if it fails a delete it will just try again the next time.

Since the [delete method](http://apiwiki.twitter.com/Twitter-REST-API-Method%3A-statuses%C2%A0destroy) is not rate limited, you could run this whenever. However, I would suggest to run it at once a night, perhaps late in the evening, so that you don't interfere with the Twitter API usage from your normal Twitter clients.
