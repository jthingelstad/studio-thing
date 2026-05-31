---
microblog_id: 1074723
url: "https://www.thingelstad.com/2017/12/01/aws-reinvent-keynote.html"
title: "AWS re:Invent 2017 Keynote Notes"
published: "2017-12-02T00:50:00+00:00"
post_kind: post
categories: []
---

My quick reaction to the notable announcements at AWS re:Invent 2017.

### Compute

- [Amazon Elastic Container Service for Kubernetes](https://aws.amazon.com/blogs/aws/amazon-elastic-container-service-for-kubernetes/) - Happy to see AWS supporting [Kubernetes](https://kubernetes.io) natively! This is a first step that should result in a better solution for customers that are trying to navigate through platform decisions.
- [AWS Fargate: Run Containers without Managing Infrastructure](https://aws.amazon.com/blogs/aws/aws-fargate/) - New offering from AWS that promises to deal with the backend of container orchestration.

### Databases

- [Amazon Aurora Serverless](https://aws.amazon.com/blogs/aws/in-the-works-amazon-aurora-serverless/) - What is a Serverless database? I'm not sure I know, but the idea of a database that has no cost other than storage when it's idle is pretty amazing for certain workloads. Sadly this is only available for MySQL at the moment, but they promise PostgreSQL coming soon.
- [S3 Select and Glacier Select: Retrieving Subsets of Objects](https://aws.amazon.com/blogs/aws/s3-glacier-select/) - Wow, this is pretty cool. Take a bunch of data and dump it into an S3 bucket and then execute SQL-like `select` commands against that data. This enables some very interesting capabilities.
- [Amazon Neptune: A Fully Managed Graph Database Service](https://aws.amazon.com/blogs/aws/amazon-neptune-a-fully-managed-graph-database-service/) - Graph databases are a bear to pick, use and run. AWS offering a cloud hosted graph database will hopefully address all of these issues. There are a large number of use cases where graph databases make a lot of sense but so many people have been burned by them that they tend to solve a graph problem using a document or relational database. It's cool to see that this supports RDF and SPARQL, core concepts of the [Semantic Web](https://www.w3.org/standards/semanticweb/). It also supports [TinkerPop3](https://tinkerpop.apache.org/) (really? can we get better names?).

### Machine Learning

- [Amazon SageMaker: Accelerating Machine Learning](https://aws.amazon.com/blogs/aws/sagemaker/) - Picking models for machine learning training is an often overlooked complexity with doing this right. This bundles that into one tool and should make it easier. We'll see.
- [Amazon Comprehend: Continuously Trained Natural Language Processing](https://aws.amazon.com/blogs/aws/amazon-comprehend-continuously-trained-natural-language-processing/) - I'm sure this has some great use cases around sentiment analysis but the surveillance capabilities creep me out.
- [Amazon Transcribe: Accurate Speech To Text At Scale](https://aws.amazon.com/blogs/aws/amazon-transcribe-scalable-and-accurate-automatic-speech-recognition/) - It just got significantly easier to add speech-to-text capabilities to various applications.

### Other

- [Announcing Alexa for Business: Using Amazon Alexa's Voice Enabled Devices for Workplaces](https://aws.amazon.com/blogs/aws/launch-announcing-alexa-for-business-using-amazon-alexas-voice-enabled-devices-for-workplaces/) - I actually bought an Echo for us to try and use in our operations area. Idea was to make some read-only data available via voice. It didn't go anywhere in large part because the security side was too complicated. Theoretically this would solve that, but I'm pretty bearish that this offering is something that many folks would care about.
