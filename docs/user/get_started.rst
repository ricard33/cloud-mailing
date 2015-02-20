Get started with Cloud Mailing API
==================================

Overview
--------
The CloudMailing XML-RPC server allows to directly manage MailFountain CloudMailing Engine.

Authentication
--------------
You should be authenticated to be able to use it. Authentication is done by simple HTTP authentication method.
A special API key should be used as password (login is fixed to 'admin'). This key has to be generated from Web
administration pages.

Example of authentication::

    import xmlrpclib

    config = {
        'ip': '192.168.1.150',
        'api_key': "xXXxxxXxxX",
    }
    cm_master = xmlrpclib.ServerProxy("https://admin:%(api_key)s@%(ip)s:33610/CloudMailing" % config)


Create a mailing
----------------
To create a mailing, simply call the `create_mailing()` RPC function::

    mailing_id = cm_master.create_mailing(
        "my-mailing@%example.org",         # Sender email
        "My Mailing",                      # Sender name
        "The great newsletter",            # Subject
        "<h1>Title</h1><p>Coucou</p>",     # HTML content
        "Title\nCoucou\n",                 # Plain text content
        "UTF-8"                            # Text encoding (for both HTML and plain text content)
    )

This function returns you the mailing ID. This ID is unique and allows you to manage the mailing.

Then you should want to change/add more properties to your mailing. The function `set_mailing_properties()` is made
for this::

        cm_master.set_mailing_properties(mailing_id, {
            'scheduled_start': datetime.now() + timedelta(hours=3),
            'scheduled_duration': 1440,  # in minutes
            'click_tracking': True,
        })

Add some recipients
-------------------
To add recipients into your mailing, you should use the `add_recipients()` function::

    cm_master.add_recipients(mailing_id, [
        {'email': 'john.doe@example.org', 'firstname': 'John', 'lastname': 'DOE', 'another_custom_field': 'blabla'},
        {'email': 'wilfred.smith@example.org'},
        [...]
    ])

The function will return you an array with exactly the same number of entries, in the same order as input. Each entry is
also a dictionary containing 'email' field (the same as input), an 'id' which is unique for each recipient and,
only in case an error occurs, a field 'error' containing the failure reason in plain text.

'id' and 'error' are mutually exclusive. In case of success, only 'id' is present; in case of failure, only 'error' can
be found.

You can of course call this function as many time you want. There is no limit to the quantity of recipients a mailing
can handle. **But** be careful **to not send too many recipients at once** (i.e. in one single call) because depending
of the amount of customization data per recipient, you may reach the buffer limit of either the XMLRPC client or server.

Start a mailing
---------------
The start of a mailing is very simple::

        cm_master.start_mailing(mailing_id)

After this call, the mailing will be immediately eligible for adding its recipients to a sending queue, on condition
you didn't define a scheduled_start date in the future of course.

Retrieve recipients reports
---------------------------
Once the mailing started, you should want to retrieve sending status for each recipient. As it can have a hugh amount
of recipients, it won't be efficient to request continuously for each ones.

So Cloud Mailing API provides a more sophisticated function which will only return recipients for which the sending
status has changed since the last call. And for security, the maximum amount of results is limited.
 ::

    mailing_is_running = True
    cursor = ''
    status_filter = []  # No filter = all status except 'READY' (no sens to get them)
    while mailing_is_running:
        result = cm_master.get_recipients_status_updated_since(cursor, status_filter, 1000)
        cursor = result['cursor']
        recipients_status = result['recipients']
        # recipients_status is an array containing dictionaries
        [...]

To make it possible, the function returns you a private cursor object that you have to send it back on next call.

Retrieve mailing report
-----------------------
With mailing report, you will able to know how many recipients have been handled with success, are in error, will be
tried again and left to be handled. This will allow you to know (and its probably the most important) if your mailing
is finished or not (throw the mailing status)::

    filter = {'id': [mailing_id]}
    mailing = cm_master.list_mailings(filter)[0]
    while mailing['status'] != 'FINISHED':
        print("Total recipients: %d", mailing['total_recipient'])
        print("Recipients finished: %d", mailing['total_sent'])
        print("Recipients in error: %d", mailing['total_error'])
        [...]
        mailing = cm_master.list_mailings(filter)[0]

