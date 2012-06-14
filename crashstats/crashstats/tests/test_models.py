import os
import shutil
import tempfile
import datetime
import mock
from django.core.cache import cache
from django.test import TestCase
from django.conf import settings
from crashstats.crashstats import models


class Response(object):
    def __init__(self, content=None, status_code=200):
        self.content = content
        self.status_code = status_code


class TestModels(TestCase):

    def setUp(self):
        super(TestModels, self).setUp()
        # thanks to settings_test.py
        assert settings.CACHE_MIDDLEWARE
        assert not settings.CACHE_MIDDLEWARE_FILES

    def tearDown(self):
        super(TestModels, self).tearDown()
        cache.clear()

    def test_bugzilla_api(self):
        model = models.BugzillaBugInfo

        api = model()

        with mock.patch('requests.get') as rget:
            def mocked_get(**options):
                assert options['url'].startswith(models.BugzillaAPI.base_url)
                return Response('{"bugs": [{"product": "mozilla.org"}]}')

            rget.side_effect = mocked_get
            info = api.get('747237', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'mozilla.org'}])

            # prove that it's cached by default
            def new_mocked_get(**options):
                return Response('{"bugs": [{"product": "DIFFERENT"}]}')

            rget.side_effect = new_mocked_get
            info = api.get('747237', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'mozilla.org'}])

            info = api.get('747238', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'DIFFERENT'}])

    def test_current_versions(self):
        model = models.CurrentVersions

        api = model()

        def mocked_get(**options):
            assert 'current/versions/' in options['url']
            return Response("""
                {"currentversions": [{
                  "product": "Camino",
                  "throttle": "100.00",
                  "end_date": "2012-05-10 00:00:00",
                  "start_date": "2012-03-08 00:00:00",
                  "featured": true,
                  "version": "2.1.3pre",
                  "release": "Beta",
                  "id": 922}]
                  }
              """)

        with mock.patch('requests.get') as rget:

            rget.side_effect = mocked_get
            info = api.get()
            self.assertTrue(isinstance(info, list))
            self.assertTrue(isinstance(info[0], dict))
            self.assertEqual(info[0]['product'], 'Camino')

    def test_adu_by_day(self):
        model = models.ADUByDay
        api = model()

        def mocked_get(**options):
            assert 'adu/byday' in options['url']
            return Response("""
               {"product": "Thunderbird",
                "start_date": "2012-05-29 00:00:00+00:00",
                "end_date": "2012-05-30 00:00:00+00:00",
                "versions": [{"statistics": [], "version": "12.0"}]
                }
              """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            yesterday = today - datetime.timedelta(days=1)
            r = api.get('Thunderbird', ['12.0'], ['Mac'], yesterday, today)
            self.assertEqual(r['product'], 'Thunderbird')
            self.assertTrue(r['versions'])

    def test_tcbs(self):
        model = models.TCBS
        api = model()

        def mocked_get(**options):
            assert 'crashes/signatures' in options['url']
            return Response("""
               {"crashes": [],
                "totalPercentage": 0,
                "start_date": "2012-05-10",
                "end_date": "2012-05-24",
                "totalNumberOfCrashes": 0}
              """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            r = api.get('Thunderbird', '12.0', 'plugin', today, 336)
            self.assertEqual(r['crashes'], [])

    def test_report_list(self):
        model = models.ReportList
        api = model()

        def mocked_get(**options):
            assert 'report/list/signature' in options['url']
            return Response("""
                {
          "hits": [
            {
              "product": "Fennec",
              "os_name": "Linux",
              "uuid": "5e30f10f-cd5d-4b13-9dbc-1d1e62120524",
              "many_others": "snipped out"
            }],
          "total": 333
          }
              """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            r = api.get('Pickle::ReadBytes', 'Fennec', today, 250)
            self.assertTrue(r['total'])
            self.assertTrue(r['hits'])

    def test_report_index(self):
        model = models.ReportIndex
        api = model()

        def mocked_get(**options):
            assert 'crash/processed' in options['url'], options['url']
            return Response("""
            {
              "product": "Firefox",
              "uuid": "7c44ade2-fdeb-4d6c-830a-07d302120525",
              "version": "13.0",
              "build": "20120501201020",
              "ReleaseChannel": "beta",
              "os_name": "Windows NT",
              "date_processed": "2012-05-25 11:35:57.446995",
              "success": true,
              "signature": "CLocalEndpointEnumerator::OnMediaNotific",
              "addons": [
                [
                  "testpilot@labs.mozilla.com",
                  "1.2.1"
                ],
                [
                  "{972ce4c6-7e08-4474-a285-3208198ce6fd}",
                  "13.0"
                ]
              ]
            }
            """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            r = api.get('7c44ade2-fdeb-4d6c-830a-07d302120525')
            self.assertTrue(r['product'])

    def test_search(self):
        model = models.Search
        api = model()

        def mocked_get(**options):
            assert 'search/signatures' in options['url'], options['url']
            return Response("""
            {"hits": [
                  {
                  "count": 586,
                  "signature": "nsASDOMWindowEnumerator::GetNext()",
                  "numcontent": 0,
                  "is_windows": 586,
                  "is_linux": 0,
                  "numplugin": 0,
                  "is_mac": 0,
                  "numhang": 0
                }],
              "total": 123
              }
            """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            yesterday = today - datetime.timedelta(days=10)
            r = api.get('Thunderbird', '12.0', 'Mac', yesterday, today)
            self.assertTrue(r['hits'])
            self.assertTrue(r['total'])

    def test_bugs(self):
        model = models.Bugs
        api = model()

        def mocked_post(**options):
            assert 'by/signatures' in options['url'], options['url']
            assert options['data'] == {'id': 'Pickle::ReadBytes'}
            return Response("""
               {"bug_associations": ["123456789"]}
            """)

        with mock.patch('requests.post') as rpost:
            rpost.side_effect = mocked_post
            r = api.get('Pickle::ReadBytes')
            self.assertTrue(r['bug_associations'])

    def test_signature_trend(self):
        model = models.SignatureTrend
        api = model()

        def mocked_get(**options):
            assert 'topcrash/sig/trend' in options['url'], options['url']
            return Response("""
            {
              "signature": "Pickle::ReadBytes",
              "start_date": "2012-04-19T08:00:00+00:00",
              "end_date": "2012-05-31T00:00:00+00:00",
              "signatureHistory": []
            }
            """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            r = api.get('Thunderbird', '12.0', 'Pickle::ReadBytes',
                        today, 1000)
            self.assertTrue(r['signature'])

    def test_signature_summary(self):
        model = models.SignatureSummary
        api = model()

        def mocked_get(**options):
            assert 'signaturesummary' in options['url'], options['url']
            return Response("""
            [
              {
                "version_string": "12.0",
                "percentage": "48.440",
                "report_count": 52311,
                "product_name": "Firefox"
              },
              {
                "version_string": "13.0b4",
                "percentage": "9.244",
                "report_count": 9983,
                "product_name": "Firefox"
              }
            ]
            """)

        with mock.patch('requests.get') as rget:
            rget.side_effect = mocked_get
            today = datetime.datetime.utcnow()
            yesterday = today - datetime.timedelta(days=10)
            r = api.get('products', 'Pickle::ReadBytes', yesterday, today)
            self.assertTrue(r[0]['version_string'])


class TestModelsWithFileCaching(TestCase):

    def setUp(self):
        super(TestModelsWithFileCaching, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        # Using CACHE_MIDDLEWARE_FILES is mainly for debugging but good to test
        self._cache_middleware = settings.CACHE_MIDDLEWARE
        self._cache_middleware_files = settings.CACHE_MIDDLEWARE_FILES
        settings.CACHE_MIDDLEWARE = True
        settings.CACHE_MIDDLEWARE_FILES = self.tempdir

    def tearDown(self):
        super(TestModelsWithFileCaching, self).tearDown()
        settings.CACHE_MIDDLEWARE = self._cache_middleware
        settings.CACHE_MIDDLEWARE_FILES = self._cache_middleware_files
        if os.path.isdir(self.tempdir):
            shutil.rmtree(self.tempdir)
        cache.clear()

    def test_bugzilla_api_to_file(self):
        model = models.BugzillaBugInfo

        api = model()

        with mock.patch('requests.get') as rget:
            def mocked_get(**options):
                assert options['url'].startswith(models.BugzillaAPI.base_url)
                return Response('{"bugs": [{"product": "mozilla.org"}]}')

            rget.side_effect = mocked_get
            info = api.get('747237', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'mozilla.org'}])

            # prove that it's cached by default
            def new_mocked_get(**options):
                return Response('{"bugs": [{"product": "DIFFERENT"}]}')

            rget.side_effect = new_mocked_get
            info = api.get('747237', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'mozilla.org'}])

            info = api.get('747238', 'product')
            self.assertEqual(info['bugs'], [{u'product': u'DIFFERENT'}])

    def test_caching_huge_url(self):
        """This has come about because we're sometimes fetching URLs like
        /buginfo/bug?bug_ids=736832,682573,751162,...really long and many...
        """

        model = models.BugzillaBugInfo
        api = model()

        with mock.patch('requests.get') as rget:
            def mocked_get(**options):
                assert options['url'].startswith(models.BugzillaAPI.base_url)
                return Response('{"bugs": [{"product": "mozilla.org"}]}')

            rget.side_effect = mocked_get
            ids = [str(700000 + c) for c in range(50)]
            # this is so huge as a file directory it would be hashed
            # and should work
            info = api.get(ids, 'product')
            self.assertEqual(info['bugs'], [{u'product': u'mozilla.org'}])
