Create a mailing
================

Mailing type
------------
Cloud Mailing is capable to mange two types of mailing:
 * **Regular mailing**: simple mailing which will end as soon as its recipients list is empty, or its end date is
   reached, whatever occurs in first.
 * **Opened mailing**: for this type of mailing, only the end date (if set) will close the mailing.

In fact, the real (and only) difference between 2 types is the mailing automatic ending.

Regular mailing
^^^^^^^^^^^^^^^
The *regular* type is for mailings for which the number of recipients is known (or nearly) from start.
This is the *default* type.

The simplest workflow is:
- create mailing
 - add recipients
 - start mailing
 - wait for the automatic end when all recipients have been handled

While this is very simple, it can be too long before the first recipient is addressed when the number of recipients is
high. It is possible to start the mailing before adding all recipients, then adding them after, but there is a big risk
that the recipients queue become empty before the end (because you didn't added recipients fast enough), and the mailing
closes itself too early.

That why it is possible to set a mailing property (`dont_close_if_empty`) that explicitly tells Cloud Mailing to not close this mailing because
we are still filling its recipients queue. So the workflow become:

 - create mailing
 - set `dont_close_if_empty` property to `True`
 - start mailing
 - add recipients
 - set `dont_close_if_empty` property to `False`
 - wait for the automatic end when all recipients have been handled

Opened mailing
^^^^^^^^^^^^^^
The *opened* type is for *permanent* mailings. They are mailing that are always active, and recipients can be added at
any time and handled immediately.

An example of opened mailing usage can be the confirmation email of an online store when a customer completes a
purchase. The email is always the same, only content (purchased items) change and is handled by advanced customization.
