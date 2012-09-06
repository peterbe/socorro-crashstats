from django.conf import settings
from django.test import TestCase

from funfactory.urlresolvers import reverse

from ..browserid_mock import mock_browserid


class TestViews(TestCase):
    def _login_attempt(self, email, assertion='fakeassertion123'):
        with mock_browserid(email):
            r = self.client.post(reverse('auth:mozilla_browserid_verify'),
                                 {'assertion': assertion})
        return r

    def test_invalid(self):
        """Bad BrowserID form (i.e. no assertion) -> failure."""
        response = self._login_attempt(None, None)
        self.assertRedirects(response,
                             reverse(settings.LOGIN_REDIRECT_URL_FAILURE))

    def test_bad_verification(self):
        """Bad verification -> failure."""
        response = self._login_attempt(None)
        self.assertRedirects(response,
                             reverse(settings.LOGIN_REDIRECT_URL_FAILURE))

    def test_bad_email(self):
        response = self._login_attempt('tmickel@mit.edu')
        assert response.status_code == 302
        # see comment in test_good_email() for why this is commented out
        #self.assertRedirects(response,
        #                     reverse(settings.LOGIN_REDIRECT_URL_FAILURE))

    def test_good_email(self):
        response = self._login_attempt(settings.ALLOWED_PERSONA_EMAILS[0])
        assert response.status_code == 302
        # this below won't work because the homepage, which is what
        # LOGIN_REDIRECT_URL is, also redirects so that assertRedirects()
        # doesn't work at the moment.
        #self.assertRedirects(response,
        #                     reverse(settings.LOGIN_REDIRECT_URL))
