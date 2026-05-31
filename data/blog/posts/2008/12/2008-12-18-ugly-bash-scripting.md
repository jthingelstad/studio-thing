---
microblog_id: 1075744
url: "https://www.thingelstad.com/2008/12/18/ugly-bash-scripting.html"
title: "Ugly Bash Scripting"
published: "2008-12-18T06:00:00+00:00"
post_kind: post
categories: []
---

I started down this rabbit hole tonight trying to make a bash script do
more than I probably should make it do. But I didn't want to move to
something else. This may be some of the ugliest stuff I've ever written.

```bash
for file in $files; do
    if [ "$file" != "./00000000000001-tSQLVersions.sql" ]; then
        echo "Checking if $file is already loaded..."
        # oh this is ugly, oh so very very ugly
        # the tr on the end trims the newline out of the return from SQL
        check=`$MySQL -u$MyUSER -h$MyHOST -p$MyPASS $MyDB --execute="SELECT COUNT(*) FROM tSQLVersions WHERE message = '$file';" | tr -d '\n'`
        check=`echo -n "$check"`
    else
        # ridiculously ugly hack to hardcode updater to always assume this special file isn't loaded
        check="COUNT(*)0"
    fi

    if [ "$check" = "COUNT(*)0" ]; then
        echo "Loading $file..."
        $MySQL -u$MyUSER -h$MyHOST -p$MyPASS $MyDB < $file
        $MySQL -u$MyUSER -h$MyHOST -p$MyPASS $MyDB --execute="insert into tSQLVersions (message) values ('$file');"
    else
        echo "File $file has already been loaded!"
    fi
done
```

The `tr -d '\n'` at the end of line 6 is my personal
favorite. MySQL was dumping a newline in the STDOUT and screwing up my
comparison. Fix it right? Nah. Just rip that newline out of there. All
better!

I share this for others to know what not to do.

But hey, it works. :-) Who needs any fancy pants migrations.
