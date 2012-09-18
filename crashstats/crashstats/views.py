import json
import datetime
import functools
import math
from collections import defaultdict
from django import http
from django.shortcuts import render, redirect
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.syndication.views import Feed

from session_csrf import anonymous_csrf

from . import models
from . import forms
from . import utils
from .decorators import check_days_parameter


def plot_graph(start_date, end_date, crashes, currentversions):

    graph_data = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
    }

    count = 0

    for count, product_version in enumerate(sorted(crashes, reverse=True),
                                            start=1):
        graph_data['item%s' % count] = product_version.split(':')[1]
        graph_data['ratio%s' % count] = []
        for day in sorted(crashes[product_version]):
            ratio = crashes[product_version][day]['crash_hadu']
            t = utils.unixtime(day, millis=True)
            graph_data['ratio%s' % count].append([t, ratio])

    graph_data['count'] = count

    return graph_data


def set_base_data(view):

    def _basedata(product=None, versions=None):
        """
        from @product and @versions transfer to
        a dict. If there's any left-over, raise a 404 error
        """
        data = {}
        api = models.CurrentVersions()
        data['currentversions'] = api.get()
        if versions is None:
            versions = []
        else:
            versions = versions.split(';')

        for release in data['currentversions']:
            if product == release['product']:
                data['product'] = product
                if release['version'] in versions:
                    versions.remove(release['version'])
                    if 'versions' not in data:
                        data['versions'] = []
                    data['versions'].append(release['version'])

        if product is None:
            # thus a view that doesn't have a product in the URL
            # e.g. like /query
            if not data.get('product'):
                data['product'] = settings.DEFAULT_PRODUCT
        elif product != data.get('product'):
            raise http.Http404("Not a recognized product")

        if product and versions:
            raise http.Http404("Not a recognized version for that product")

        return data

    @functools.wraps(view)
    def inner(request, *args, **kwargs):
        product = kwargs.get('product', None)
        versions = kwargs.get('versions', None)
        for key, value in _basedata(product, versions).items():
            setattr(request, key, value)
        return view(request, *args, **kwargs)

    return inner


@set_base_data
@check_days_parameter([3, 7, 14], default=7)
def products(request, product, versions=None):
    days = request.days
    data = {}

    # FIXME hardcoded default, find a better place for this to live
    os_names = settings.OPERATING_SYSTEMS

    if versions is None:
        versions = []
        for release in request.currentversions:
            if release['product'] == request.product and release['featured']:
                versions.append(release['version'])
    else:
        versions = versions.split(';')

    data['versions'] = versions
    if len(versions) == 1:
        data['version'] = versions[0]

    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=days + 1)

    mware = models.Crashes()
    crashes = mware.get(product, versions, os_names,
                        start_date, end_date)
    data['graph_data'] = json.dumps(
        plot_graph(start_date, end_date, crashes['hits'],
                   request.currentversions)
    )
    data['report'] = 'products'
    data['days'] = days
    return render(request, 'crashstats/products.html', data)


@set_base_data
@anonymous_csrf
@check_days_parameter([1, 3, 7, 14, 28], default=7)
def topcrasher(request, product=None, versions=None,
               crash_type=None, os_name=None):
    data = {}

    if not versions:
        # :(
        # simulate what the nav.js does which is to take the latest version
        # for this product.
        for release in request.currentversions:
            if release['product'] == product and release['featured']:
                url = reverse('crashstats.topcrasher',
                              kwargs=dict(product=product,
                                          versions=release['version']))
                return redirect(url)
    else:
        versions = versions.split(';')

    if len(versions) == 1:
        data['version'] = versions[0]

    days = request.days
    end_date = datetime.datetime.utcnow()

    if crash_type not in ['all', 'browser', 'plugin', 'content']:
        crash_type = 'browser'

    data['crash_type'] = crash_type

    if os_name not in settings.OPERATING_SYSTEMS:
        os_name = None

    data['os_name'] = os_name

    api = models.TCBS()
    tcbs = api.get(
        product,
        data['version'],
        crash_type,
        end_date,
        duration=(days * 24),
        limit='300'
    )
    signatures = [c['signature'] for c in tcbs['crashes']]

    bugs = defaultdict(list)
    api = models.Bugs()
    for b in api.get(signatures)['bug_associations']:
        bugs[b['signature']].append(b['bug_id'])

    for crash in tcbs['crashes']:
        sig = crash['signature']
        if sig in bugs:
            if 'bugs' in crash:
                crash['bugs'].extend(bugs[sig])
            else:
                crash['bugs'] = bugs[sig]

    data['tcbs'] = tcbs
    data['report'] = 'topcrasher'
    data['days'] = days

    return render(request, 'crashstats/topcrasher.html', data)


@set_base_data
def daily(request, product=None, versions=None):
    data = {}

    if versions is None:
        versions = []
        for release in request.currentversions:
            if release['product'] == request.product and release['featured']:
                versions.append(release['version'])
    else:
        versions = versions.split(';')

    data['versions'] = versions
    if len(versions) == 1:
        data['version'] = versions[0]

    os_names = settings.OPERATING_SYSTEMS

    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=8)

    api = models.Crashes()
    crashes = api.get(product, versions, os_names, start_date, end_date)

    data['graph_data'] = json.dumps(
        plot_graph(start_date, end_date, crashes['hits'],
                   request.currentversions)
    )
    data['report'] = 'daily'

    return render(request, 'crashstats/daily.html', data)


@set_base_data
def builds(request, product=None, versions=None):
    data = {}

    # the model DailyBuilds only takes 1 version if possible.
    # however, the way our set_base_data decorator works we have to call it
    # versions (plural) even though we here don't support that
    if versions is not None:
        assert isinstance(versions, basestring)

        request.version = versions  # so it's available in the template

    data['report'] = 'builds'
    api = models.DailyBuilds()
    middleware_results = api.get(product, version=versions)
    builds = defaultdict(list)
    for build in middleware_results:
        if build['build_type'] != 'Nightly':
            continue
        key = '%s%s' % (build['date'], build['version'])
        build['date'] = datetime.datetime.strptime(
            build['date'],
            '%Y-%m-%d'
        )
        builds[key].append(build)

    # lastly convert it to a list of tuples
    all_builds = []
    # sort by the key but then ignore it...
    for __, individual_builds in sorted(builds.items(), reverse=True):
        # ...by using the first item to get the date and version
        first_build = individual_builds[0]
        all_builds.append((
            first_build['date'],
            first_build['version'],
            individual_builds
        ))

    data['all_builds'] = all_builds
    return render(request, 'crashstats/builds.html', data)


@set_base_data
@check_days_parameter([3, 7, 14, 28], 7)
def hangreport(request, product=None, versions=None, listsize=100):
    data = {}
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        return http.HttpResponseBadRequest('Invalid page')

    days = request.days
    end_date = datetime.datetime.utcnow().strftime('%Y-%m-%d')

    # FIXME refactor into common function
    if not versions:
        # simulate what the nav.js does which is to take the latest version
        # for this product.
        for release in request.currentversions:
            if release['product'] == product and release['featured']:
                url = reverse('crashstats.hangreport',
                              kwargs=dict(product=product,
                                          versions=release['version']))
                return redirect(url)
    else:
        versions = versions.split(';')[0]

    data['version'] = versions

    current_query = request.GET.copy()
    if 'page' in current_query:
        del current_query['page']
    data['current_url'] = '%s?%s' % (reverse('crashstats.hangreport',
                                     args=[product, versions]),
                                     current_query.urlencode())

    api = models.HangReport()
    data['hangreport'] = api.get(product, versions, end_date, days,
                                 listsize, page)

    data['hangreport']['total_pages'] = data['hangreport']['totalPages']
    data['hangreport']['total_count'] = data['hangreport']['totalCount']

    data['report'] = 'hangreport'
    if page > data['hangreport']['totalPages'] > 0:
        # naughty parameter, go to the last page
        if isinstance(versions, (list, tuple)):
            versions = ';'.join(versions)
        url = reverse('crashstats.hangreport',
                      args=[product, versions])
        url += ('?days=%s&page=%s'
                % (days, data['hangreport']['totalPages']))
        return redirect(url)

    data['current_page'] = page
    data['days'] = days
    return render(request, 'crashstats/hangreport.html', data)


@set_base_data
@check_days_parameter([3, 7, 14, 28], 7)
def topchangers(request, product=None, versions=None):
    data = {}

    days = request.days

    if not versions:
        # :(
        # simulate what the nav.js does which is to take the latest version
        # for this product.
        for release in request.currentversions:
            if release['product'] == product and release['featured']:
                url = reverse('crashstats.topchangers',
                              kwargs=dict(product=product,
                                          versions=release['version']))
                return redirect(url)
    else:
        versions = versions.split(';')

    data['days'] = days
    data['versions'] = versions
    if len(versions) == 1:
        data['version'] = versions[0]

    end_date = datetime.datetime.utcnow()

    # FIXME hardcoded crash_type
    crash_type = 'browser'

    changers = defaultdict(list)
    api = models.TCBS()
    for v in versions:
        tcbs = api.get(product, v, crash_type, end_date,
                       duration=days * 24, limit='300')

        for crash in tcbs['crashes']:
            if crash['changeInRank'] != 'new':
                change = int(crash['changeInRank'])
                if change <= 0:
                    continue
                changers[change].append(crash)

    data['topchangers'] = changers

    data['report'] = 'topchangers'
    return render(request, 'crashstats/topchangers.html', data)


@set_base_data
def report_index(request, crash_id):
    data = {}

    api = models.ProcessedCrash()
    data['report'] = api.get(crash_id)

    data['bug_product_map'] = settings.BUG_PRODUCT_MAP

    process_type = 'unknown'
    if data['report']['process_type'] is None:
        process_type = 'browser'
    elif data['report']['process_type'] == 'plugin':
        process_type = 'plugin'
    elif data['report']['process_type'] == 'content':
        process_type = 'content'
    data['process_type'] = process_type

    data['product'] = data['report']['product']
    data['version'] = data['report']['version']

    data['parsed_dump'] = utils.parse_dump(data['report']['dump'],
                                           settings.VCS_MAPPINGS)

    bugs_api = models.Bugs()
    data['bug_associations'] = bugs_api.get(
        [data['report']['signature']]
    )['bug_associations']

    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=14)

    comments_api = models.CommentsBySignature()
    data['comments'] = comments_api.get(data['report']['signature'],
                                        start_date, end_date)

    raw_api = models.RawCrash()
    data['raw'] = raw_api.get(crash_id)

    if 'HangID' in data['raw']:
        data['hang_id'] = data['raw']['HangID']

        crash_pair_api = models.CrashPairsByCrashId()
        data['crash_pairs'] = crash_pair_api.get(
            data['report']['uuid'],
            data['hang_id']
        )

    return render(request, 'crashstats/report_index.html', data)


@set_base_data
def report_list(request):
    data = {}

    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        return http.HttpResponseBadRequest('Invalid page')

    data['current_page'] = page

    signature = request.GET.get('signature')
    product_version = request.GET.get('version')
    if 'date' in request.GET:
        end_date = datetime.datetime.strptime(request.GET.get('date'),
                                              '%Y-%m-%d')
    else:
        end_date = datetime.datetime.utcnow()

    duration = int(request.GET.get('range_value'))
    data['current_day'] = duration

    start_date = end_date - datetime.timedelta(days=duration)
    data['start_date'] = start_date.strftime('%Y-%m-%d')
    data['end_date'] = end_date.strftime('%Y-%m-%d')

    results_per_page = 250
    result_offset = results_per_page * (page - 1)

    api = models.ReportList()
    data['report_list'] = api.get(signature, product_version,
                                  start_date, results_per_page,
                                  result_offset)

    current_query = request.GET.copy()
    if 'page' in current_query:
        del current_query['page']
    data['current_url'] = '%s?%s' % (reverse('crashstats.report_list'),
                                     current_query.urlencode())

    # TODO do something more user-friendly in the case of missing data...
    # TODO will require template work
    if not data['report_list']['hits']:
        raise Exception('No data for report')

    data['product'] = data['report_list']['hits'][0]['product']
    data['version'] = data['report_list']['hits'][0]['version']
    data['signature'] = data['report_list']['hits'][0]['signature']

    data['report_list']['total_pages'] = int(math.ceil(
        data['report_list']['total'] / float(results_per_page)))

    data['report_list']['total_count'] = data['report_list']['total']

    data['comments'] = []
    data['table'] = {}
    data['crashes'] = []

    for report in data['report_list']['hits']:
        buildid = report['build']
        os_name = report['os_name']

        report['date_processed'] = datetime.datetime.strptime(
            report['date_processed'],
            '%Y-%m-%d %H:%M:%S.%f+00:00'
        ).strftime('%b %d, %Y %H:%M')

        report['install_time'] = datetime.datetime.strptime(
            report['install_time'],
            '%Y-%m-%d %H:%M:%S+00:00'
        ).strftime('%Y-%m-%d %H:%M:%S')

        data['hits'] = report

        if buildid not in data['table']:
            data['table'][buildid] = {}
        if 'total' not in data['table'][buildid]:
            data['table'][buildid]['total'] = 1
        else:
            data['table'][buildid]['total'] += 1

        if os_name not in data['table'][buildid]:
            data['table'][buildid][os_name] = 1
        else:
            data['table'][buildid][os_name] += 1

        if report['user_comments']:
            data['comments'].append((report['user_comments'],
                                     report['uuid'],
                                     report['date_processed']))

    bugs_api = models.Bugs()
    data['bug_associations'] = bugs_api.get(
        [data['signature']]
    )['bug_associations']

    return render(request, 'crashstats/report_list.html', data)


@set_base_data
def query(request):
    data = {}

    results_per_page = 100

    try:
        data['current_page'] = int(request.GET.get('page', 1))
    except ValueError:
        return http.HttpResponseBadRequest('Invalid page')

    current_query = request.GET.copy()
    if 'page' in current_query:
        del current_query['page']
    data['current_url'] = '%s?%s' % (reverse('crashstats.query'),
                                     current_query.urlencode())

    api = models.Search()
    # FIXME implement me
    data['query'] = api.get(
        product='Firefox',
        versions='18.0a1;17.0a2;16.0b2;15.0.1',
        signature='nsIView::GetViewFor(nsIWidget*)',
        os_names='Windows;Mac;Linux',
        start_date='2012-09-03',
        end_date='2012-09-10',
        limit='100'
    )

    data['query']['total_pages'] = int(math.ceil(
        data['query']['total'] / float(results_per_page)))
    data['query']['total_count'] = data['query']['total']

    return render(request, 'crashstats/query.html', data)


@utils.json_view
def buginfo(request, signatures=None):
    form = forms.BugInfoForm(request.GET)
    if not form.is_valid():
        return http.HttpResponseBadRequest(str(form.errors))

    bugs = form.cleaned_data['bug_ids']
    fields = form.cleaned_data['include_fields']

    bzapi = models.BugzillaBugInfo()
    return bzapi.get(bugs, fields)


@set_base_data
@utils.json_view
def plot_signature(request, product, versions, start_date, end_date,
                   signature):
    date_format = '%Y-%m-%d'
    try:
        start_date = datetime.datetime.strptime(start_date, date_format)
        end_date = datetime.datetime.strptime(end_date, date_format)
    except ValueError, msg:
        return http.HttpResponseBadRequest(str(msg))

    diff = end_date - start_date
    duration = diff.days * 24.0 + diff.seconds / 3600.0

    api = models.SignatureTrend()
    sigtrend = api.get(product, versions, signature, end_date, duration)

    graph_data = {
        'startDate': sigtrend['start_date'],
        'signature': sigtrend['signature'],
        'endDate': sigtrend['end_date'],
        'counts': [],
        'percents': [],
    }

    for s in sigtrend['signatureHistory']:
        t = utils.unixtime(s['date'], millis=True)
        graph_data['counts'].append([t, s['count']])
        graph_data['percents'].append([t, (s['percentOfTotal'] * 100)])

    return graph_data


@utils.json_view
def signature_summary(request):

    range_value = int(request.GET.get('range_value'))
    # FIXME only support "days"
    range_unit = request.GET.get('range_unit')
    signature = request.GET.get('signature')
    product_version = request.GET.get('version')

    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=range_value)

    report_types = {
        'architecture': 'architectures',
        'flash_version': 'flashVersions',
        'os': 'percentageByOs',
        'process_type': 'processTypes',
        'products': 'productVersions',
        'uptime': 'uptimeRange'
    }

    api = models.SignatureSummary()

    result = {}
    signature_summary = {}
    for r in report_types:
        name = report_types[r]
        result[name] = api.get(r, signature, start_date, end_date)
        signature_summary[name] = []

    # FIXME fix JS so it takes above format..
    for r in result['architectures']:
        signature_summary['architectures'].append({
            'architecture': r['category'],
            'percentage': '%.2f' % (float(r['percentage']) * 100),
            'numberOfCrashes': r['report_count']})
    for r in result['percentageByOs']:
        signature_summary['percentageByOs'].append({
            'os': r['category'],
            'percentage': '%.2f' % (float(r['percentage']) * 100),
            'numberOfCrashes': r['report_count']})
    for r in result['productVersions']:
        signature_summary['productVersions'].append({
            'product': r['product_name'],
            'version': r['version_string'],
            'percentage': '%.2f' % float(r['percentage']),
            'numberOfCrashes': r['report_count']})
    for r in result['uptimeRange']:
        signature_summary['uptimeRange'].append({
            'range': r['category'],
            'percentage': '%.2f' % (float(r['percentage']) * 100),
            'numberOfCrashes': r['report_count']})
    for r in result['processTypes']:
        signature_summary['processTypes'].append({
            'processType': r['category'],
            'percentage': '%.2f' % (float(r['percentage']) * 100),
            'numberOfCrashes': r['report_count']})
    for r in result['flashVersions']:
        signature_summary['flashVersions'].append({
            'flashVersion': r['category'],
            'percentage': '%.2f' % (float(r['percentage']) * 100),
            'numberOfCrashes': r['report_count']})

    return signature_summary


class BuildsRss(Feed):
    def link(self, data):
        return data['request'].path

    def get_object(self, request, product, versions=None):
        return {'product': product, 'versions': versions, 'request': request}

    def title(self, data):
        return "Crash Stats for Mozilla Nightly Builds for " + data['product']

    def items(self, data):
        api = models.DailyBuilds()
        all_builds = api.get(data['product'], version=data['versions'])
        nightly_builds = []
        for build in all_builds:
            if build['build_type'] == 'Nightly':
                nightly_builds.append(build)
        return nightly_builds

    def item_title(self, item):
        return (
            '%s  %s - %s - Build ID# %s' %
            (item['product'],
             item['version'],
             item['platform'],
             item['buildid'])
        )

    def item_link(self, item):
        return ('%s?build_id=%s&do_query=1' %
                (reverse('crashstats.query'), item['buildid']))

    def item_description(self, item):
        return self.item_title(item)

    def item_pubdate(self, item):
        return datetime.datetime.strptime(item['date'], '%Y-%m-%d')
