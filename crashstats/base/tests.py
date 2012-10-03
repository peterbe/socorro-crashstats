from nose.tools import eq_, ok_
from django.test import TestCase
from django.conf import settings
from django.test.client import RequestFactory

from crashstats.crashstats.models import BadStatusCodeError


class TestViews(TestCase):

    def test_500_template(self, rget):
        root_urlconf = __import__(settings.ROOT_URLCONF,
                                  globals(), locals(), ['urls'], -1)
        # ...so that we can access the 'handler500' defined in there
        par, end = root_urlconf.handler500.rsplit('.', 1)
        # ...which is an importable reference to the real handler500 function
        views = __import__(par, globals(), locals(), [end], -1)
        # ...and finally we the handler500 function at hand
        handler500 = getattr(views, end)
        # to make a mock call to the django view functions you need a request
        fake_request = RequestFactory().request(**{'wsgi.input': None})

        # the reason for first causing an exception to be raised is because
        # the handler500 function is only called by django when an exception
        # has been raised which means sys.exc_info() is something.
        try:
            raise NameError("sloppy code!")
        except NameError:
            # do this inside a frame that has a sys.exc_info()
            response = handler500(fake_request)
            eq_(response.status_code, 500)
            ok_('NameError' in response.content)

        # or equally with a BadStatusCodeError exception
        try:
            raise BadStatusCodeError('599: on http://middleware.com')
        except BadStatusCodeError:
            response = handler500(fake_request)
            eq_(response.status_code, 500)
            ok_('599: on http://middleware.com' in response.content)
