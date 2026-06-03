---
microblog_id: 1074926
url: "https://www.thingelstad.com/2012/12/02/adding-email-mention.html"
title: "Adding Email Mention Notification to WordPress P2"
published: "2012-12-02T06:00:00+00:00"
post_kind: post
categories: ["Minnestar"]
---

I'm using the P2 theme on a couple of websites, one of them is for the [team minnestar](http://team.minnestar.org/) to help coordination and collaboration. P2 supports the ability to use a [@user](https://micro.blog/user) notation to mention other users on the site, but it doesn't do anything other than highlight the user. This snippet of PHP added to the bottom of the P2 functions.php will send email notifications on those mentions. This isn't heavily tested but it works well for me.

```php
/**
 * Custom code added to P2 to enable email notifications
 * when a user is @mentioned in the site.
 *
 * Original at [trepmal.com/2011/06/2...](http://trepmal.com/2011/06/24/using-wordpress-multisite-p2-and-more/)
 * and modified from there.
 */
add_action('publish_post','send_email_notification_once',9);
function send_email_notification_once($postID) {
    $post = get_post($postID);
    $author = get_userdata($post->post_author);
    global $p2;
    $mentions = $p2->components['mentions']->find_mentions($post->post_content);
    $permalink = get_permalink($postID);
    $blog_title = get_bloginfo('name');
    foreach ( $mentions as $match ) {
        $email = get_user_by('slug',$match)->user_email;
        $message = "You have been mentioned in this post:\n $permalink 

 {$post->post_content} ";
        wp_mail($email, "[$blog_title] You've been mentioned by {$author->display_name}", $message);
    }
}

add_action('comment_post','send_email_notification_once_comment',9);
function send_email_notification_once_comment($commentID){
    $comment = get_comment($commentID);
    global $p2;
    $mentions = $p2->components['mentions']->find_mentions($comment->comment_content);
    $permalink = get_permalink($comment->comment_post_ID);
    $blog_title = get_bloginfo('name');
    foreach ( $mentions as $match ) {
        $email = get_user_by('slug',$match)->user_email;
        $message = "You have been mentioned by {$comment->comment_author} in this comment:\n $permalink 

 {$comment->comment_content} ";
        wp_mail($email, "[$blog_title] You've been mentioned in a comment by {$comment->comment_author}", $message);
    }
}
```
