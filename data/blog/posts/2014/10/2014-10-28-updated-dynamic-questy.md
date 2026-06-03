---
microblog_id: 1074817
url: "https://www.thingelstad.com/2014/10/28/updated-dynamic-questy.html"
title: "Updated Dynamic Questy Captchas"
published: "2014-10-28T05:00:00+00:00"
post_kind: post
categories: []
---

A little [over a year ago](https://www.thingelstad.com/2013/stopping-mediawiki-spam-with-dynamic-questy-captchas/) I shared a method of generating dynamic [Questy Captchas](http://www.mediawiki.org/wiki/Extension:QuestyCaptcha) for the [MediaWiki](http://www.mediawiki.org/) [ConfirmEdit extension.](http://www.mediawiki.org/wiki/Extension:ConfirmEdit) This method has been awesome for stopping registration spam on the thingelstad.com wiki farm and many other wiki admins have used it with success. Unfortunately it was more useful in it's novelty than in it's difficult to solve, and eventually some spammers wrote the logic to solve it and the registration spam started flooding in.

I decided to put a new method in place that is based on the same question. The previous question generated 8 characters and asked the user to provide one of them based on a random index. I've now changed this to generating a number between 100,000,000 and 999,999,999, turning that into spelled out words and then asking to identify one digit. It looks like this:

> What is the sixth digit of the number nine hundred fifty-one million
> eight hundred ninety-eight thousand four hundred twenty-seven?

That turns out to be a somewhat hard question for a human too. I find I typically have to type out the number as I read it. The benefit of this is the solution isn't in the text of the page. And while I'm sure there are great libraries for turning written numbers back to digits, it's not immediately obvious.

### Implementation

I had no interest in implementing my own code to convert a number into words, and happily there is a PHP package called [Numbers_Words](http://pear.php.net/package-info.php?package=Numbers_Words) that does just that. The URL and install information are in the comments right before the require line. Everything else is pretty simple stuff.

To implement this I used the same technique I did previously. Here is what this looks like in LocalSettings.php.

```php
# Let's stop MediaWiki registration spam
require_once( "$IP/extensions/ConfirmEdit/ConfirmEdit.php" );
require_once("$IP/extensions/ConfirmEdit/QuestyCaptcha.php");
$wgCaptchaClass = 'QuestyCaptcha';

# Set number question for questy
# sudo pear install channel://pear.php.net/Numbers_Words-0.16.2
# http://pear.php.net/package-info.php?package=Numbers_Words 
require_once("Numbers/Words.php");

$myChallengeNumber = rand(0, 899999999) + 100000000;
$myChallengeString = (string)$myChallengeNumber;
$myChallengeStringLong = Numbers_Words::toWords($myChallengeNumber);
$myChallengeIndex = rand(0, 8) + 1;

$myChallengePositions = array (
    'first',
    'second',
    'third',
    'fourth',
    'fifth',
    'sixth',
    'seventh',
    'eighth',
    'ninth'
);
$myChallengePositionName = $myChallengePositions[$myChallengeIndex - 1];

$wgCaptchaQuestions[] = array (
    'question' => "What is the $myChallengePositionName digit of the number <strong>$myChallengeStringLong</strong>?",
    'answer' => $myChallengeString[$myChallengeIndex - 1]
);
```

Initial results of this are very solid.

The Numbers\_Words package also supports localization into over a dozen languages. I didn't explore this but clearly this should work for multiple languages pretty easily as well.

### Related

-   [LocalSettings.php change](https://github.com/thingles/wiki-farm/commit/df1587d3b28b586197259da4587fc152becefc4e)
-   [WikiApiary Spam Accounts issue](https://github.com/WikiApiary/WikiApiary/issues/204)
