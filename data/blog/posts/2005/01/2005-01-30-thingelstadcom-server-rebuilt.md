---
microblog_id: 1076373
url: "https://www.thingelstad.com/2005/01/30/thingelstadcom-server-rebuilt.html"
title: "thingelstad.com Server Rebuilt"
published: "2005-01-30T06:00:00+00:00"
post_kind: post
categories: []
---

My frequent visitors (all two of you! :-P) likely noticed that my site has been down since Saturday morning. I took some extra time this weekend to rebuild my [terabyte server](https://www.thingelstad.com/2004/04/02/project-terabyte.html). When I put the server up the first time I filled the RAID with 6 200G SATA drives and created one RAID5 set with 5 drives and left the last for a hot spare. I put a couple of logical partitions on it and left a spare 200G ATA drive in for generic downloads and other expendable items.

The problem with this is my entire system was on one drive and that led to performance problems and eventually would create maintenance challenges. For example, I couldn't unmount the big volume to do a chkdsk without causing all sorts of problems. So, I decided to redo it all and suffer the pain involved.

I added two more drives so I now have the Escalade 8506-8 card fully populated. My hot swap carrier only holds 7 drives so I put the 8th hard mounted in the case and designated it as the hot spare (figuring you usually don't have to change that since it's only used if your system is degraded). I did a more traditional RAID1 mirror on the first two drives and divided that into boot, app and data volumes. Then I just did one big export volume on the RAID5 set around 800G. Aside from the hours it took to re-initialize the RAID5 set it went smoothly.

I ran into one big problem though. It seems the ASUS PU-DL 1007 BIOS potentially has some problems booting off of the Escalade 8506-8 that only exhibit themselves when there are multiple volumes. The system would lock on boot and had to be hard reset. You could occasionally get it to boot by loaded the Windows rescue shell and accessing the disk then restarting, but not always. I updated the PU-DL BIOS to 1009 (current) which mentions some "zero config boot" issues and haven't had this problem since. (Knock on wood!)

I'm still cleaning up, need to deal with permissions and security stuff. But the end is clearly in view. Getting ready to put the server back in the laundry room. Man is this thing loud!
