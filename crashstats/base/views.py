import sys
from django.conf import settings
from django.shortcuts import render
from crashstats.crashstats.models import BadStatusCodeError


def handler500(request):
    status = 500
    data = {
        'product': settings.DEFAULT_PRODUCT,
        'middleware_error': False,
    }
    err_type, err_value, __ = sys.exc_info()

    if err_type is BadStatusCodeError:
        # interesting!
        error_code = err_value.args[0].split()[0]
        if error_code.isdigit() and error_code[0] == '4':
            data['middleware_error'] = int(error_code)
            status = int(error_code)
    return render(request, '500.html', data, status=status)


def handler404(request):
    data = {'product': settings.DEFAULT_PRODUCT}
    return render(request, '404.html', data, status=404)
