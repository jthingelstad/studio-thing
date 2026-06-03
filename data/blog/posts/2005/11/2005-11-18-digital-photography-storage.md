---
microblog_id: 1076244
url: "https://www.thingelstad.com/2005/11/18/digital-photography-storage.html"
title: "Digital Photography Storage Explosion"
published: "2005-11-18T06:00:00+00:00"
post_kind: post
categories: []
---

_This is also avaiable in [PDF format](https://files.thingelstad.com/posts/2005/digital-photography/DigitalPhotographyStorageExplosion.pdf)._  
_You can also download the [data used for analysis](https://files.thingelstad.com/posts/2005/digital-photography/Pics%20Analysis.xls.zip)._

### Abstract

Digital cameras have spread at an amazing rate. There are almost no film cameras being developed anymore, having been relegated to antique status. In fact, at the most recent photographer's expo, for the first time in the history of the event, no 35mm film cameras were introduced. Canon, Nikon and others are only focused in the digital realm. Even for high-end photography, digital has now become the "king of the hill".

While digital photography has huge benefits, it comes with a data management challenge that is an iceberg we are just now seeing the top of on the horizon. The average home computer user is ill-equipped to deal with these challenges, and even worse, most do not even realize the problem exists. This data problem ranges from photo organization, to storage and disaster recovery. These issues, particularly the last two, have the potential to be the Achilles heal of digital photography.

This document looks deeper into the trends regarding the storage requirements of digital photos, and some of the ancillary challenges that need to be addressed.

### The Problem

I got my very first digital camera, a Fuji MX-700, in June of 1999 and instantly fell in love with it. That camera awoke me to the wonders of digital photography. Instant gratification after taking the picture and the ability to easily share images over the Internet were just the beginning. I had for years owned the most popular film camera ever made, the Pentax K-1000. It collected dust for years, and I recently released it to a better owner through an eBay auction.

With its very small sensor and file sizes that camera couldn't compare to the quality of film. Many people scoffed at the idea that digital would be a real format for photography. The same fate fell on the first MP3 players. The failure in this logic is not accounting for the rapid pace that digital technology advances at. It was, and continues to be, only a matter of time before digital mediums eclipse their historical "analog" counterparts.

| Manufacturer | Model         | Sensor Size |
|--------------|---------------|-------------|
| Fuji Film    | MX-700        | 1.5 million |
| Fuji Film    | MX-2700       | 2.3         |
| Toshiba      | PDR-M70       | 3.37        |
| Canon        | PowerShot G2  | 4.0         |
| Canon        | PowerShot G3  | 4.0         |
| Canon        | Digital Rebel | 6.3         |
| Canon        | S500          | 5.0         |
| Canon        | EOS 20D       | 8.2         |

Every photo I've taken since that day in 1999 has been digital.

While much about this transition has been wonderful, and I certainly would not return to film, there are challenges. In the period from June 9, 1999 to October 27, 2005, a span of 2,332 days, I've taken over 20,000 pictures. That represents over 8 pictures a day for several years, a frequency that is unfathomable in film photography. This collection now represents nearly 50 gigabytes of storage that is more precious than any collection of spreadsheets or word processing documents I can imagine. Vacation memories, the birth of a child, weddings are just some examples of this immensely important data. Figure 1 shows the storage requirement of these photos over time.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure1.png" alt="Line chart showing cumulative digital photo storage growing from near 0 GB in June 1999 to about 46 GB by October 2005.">  
Figure 1

The explosion of storage required to accommodate increasing numbers of photos at higher resolutions is a genuine challenge. This data management problem was, until recently, inconceivable to the average person and was only an issue that organizations with specialized technical staff had to deal with. The idea of backing up 50 GB of data on anything other than a spare hard drive is preposterous; optical media is too small (including DVD) and tape is cost prohibitive, hard to use and prone to failure. Even the hard drive option has only recently become an option with the advent of USB2 and Firewire, before that there really was no option.

The amazing thing about this storage issue is the rate at which it is growing. It took 299 days for me to collect my first gigabyte of photos. I didn't reach the five gigabyte point until 1,144 days of photography. That is approximately half of the time I've had a digital camera. In the 1,188 days following that I've added another 41 gigabytes of photos, all while continuing to accelerate the storage needs. Figure 2 shows the storage size of photos taken by year (only showing years with complete data).

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure2.png" alt="Bar chart showing photo storage in GB per year from 2000 to 2004, rising sharply from about 1.5 GB in 2000 to nearly 20 GB in 2004.">  
Figure 2

This may sound huge, but luckily this technical problem has been helped by hard drive manufacturers. Figure 3 below compares the growth of my digital photos to Moore's Law<sup>[1](#footnote1)</sup> and Kryder's Law<sup>[2](#footnote2)</sup>. Both of these laws relate to the growth rates of technology. Moore's Law, reduced, states that computing power doubles every 18 months. Kryder's Law is a similar law for storage, but doubling even faster at 13 months.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure3.png" alt="Line chart showing personal photo storage growth in GB from 1999 to 2005 tracking faster than Moores Law but close to Kryders Law.">  
Figure 3 - Plotted on logarithmic scale.

It is interesting to note that both Moore's and Kryder's growth rates were well ahead of me for nearly the entire first year of photography. Since then, I've steadily outpaced Moore's and am knocking aggressively on the top-end of Kryder's growth rate.

The casual observer could stop reading here and think there is no problem. The growth of storage (theoretically at least) is growing at the same pace as digital photography. However, that isn't the entire story. If we make the assumption that the average person consumes technology at the average rate (dictated by Moore's Law) what we find is that on average, people have to buy more technology than they would have historically purchased to deal with storing all this data. In the past the default hard drive options at Dell.com would be fine, but as digital photography explodes the average user will be buying more sophisticated systems that come with a variety of technical challenges. This is a hidden, and mandatory cost and still doesn't resolve the issue of backing up this data.

### Digital Behavior

Digital photography introduces people to an entirely new way of using photos, with one of the biggest implication being how many pictures you actually take.

Take a moment to look at Figure 4 below showing the number of photos taken each month with a 6-month moving average.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure4.png" alt="Line chart showing monthly picture counts from Jun-99 to Sep-05, with a sharp spike near Jun-04 reaching about 1,600 and a rising average trend.">  
Figure 4

You can see a clear growth in the tendency to simply take more and more photos. I have been taking 36% more pictures every year since starting with digital photography. Compounding that problem is the growth of megapixels, and with it file-sizes, in digital cameras. The storage space required for the increasingly growing collection of photos is growing geometrically.

Figure 5 is interesting for other reasons as it identifies how events like vacation (July 2002, July 2004) affect these trends, as well as major life events like the birth of a child (June 2005). Going to Europe in July 2004 now carries with it a permanent issue of keeping 4.5 gigabytes of data around forever. That is notably more challenging than putting some prints in a photo album and placing it on the shelf. One is an active process of sophisticated data management, the other a passive matter of organizing physical documents. As we continue to use digital technology to capture events in our life we may begin to look at the digital cost of those events. Going on vacation will cost $2,000 and have a data load of 3GB, my childs school play will have a data load of 1.5GB, etc. All the while being additive of course, we are never removing old content.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure5.png" alt="Line chart showing monthly photo count and storage size in GB from June 1999 to late 2005, with sharp growth peaks around mid-2004 reaching nearly 4.5 GB.">  
Figure 5

Let's take a moment to look at our digital photography behavior. This is somewhat tangential to the issue at hand, but is interesting nonetheless and provides some depth to the trend of taking more photos over time. Figure 6 below shows the number of digital photos taken each month during the sample period.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure6.png" alt="3D bar chart showing photo counts per month from 1999 to 2005, with a dramatic spike in September 2003 near 1700 photos.">  
Figure 6

It is clear that the summer months represent big picture taking times. December also reflects a high volume of pictures, no doubt due to the Christmas holiday. Figures 7 and 8 show photographic activity by day and hour.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure7.png" alt="3D bar chart showing photo counts by day of week from 1999 to 2005, with Saturday 2005 reaching roughly 2,250 photos, the highest bar.">  
Figure 7

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure8.png" alt="3D bar chart showing photo counts by hour of day from 1999 to 2005, with peaks around 2 to 4 PM reaching nearly 800 photos.">  
Figure 8

The results are not terribly surprising. The majority of photos are taken on the weekends and there are very few photos taken while sleeping. It is a little surprising that the afternoon is higher than the early evening hours.

### Terabytes of Disney World

So clearly this is a growing mountain of data, and this is just one families archive of photos. The impact of this on a large scale, with hundreds of millions of photographers throughout the world is stunning. On a recent vacation to Disney World I was particularly taken with the pervasiveness of digital photography and digital video <sup>[3](#footnote3)</sup> equipment. I started to wonder what the storage requirement of the thousands of vacationers visiting Disney World everyday was.

I contacted Disney to find out how many visitors on average attend Disney World each day but they do not disclose that number.

> Date: Fri, 21 Oct 2005 09:16:30 -0700 To: Subject: Re: Request for
> General Information about Walt Disney World Resort From: Walt Disney
> World Guest Mail Reply-To: Walt Disney World Guest Mail
>
> Dear Jamie,
>
> Thank you for contacting the Walt Disney World Resort.
>
> We appreciate your interest in obtaining information about guest
> attendance. Regrettably, this type of specific information is
> proprietary and cannot be released. We are sorry that we cannot be of
> more assistance, and we appreciate your understanding.
>
> If you have questions or need further assistance, feel free to contact
> us.
>
> Sincerely,
>
> Ronda WDW Online Communications

Denied the true information, I did find some estimates of attendance on the web<sup>[4](#footnote4)</sup>. Using this estimate I concluded that Disney World averaged 38,462 visitors a day. According to at least one survey 54% of Americans are using digital cameras<sup>[5](#footnote5)</sup>. It seems straightforward to me that the average visitor to Disney World is also more likely to have a digital camera, but we'll use the average anyway.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/megapixels.png" alt="Line chart showing camera megapixel distribution peaking at 30 percent for 4-megapixel cameras, dropping to 5 percent at 1 and 7 megapixels.">

The next challenge is determining the distribution of camera types. I used a standard bell curve distribution from 2 megapixel to 8 megapixel (shown on the right), and also assumed that everyone is taking a JPEG file. The last bit of information needed is an estimate of how many pictures each one of these digitally equipped visitors would take at Disney World. I estimated 100 pictures, which I would suggest is high, but realistic given that you are on vacation, at a special place and have a high desire to capture "life's moments". For comparison, I took 241 pictures in two days at Disney World, averaging 120 pictures a day.

Given these assumptions, the attendees to Disney World generate 3,869 GB, or 3.78 **terabytes**, of data every single day. An equally interesting way to look at this is bandwidth. If you used the average cable modem available in the US today, and transmitted data at the maximum rate every minute that Disney World was open <sup>[6](#footnote6)</sup>, you would have to have 420 cable modems running in parallel (839 Mbps) to handle the data.

### Challenges

The challenges posed by dealing with such a large volume of data for both the individual, and the technology world as a whole, are significant. When you add to the equation that these are your memories, some of the most precious things you have, the criticality of the problem becomes clear.

Backing up data of this size is not easy. My solution thus far has been a plan of massive redundancy. I have four computers in my house that have large hard drives and every night an automated task runs to replicate any new images onto all of the backup points. This provides great redundancy and protection, however it's expensive using an additional 200 GB of storage for redundant copies, and growing every day. Realistically this solution will not be viable in a couple of years without further investment in high-end technology.

An additional problem with this is that it is all in one physical location so I'm not protected from catastrophic failure (e.g., fire burns down my house). It would be great to leverage a broadband connection to backup to a service provider over the Internet, however the pricing models for this make it unreasonable, costing hundreds of dollars a month. Alternatively, some technically sophisticated families can adopt a buddy system mirroring their photos between each other using backup programs with FTP options. This is a nice option, with relatively low costs but is hard to setup and issues like encryption must be addressed to insure privacy.

In the meantime, the best solution for offsite storage seems to be a removable USB or Firewire hard drive pair that you rotate to a safe deposit box. This is cumbersome and requires manual intervention which will only work for the most diligent of people.

We may think that the storage requirement problem is easily solved by Kryder's law and the hard drive manufacturers; there are further challenges that will make storage requirements grow even faster.

### The Raw Problem

Almost all digital photography is done straight to a JPEG file. This is an easy format that is usable on nearly every computer that exists, but may be a bad decision for pictures that you really care about. Most cameras support a file format called RAW which captures the photo in a different way, allowing you much more flexibility in the future. To keep it simple, a RAW file can be considered analogous to a negative <sup>[7](#footnote7)</sup>, with shooting to JPEG being similar to a Polaroid. You can then digitally develop that RAW file and improve the picture significantly. However, this comes at a cost - storage. It should be assumed that in the relatively near future camera manufacturers will migrate away from JPEG as consumers look for higher quality and more post-processing capability.

Raw files are compressed, but not as much as JPEG files. The resulting file is approximately 300% larger than a comparable JPEG file. Figure 9 shows the theoretical effect of using RAW photography as opposed to JPEG.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure9.png" alt="Line chart showing RAW photo storage growth from 1999 to 2005 outpacing Moore's Law and Kryder's Law projections, reaching near 100 GB.">
Figure 9 - Plotted on logarithmic scale.

You can see the problem right away! We break above Kryder's law immediately and stay well above it. At the end of our sample period our storage needs have tipled from 46 GB to 143 GB. Let's look at this growth on a linear scale in Figure 10, as opposed to the logarithmic scale in Figure 9. The huge disparity in storage needs versus growth are profound.

<img src="https://files.thingelstad.com/posts/2005/digital-photography/figure10.png" alt="Line chart showing RAW photo storage growth from 1999 to 2005 outpacing Moore's Law but tracking close to Kryder's Law, reaching about 80 GB total size.">
Figure 10

While it is appealing to do photography only in RAW, the storage implications make it very challenging.

### Other People's

Another interesting phenomenon in digital photography is the impact of other people pictures. I have a couple thousand pictures that others have taken that I keep in my collection. *Note, those pictures are excluded from all the analysis in this document.* These photos further increase my growth rates.

I call this trend "group photography". This is very typical with extended family outings or holidays. Several people with digital cameras will take pictures throughout the day and then one person will collect the photos from everyone. They will then synchronize the timestamps of the photos and distribute the entire collection of photos to everyone. This is a wonderful thing, but amplifies even further the massive storage issues related to digital photography. Now that trip to Disney World results in several hundred photos instead of the smaller hundred that you took by yourself.

### Conclusions

I believe that I am seeing the challenges of this problem sooner than the average person. I may take more pictures, and I've been doing digital photography for a long-time. However, it is clear that the industry needs to provide both software and services to help the average consumer with this problem, or run the risk of huge issues as people start losing more photos and precious memories and digital photography experiences a customer backlash. It is only a matter of time before large numbers of people start running out of hard drive space, or have a virus delete their entire summer vacation. Given the huge storage sizes it is unlikely that people will have backups around. After all, how many people can really honestly say they practice good data management processes even with small files?

I already know several people that print all their digital pictures for this very reason. They simply do not trust their computer, or their own skills at managing the data, and print everything for archival. This seems cumbersome to me, but I understand the comfort that having those photos in storage would provide. Far too many people have been clobbered by an Internet virus and lost data. They never want to lose their memories.

There is a rather simple suggestion to make this problem better and that is editing. Most people tend to keep every digital photo they ever take, never deleting anything. I do not like the idea of deleting photos unless they are plainly out-of-focus or otherwise bad. I suggest this problem should be solved by the technology that created it.

There are several things that companies like Canon and Nikon should be doing to assure this problem is managed. Digital camera makers should be pushing the burgeoning online backup service market to lower it's prices for large amounts of storage. There are hundreds of companies that will backup data for you to a managed service over a broadband connection. The problem is cost. These services still operate in terms of megabytes, not gigabytes. They all would charge several hundred dollars a month for this service.

Once solving the backup problem with cheap, reliable service provider model we need to address the software problem. There are no photo management programs that do well managing 20,000 photos. Programs like iPhoto and Picasa became unusable with very large photo collections. Additionally, the metadata that you attach to photos for indexing and searching needs to be self-contained in the photo files themselves, like the EXIF data that the camera embeds. The industry cannot try to lock people in to specific software packages by storing metadata in proprietary formats.

There are independent software developers working on the software problem, but it is not moving fast enough. The managed services market has held it's prices unreasonably high even while storage costs continue to decline. The is an opportunity for services like Flickr to provide options to help these problems, but informed customers will be hesitant to turn over such important data to a service like that.

In the meantime, the most cost-effective solution is to leverage a "buddy system" with others that have broadband connections. Swap hard drives and use software to backup encrypted copies of your digital photo collection to their network. As is too often the case though, this solution is only viable for the technically sophisticated user with their own infrastructure.

---

<a name="footnote1">1:</a> For more information on Moore's Law see Wikipedia at
<http://en.wikipedia.org/wiki/Moore%27s_Law>.
  
<a name="footnote2">2:</a> For more information
on Kryder's Law see Wikipedia at
<http://en.wikipedia.org/wiki/Kryder%27s_law>.

<a name="footnote3">3:</a> This document doesn't attempt to address the storage issues
related to digital video, however, it is worth noting that they are
orders of magnitude bigger than digital photography.

<a name="footnote4">4:</a> Article at <http://www.wdisneyw.co.uk/attend.html>.

<a name="footnote5">5:</a> Article at
<http://www.letsgodigital.org/en/news/articles/story_4267.html>.

<a name="footnote6">6:</a> Disney World Magic Kingdom is open from 9:00 am to 8:00 pm.

<a name="footnote7">7:</a> For more information on the RAW format see
<http://www.luminous-landscape.com/tutorials/understanding-series/u-raw-files.shtml>.
