---
microblog_id: 1226382
url: "https://www.thingelstad.com/2020/11/26/this-was-the.html"
title: ""
published: "2020-11-26T18:43:11+00:00"
post_kind: micropost
categories: []
---

This was the worst production outage I've experienced in Amazon Web Services, lasting **over 21 hours**. AWS has also published the [full incident report](https://aws.amazon.com/message/11201/). 

> **Latest Update (1:18 AM PST):** We have restored all traffic to Kinesis Data Streams via all endpoints and it is now operating normally. We have also resolved the error rates invoking CloudWatch APIs. We continue to work towards full recovery for IoT SiteWise and details of the service status is below. All other services are operating normally. <mark>We have identified the root cause of the Kinesis Data Streams event, and have completed immediate actions to prevent recurrence.</mark>
> 
> **Previous Update (12:43 PM PST):** We have restored all traffic to Kinesis Data Streams via all endpoints and it is now operating normally. We have also resolved the error rates invoking CloudWatch APIs. We continue to work towards full recovery for IoT SiteWise and Elastic Container Service; details of these services' status is below. All other services are operating normally. We have identified the root cause of the Kinesis Data Streams event, and have completed immediate actions to prevent recurrence.
> 
> **Previous Update (11:43 PM PST):** We have restored all traffic to Kinesis Data Streams via all endpoints, and have resolved the error rates invoking CloudWatch APIs. We are continuing to closely monitor Kinesis and work toward full recovery of all services. We have identified the root cause of the Kinesis Data Streams event, and have completed immediate actions to prevent recurrence. Kinesis and CloudWatch are operating normally.
> 
> **Previous Update (10:30 PM PST):** We have restored all traffic to Kinesis Data Streams from Internet-facing endpoints, and we are continuing to incrementally restore all requests to Kinesis Data Streams using VPC Endpoints. We are also beginning to observe incremental recovery of CloudWatch metrics functionality for new incoming metrics, and working towards full recovery. The backlog of metrics will take additional time to populate. 
> 
> **Previous Update (9:06 PM PST):** Over the past two hours, we have continued to bring more traffic in to Kinesis Data Streams, which is leading to gradual recovery of applications that use Kinesis directly, as well as dependent services within the US-EAST-1 Region. We are bringing traffic in more slowly than anticipated while we closely monitor each change to ensure continued stability. We expect that over the next few hours, we will complete restoring Kinesis Data Streams to normal operations.
> 
> CloudWatch metrics remain delayed in the US-EAST-1 Region. Once we have restored the throttles for Kinesis to previous levels, we will be restoring CloudWatch metrics functionality. We expect to see recovery of CloudWatch metrics at that stage for new incoming metrics, but the backlog of metrics may take additional time to populate.
> 
> **Previous Update (6:23 PM PST):** We’d like to provide an update on the issue affecting the Kinesis Data Streams API, and other dependent services, within the US-EAST-1 Region. We have now fully mitigated the impact to the subsystem within Kinesis that is responsible for the processing of incoming requests and are no longer seeing increased error rates or latencies. However, we are not yet taking the full traffic load and are working to relax request throttles on the service. Over the next few hours we expect to relax these throttles to previous levels. We expect customers to begin seeing recovery as these throttles are relaxed over this timeframe.
