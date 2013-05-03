import datetime
import functools
from collections import defaultdict

from django.contrib import messages
from django.views.decorators.http import require_POST
from django.core.urlresolvers import reverse
from django.shortcuts import render, redirect

from crashstats.crashstats.models import (
    CurrentProducts,
    ReleasesFeatured
)


def admin_required(view_func):
    @functools.wraps(view_func)
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated():
            messages.error(
                request,
                'You are not logged in'
            )
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return inner


@admin_required
def home(request):
    # because of temporary lack of other things to do on the admin pages,
    # let's go straight to the only feature available
    return redirect('manage:featured_versions')
    #data = {}
    #return render(request, 'manage/home.html', data)


@admin_required
def featured_versions(request):
    data = {}

    products_api = CurrentProducts()
    products_api.cache_seconds = 0
    products = products_api.get()

    data['products'] = products['products']  # yuck!

    releases = products['hits']
    _all_products = defaultdict(list)
    for product_name in data['products']:
        for release in releases[product_name]:
            _all_products[product_name].append(release)

    data['versions'] = {}
    now = datetime.date.today()
    for product in _all_products:
        data['versions'][product] = []
        versions = _all_products[product]

        for version in versions:
            start_date = datetime.datetime.strptime(
                version['start_date'],
                '%Y-%m-%d'
            ).date()
            if start_date > now:
                continue
            end_date = datetime.datetime.strptime(
                version['end_date'],
                '%Y-%m-%d'
            ).date()
            if end_date < now:
                continue
            data['versions'][product].append(version)

    return render(request, 'manage/featured_versions.html', data)


@admin_required
@require_POST
def update_featured_versions(request):
    products_api = CurrentProducts()
    products = products_api.get()['products']

    data = {}
    for product in request.POST:
        if product in products:
            data[product] = request.POST.getlist(product)

    featured_api = ReleasesFeatured()
    if featured_api.put(**data):
        messages.success(
            request,
            'Featured versions successfully updated.'
        )

    url = reverse('manage:featured_versions')
    return redirect(url)
