---
microblog_id: 1754499
url: "https://www.thingelstad.com/2022/12/13/find-unique-addresses.html"
title: "Find Unique Addresses for Multiple POAP Events"
published: "2022-12-14T03:18:41+00:00"
post_kind: post
categories: ["Crypto", "POAP"]
---

**How do you get a list of unique addresses that have claimed any set of POAPs?**

Each POAP event allows you to download a CSV file that has the addresses that claimed it, along with other data. Download all the CSV files into a directory. Now, assuming you are on Unix-like system, the rest is pretty easy.

First put all the CSVs together in one file. The download from POAP is missing a trailing newline, so loop in the shell.

```bash
for file in *.csv; do
for> cat $file >> combined.csv
for> echo "" >> combined.csv
for> done
```

Now lets spit the second column, the address, into another file. `awk` does this well.

`awk -F "\"*,\"*" '{print $2}' combined.csv > addresses.txt`

Now the classic `sort` and `uniq` combination will give us what we want.

`cat addresses.txt| sort | uniq > addresses-uniq.txt`

And you have your list!
