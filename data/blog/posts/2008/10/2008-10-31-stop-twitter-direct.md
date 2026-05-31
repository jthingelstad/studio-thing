---
microblog_id: 1075773
url: "https://www.thingelstad.com/2008/10/31/stop-twitter-direct.html"
title: "Stop Twitter Direct Messages"
published: "2008-10-31T05:00:00+00:00"
post_kind: post
categories: []
---

My relationship with [Twitter](http://twitter.com/) [ebbs](https://www.thingelstad.com/2007/11/04/buhbye-twitter.html) and [flows](https://www.thingelstad.com/2008/03/11/hello-again-twitter.html). Sometimes I find it very enjoyable, and at other times it seems like a worthless distraction. However, there is one part of Twitter that I have never liked, **direct messages**.

Why not like direct messages? I'm not a fan of anything that creates another queue that I have to monitor and respond to. I try to keep everything in one workflow, and that workflow is email. My annoyance isn't limited to Twitter direct messages, but extends equally to Facebook messages and any other website specific inbox. I think Facebook could actually do their members a huge service by making their message system IMAP-capable. It would make it infinitely more useful and you could happily sit in your choice of email clients. On the other hand I would rather just not deal with Twitter direct messages.

I'd thought for a while that part of a Twitter Pro premium service could be to turn off direct message function. I decided to take matters into my own hands and rid myself of direct messages now instead. You can use this little program to do the same for you.

The first thing to do is tell Twitter to stop notifying you of a direct message. Go to your account Settings and in the Notices tab uncheck the Direct Text emails option.

![direct-text-email-setting.png](https://www.thingelstad.com/uploads/2020/8f5b60a51a.png)

Now, this 28-line Ruby program will simply respond (via direct message) to any direct messages you have received and then delete the direct message from your account, leaving no queue behind. If you don't like the delete, you can just comment out line 24. To make life easy this uses the [Twitter4R library for Ruby](http://twitter4r.rubyforge.org/). You will have to edit lines 9 and 19 to your credentials and personal message.

```ruby
# Get requires out of the way
require('rubygems')
gem('twitter4r', '>=0.2.0')
require('twitter')
require('time')

# Let's get a Twitter Client created
# Put your credentials in here
client = Twitter::Client.new(:login => 'USERNAME', :password => 'PASSWORD')

# Get Direct Messages
messages = client.messages(:received)

# Loop through any direct messages received
messages.each do |message|
  # Reply to the message
  # Set the message text to what you want, make sure it is Twitter length compliant
  response = Twitter::Message.create(
    :text => 'PUT YOUR MESSAGE HERE. YOU PROBABLY WANT YOUR EMAIL IN HERE.',
    :recipient => message.sender,
    :client => client)

  # Delete the message
  client.message(:delete, message)

  # Put a brief pause here just to make Twitter happier
  sleep 5
end
```

There is no error checking and by default it outputs nothing. It is intended to be invoked via cron at whatever interval you would like. If you do not have the Twitter4R Gem installed just run `gem install twitter4r`.
