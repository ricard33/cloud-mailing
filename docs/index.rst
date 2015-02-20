.. Cloud Mailing documentation master file, created by
   sphinx-quickstart on Thu Feb 19 23:04:00 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Cloud Mailing's documentation!
=========================================

Cloud Mailing is an e-mailing engine designed for simplicity and performance thanks to its cloud (= *distributed*)
architecture.

Look how easy it is to use::

    import xmlrpclib

    config = {
        'ip': '192.168.1.150',
        'api_key': "xXXxxxXxxX",
    }

    cm_master = xmlrpclib.ServerProxy("https://admin:%(api_key)s@%(ip)s:33610/CloudMailing" % config)

    mailing_id = cm_master.create_mailing(
        "my-mailing@example.org",          # Sender email
        "My Mailing",                      # Sender name
        "The great newsletter",            # Subject
        "<h1>Title</h1><p>Coucou</p>",     # HTML content
        "Title\nCoucou\n",                 # Plain text content
        "UTF-8"                            # Text encoding (for both HTML and plain text content)
    )

    cm_master.set_mailing_properties(mailing_id, {
        'scheduled_start': datetime.now() + timedelta(hours=3),
        'scheduled_duration': 1440,  # in minutes
        'click_tracking': True,
    })

    cm_master.add_recipients(mailing_id, [
        {'email': 'john.doe@example.org', 'firstname': 'John', 'lastname': 'DOE', 'another_custom_field': 'blabla'},
        {'email': 'wilfred.smith@example.org'},
        [...]
    ])

    cm_master.start_mailing(mailing_id)

Table of content
----------------

.. toctree::
   :maxdepth: 3

   user/index
   dev/index

Features
--------

- Simple to use
- Scalable

Installation
------------

TODO

Contribute
----------

- Issue Tracker: github.com/ricard33/cloud-mailing/issues
- Source Code: github.com/ricard33/cloud-mailing
.. - Developer guide: :ref:`dev-guide`

Support
-------

.. If you are having issues, please let us know.
   We have a mailing list located at: project@google-groups.com

License
-------

The project is licensed under the GNU Affero General Public License v3.



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

