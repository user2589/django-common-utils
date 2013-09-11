# -*- coding: utf-8 -*-
from django.conf import settings
from django.utils import translation
from django.utils.html import strip_spaces_between_tags
from django.core.exceptions import ImproperlyConfigured, MiddlewareNotUsed

class CompressHTML(object):
    """ middleware - different settings for several hosts based on the same code"""
    def process_response(self, request, response):
        if response.status_code == 200 and not settings.DEBUG \
                and 'text/html' in response['Content-Type']:
            response.content = strip_spaces_between_tags(response.content)
            response['Content-Length'] = str(len(response.content))
        return response

class LangByTldMIddleware(object):
    """ middleware - different settings for several hosts based on the same code"""
    LANG_BY_TLD = {
        'ae' : 'ar',
        'cn' : 'zh-cn',
        'hk' : 'zh-cn',
        'tw' : 'zh-cn',
        'th' : 'th',
        'ru' : 'ru',
        'ua' : 'ru',
        'ca' : 'en',
        'uk' : 'en',
        'us' : 'en',
    }
    def __init__(self):
        if not settings.USE_I18N:
            raise MiddlewareNotUsed()

    def process_request(self, request):
        if not hasattr(request, 'LANGUAGE_CODE'):
            raise ImproperlyConfigured('LangByTldMIddleware should be below django.middleware.LocaleMiddleware')

        if hasattr(request, 'session') and 'django_language' in request.session or \
            settings.LANGUAGE_COOKIE_NAME in request.COOKIES:
            return None

        if request.LANGUAGE_CODE not in request.META.get('HTTP_ACCEPT_LANGUAGE', ''):
            domain = request.get_host()
            tld = domain.split(':', 1)[0].rsplit('.', 1)[-1]
            language = self.LANG_BY_TLD.get(tld, settings.LANGUAGE_CODE)
            if language:
                translation.activate(language)
                request.LANGUAGE_CODE = translation.get_language()
                request.session['django_language'] = language
