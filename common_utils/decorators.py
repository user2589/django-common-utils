# -*- coding: utf-8 -*-
from django.conf import settings

from django import http, template, shortcuts
from django.core.cache import cache
from django.utils import simplejson

from annoying.decorators import wraps

#required by @cache_view
import time
from django.utils.http import http_date
from django.utils.cache import patch_cache_control

import logging
log = logging.getLogger('common_utils.decorators')

def JSONP(view_func):
    """if you don't know what is JSONP, don't use this decorator"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        template.RequestContext(request) # handle request language
        result = view_func(request, *args, **kwargs)

        if isinstance(result, http.HttpResponse):
            return result

        # form.errors values are Promise objects.
        # they have to be forced to unicode before serializing
        if isinstance(result, dict) and 'errors' in result:
            result['errors'] = dict((key, unicode(value)) \
                for key, value in result['errors'].iteritems())

        # if opened in browser, set up nice indent
        indent= None if request.is_ajax() else 4
        response_text = simplejson.dumps(result, indent)

        if 'callback' in request.GET:
            response_text = ''.join(
                    (request.GET['callback'], '(', response_text, ')')
                )
        return http.HttpResponse(
                response_text,
                mimetype='application/javascript'
            )
    return wrapper

SKIP_HTTPS = getattr(settings, 'SKIP_HTTPS', False)

def force_secure(view_func):
    """decorator to force https"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not SKIP_HTTPS and \
                (request.method == 'GET' and not request.is_secure()):
            domain = request.get_host().split(':', 1)[0] #skip port
            path = request.get_full_path()
            return shortcuts.redirect(''.join(('https://', domain, path)))
        return view_func(request, *args, **kwargs)
    return wrapper

_cache_prefix = getattr(settings, 'KEY_PREFIX') \
    or getattr(settings, 'CACHE_MIDDLEWARE_KEY_PREFIX')

def memo_base(memo_func, cache_duration=settings.CACHE_MIDDLEWARE_SECONDS):
    """ check out cache_view for usage """
    def decorator(key_func):
        """ key func should return list of key chunks,
         or None if call should not be cached """
        @wraps(memo_func)
        def call_func(*args, **kwargs):
            cache_key_chunks = key_func(*args, **kwargs)
            if cache_key_chunks is None: # no caching
                return memo_func(*args, **kwargs)
            cache_key = ":".join(
                [_cache_prefix, memo_func.__name__] + cache_key_chunks
            ).replace(' ', '_')
            #memcached utilizes keys up to 250 chars
            #assert len(cache_key)<=250
            cached = cache.get(cache_key)
            if cached:
                log.debug('cache hit: ' + cache_key)
                return cached
            log.debug('cache miss: ' + cache_key)
            cached = memo_func(*args, **kwargs)
            cache.set(cache_key, cached, cache_duration)
            return cached
        return call_func
    return decorator

def cache_view(cache_duration=settings.CACHE_MIDDLEWARE_SECONDS):
    def decorator(view_func):
        def add_expires(another_view_func):
            """ we need to go deeper (c) Inception
                This decorator adds cache headers to response before
                it is handled by @memo_base
            """
            @wraps(another_view_func)
            def wrapper(*args, **kwargs):
                response = another_view_func(*args, **kwargs)
                if isinstance(response, http.HttpResponse) \
                    and not settings.DEBUG:
                    expiry = time.time() + cache_duration
                    response['Expires']         = http_date(expiry)
                    response['X-Cache-Expires'] = http_date(expiry)
                    response['X-Cache-Time']    = http_date()
                    response['X-Cache']         = 'Miss'

                    patch_cache_control(response, max_age=cache_duration)
                return response
            return wrapper

        @memo_base(add_expires(view_func), cache_duration)
        def key_func(request, *args, **kwargs):
            if settings.CACHE_MIDDLEWARE_ANONYMOUS_ONLY \
                and hasattr(request, 'user') \
                and request.user.is_authenticated():
                return None
            if request.GET or request.POST: #no caching for submitted forms
                return None
            username = '' or (hasattr(request, 'user') \
                        and request.user.username)
            return [username, request.LANGUAGE_CODE, request.path]
        return key_func
    return decorator

def memoize(cache_duration=settings.CACHE_MIDDLEWARE_SECONDS):
    """ caches func output considering only positional arguments"""
    def decorator(func):
        @memo_base(func, cache_duration)
        def key_func(*args, **kwargs):
            #only positional args considered for cache key
            return [unicode(arg) for arg in args]
        return key_func
    return decorator
