---
microblog_id: 1075044
url: "https://www.thingelstad.com/2011/10/02/detect-slow-cacti.html"
title: "Detect Slow Cacti Polling"
published: "2011-10-02T05:00:00+00:00"
post_kind: post
categories: []
---

I'm a big fan of graphs, and as such am a big fan of
[Cacti](http://www.cacti.net/). I've used it at work and at home. It's a
wonderfully powerful, and ridiculously complicated front-end to
[RRDTool](http://oss.oetiker.ch/rrdtool/), which is also wonderfully
powerful and ridiculously complicated. I've used Cacti to graph hundreds
of servers, the temperature in my house, [heat collected from solar
panels](https://www.thingelstad.com/2006/06/13/solar-panels-started.html) and
[Twitter
followers](https://www.thingelstad.com/2009/03/30/tracking-twitter-followers.html).

By default Cacti runs a poller every 5 minutes to collect data. Cacti
gets very unhappy if the time required to run the poller exceeds the 5
minute interval. You will get blank data gaps and there aren't any
alarms that go off when this happens. Polling times can also vary
without any changes in Cacti. If you are polling an external service and
it gets slow, that could spike your polling times up in a terrible way.

I decided to write a quick script to catch this. Rather than integrate
it into Cacti's poller I made it completely separate. Save this script
to a shell script and add it to `/etc/cron.hourly`
and you can rest easily knowing your Cacti poller is healthy.

```bash
#!/bin/bash
#
# by Jamie Thingelstad

# Where is the log?
CACTI_LOG=/usr/local/cacti/log/cacti.log

# Sample up how many lines?
CACTI_SAMPLE=24

# Warning level for 5 minute poll interval, in seconds.
# Nonsensical to set this higher than 300.
WARN_AT=240

# Where is mail?
MAIL=/usr/bin/mail

# Where to send warning? What subject?
ERR_TO="bad-things-happening@youremail.com"
ERR_SUBJECT="[Cacti] Cacti Poller time is too high"

# Scan the cacti log and see how things are
# Grep for STATS \
# Get the last CACTI_SAMPLE samples \
# Find the duration field (cut) \
# Remove the label (cut) \
# Strip the decimal points, make it an integer (cut) \
# Add the total of all the samples and count the number of samples (awk) \
#   - this step is needed because the file may have < CACTI_SAMPLES in it
POLL_DATA=$(grep "SYSTEM STATS" $CACTI_LOG | \
            tail -$CACTI_SAMPLE | \
            cut -d " " -f 7 | \
            cut -d ":" -f 2 | \
            cut -d "." -f 1 | \
            awk '{ sum += $1; count++ } END { print sum, count }')

# Get the two variables we want
TOTAL_TIME=$(echo $POLL_DATA | awk '{print $1}')
TOTAL_COUNT=$(echo $POLL_DATA | awk '{print $2}')

# Figure out the allowed time as a multiple of WARN_AT
AVERAGE_TIME=$(($TOTAL_TIME / $TOTAL_COUNT))

# Check how long it took and warn if too long, in seconds
if [ "$AVERAGE_TIME" -gt "$WARN_AT" ]; then
    # Polling is exceeded limit, send warning
    ERR_MESSAGE="Polling time for cacti is dangerously high. Last $TOTAL_COUNT polling periods averaged $AVERAGE_TIME seconds, higher than $WARN_AT second threshold."
    echo $ERR_MESSAGE | $MAIL -s "$ERR_SUBJECT" "$ERR_TO" >/dev/null 2>/dev/null
fi
```

Some notes on what this script is doing:

-   Sampling 24 lines means 24 five-minute polling periods, in other
    words, the last 24 \* 5 minutes, or 2 hours.

-   The script will calculate the average of the last 24 (or fewer)
    samples and alarm if it is over threshold. One sample over the
    threshold won't matter since it uses the average.

-   The `awk` complexity is used to deal with a new
    log file that has fewer than `CACTI_SAMPLE`
    events.
