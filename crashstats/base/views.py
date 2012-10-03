import sys
import traceback
from StringIO import StringIO

from django.conf import settings
from django.shortcuts import render


def handler500(request):
    data = {}
    err_type, err_value, err_traceback = sys.exc_info()
    out = StringIO()
    traceback.print_exc(file=out)
    traceback_formatted = out.getvalue()
    data['err_type'] = err_type
    data['err_value'] = err_value
    data['err_traceback'] = traceback_formatted
    # this is needed since no middleware will set a default product
    # and our crashstats_base.html needs it to exist
    data['product'] = settings.DEFAULT_PRODUCT
    return render(request, '500.html', data, status=500)
