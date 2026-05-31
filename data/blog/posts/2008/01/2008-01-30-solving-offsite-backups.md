---
microblog_id: 1075941
url: "https://www.thingelstad.com/2008/01/30/solving-offsite-backups.html"
title: "Solving Offsite Backups"
published: "2008-01-30T06:00:00+00:00"
post_kind: post
categories: []
---

<img src="https://www.thingelstad.com/uploads/2020/51eb7b1ddf.jpg" style="width: 160px; float: right; margin-left: 10px; " />

Nobody likes to deal with backups. It's a chore. It usually has some expense to
it. But we all know it's critical. Your probably backing up to a USB
drive that you picked up and plugged into your machine. That's good.
Maybe you've actually progressed with another computer in your house or
a NAS device and are backing up over the network. This is a good idea to
provide some separation between the backup and the computer the data is
on.

But, what if there was a real catastrophe? What if your house burned
down? What if someone broke into your house and stole all the computers?
Bad things happen, and those hard drives no longer just have letters and
check book accounts. Those are your family photos and videos, and if
your like me you cannot lose that. There is only one way to guarantee
your data and that is offsite backup. I've finally implemented a robust
offsite backup regime that I think works best.

The first thing about doing offsite backups is that it requires pairs of
storage. You could get by without it, but that will double your trips
offsite to insure that you always have storage offsite. My approach is
to have an A-set and B-set of disks, and swap them via a safe deposit
box at the bank. If the A-set is at your house or in transit, the B-set
is in the bank. If the B-set is in motion, the A-set is in the bank.
There is always a safe set.

Now what kind of disk do we go with? There are a lot of options for USB
and FireWire drives that will do the job, but there are some challenges
with that approach. First, these drives have custom power adapters that
are unique to the drive. They also have a lot of air in those cases,
greatly increasing the phyiscal space required to store the disks. This
is important if you are placing them in a safety deposit box with
limited space. The answer is to just use bare hard drives, just like you
would put inside your machine.

<p class="alert">IMAGE OF DISKS</p>

But it's crazy to open up your machine all the time. That is where a USB
drive adapter comes to the rescue.

<p class="alert">IMAGE OF ADAPTER</p>
