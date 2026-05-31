---
microblog_id: 1074914
url: "https://www.thingelstad.com/2013/07/09/stopping-mediawiki-spam.html"
title: "Stopping MediaWiki Spam with Dynamic Questy Captchas"
published: "2013-07-09T05:00:00+00:00"
post_kind: post
categories: []
---

**This method of using Questy Captcha has been defeated by some
spammers. Please check out my [updated dynamic Questy Captcha
method](https://www.thingelstad.com/2014/updated-dynamic-questy-captchas/).**
[MediaWiki](http://www.mediawiki.org/) websites are often plagued by
spammers. It's annoying in the extreme. If you setup a blank MediaWiki
website and do nothing it is likely that within a couple of weeks your
site will be found, and in a matter of days you will have thousands of
spam user accounts and tens of thousands of pages of spam. There are a
number of ways to stop wikispam. I tried using
[Recaptcha](http://recaptcha.com) to little benefit. I still got a large
number of spam registrations on my publicly available wikis. I've found
the combination below to be incredible efficient.

I started to use
[QuestyCaptcha](http://www.mediawiki.org/wiki/Extension:QuestyCaptcha)
which is a plugin for the
[ConfirmEdit](http://www.mediawiki.org/wiki/Extension:ConfirmEdit)
extension
([WikiApiary](http://wikiapiary.com/wiki/Extension:ConfirmEdit)) which
uses a simple question/answer paradigm and that worked well. However,
the hard part with Questy is figuring out what questions to use.
Particularly if your wiki is global, you need to avoid using questions
that are specific to one culture or location, or even language. What
color is the sky? Well, in what language? For
[WikiApiary](http://wikiapiary.com/) I want to make sure that people
from anywhere are able to register. I started with simple questions,
like "What is the name of this website?" but that was quickly defeated
and spam registrations started showing up. What to do?

I decided to see if QuestyCaptcha could accommodate dynamic questions
and it can! So, the first thing I did was decide to use a question that
required someone to know something generic, but could also be easily
found with a single click on a URL. My choice was to ask about the GMT
time, because if you [search for "gmt time" on
Google](https://www.google.com/search?q=gmt+time), it tells you the
answer. The PHP function `gmdate` will also give the
answer. So I created two questions that asked for the day of the week
and the hour (24 hour time) at GMT, and provide hyperlinks to the
answer. This worked great!

Then I decided to go a little further and ask a very dynamic question.
This time I generated an 8 character random string, and ask the user to
identify one of the characters in the string. No language issue! No
culture challenges! Simple. Here is the code for both of these solutions
as it would appear in your `LocalSettings.php` file.

```php
# Let's stop MediaWiki registration spam
require_once( "$IP/extensions/ConfirmEdit/ConfirmEdit.php" );
require_once("$IP/extensions/ConfirmEdit/QuestyCaptcha.php");
$wgCaptchaClass = 'QuestyCaptcha';

# Set questions for Questy
# First a couple that can be answered with a linked to Google search
$wgCaptchaQuestions[] = array (
    'question' => "What day of the week is it at <a href="http://google.com/search?q=gmt+time">Greenwich Mean Time</a> (GMT) right now?",
    'answer' => gmdate("l")
);
$wgCaptchaQuestions[] = array (
    'question' => "In 24-hour format, what hour is it in <a href="http://google.com/search?q=gmt+time">Greenwich Mean Time</a> (GMT) right now?",
    'answer' => gmdate("G")
);

# Now a more complicated one
# Generate a random string 8 characters long
$myChallengeString = substr(md5(uniqid(mt_rand(), true)), 0, 8);
# Pick a random location in those 8 strings
$myChallengeIndex = rand(0, 7) + 1;
# Let's use words to describe the position, just to make it a bit more complicated
$myChallengePositions = array ('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth');
$myChallengePositionName = $myChallengePositions[$myChallengeIndex - 1];
# Build the question/anwer
$wgCaptchaQuestions[] = array (
    'question' => "Please provide the $myChallengePositionName character from the sequence <code>$myChallengeString</code>:",
    'answer' => $myChallengeString[$myChallengeIndex - 1]
);

# Skip CAPTCHA for people who have confirmed emails
$wgGroupPermissions['emailconfirmed']['skipcaptcha'] = true;
$ceAllowConfirmedEmail = true;
```

After putting these in place I've had nearly zero spam registrations (1
or 2 were clearly done by a human testing it). Now, can this be broken?
Sure, easily. But not nearly as easy as static questions that could be
harvested by a person and then put into a tool to automatically create
accounts. In order to attack me, spammers would have to write a special
handler that dealt with the randomness of the questions. This is very
unlikely.

Feel free to use these examples, or, use other dynamic question/answer
combinations. It's not obvious that this type of configuration works
with QuestyCaptcha, but it does and it allows for very powerful spam
blocking.
