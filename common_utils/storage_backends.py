# -*- coding: utf-8 -*-
import logging
import os, tempfile, commands
import urllib2
from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.files import File
from django.utils import simplejson
from poster.encode import multipart_encode
from poster.streaminghttp import register_openers

#punypng part
register_openers()
#end of punypng part

log = logging.getLogger('common_utils.storages')

NOCOMPRESS = getattr(settings, 'NOCOMPRESS', ())

PUNYPNG_KEYS = getattr(settings, 'PUNYPNG_KEYS', [])

CSSTIDY_OPTIONS = getattr(settings, 'CSSTIDY_OPTIONS',
                '--template=highest --remove_last_\;=true --silent=true')
"""
--preserve_css=true|false - space optimization only, don't touch comments
--remove_last_\;=true|false - {property:value;} -> {property:value}
--merge_selectors=[2|1|0]
"""

YUI_JAR = getattr(settings, 'YUI_JAR',
        os.path.join(os.path.dirname(__file__), 'yuicompressor.jar'))
GCLOSURE_JAR = getattr(settings, 'GCLOSURE_JAR',
        os.path.join(os.path.dirname(__file__), 'compiler.jar'))
GCLOSURE_COMPILER_OPTIONS = getattr(settings, 'GCLOSURE_COMPILER_OPTIONS',
        ' --compilation_level SIMPLE_OPTIMIZATIONS --warning_level QUIET')
"""
--compilation_level =
        WHITESPACE_ONLY|SIMPLE_OPTIMIZATIONS|ADVANCED_OPTIMIZATIONS
--warning_level = QUIET | DEFAULT | VERBOSE
"""

class PunyKeys(object):
    def __init__(self, keys):
        self.keys = keys
        self.index = 0

    def current(self):
        return self.keys[self.index]

    def next(self):
        if self.index >= len(self.keys) - 1:
            raise RuntimeError(
                "We've ran out of punypng keys (did we have any?)! "
                "Add more keys to settings.PUNYPNG_KEYS"
            )
        self.index += 1
        return self.current()

PUNYKEY_GEN = PunyKeys(PUNYPNG_KEYS)

def temp_file(content):
    """creates temporary file with specified content and returns file object"""
    file = tempfile.NamedTemporaryFile()
    file.write(content)
    file.flush()
    return file

def compressor(func):
    def wrapper(fname, *args, **kwargs):
        func_name = func.__name__
        input_len = os.path.getsize(fname) or 1
        command = func(fname, *args, **kwargs)
        log.debug("%s command: %s"%(func_name, command))
        error, output = commands.getstatusoutput(command)
        if error:
            raise RuntimeError("Error running %s: \n %s\n"%(func_name, output))
        log.info("compression rate: %s%%" % (len(output)*100/input_len))
        if len(output) > input_len:
            raise RuntimeError("\t compression SKIPPED")
        return File(temp_file(output))
    return wrapper

@compressor
def csstidy(fname, options=CSSTIDY_OPTIONS):
    """ csstidy css compressor  """
    return "csstidy %s %s" % (fname, options)

@compressor
def yui_css_compressor(fname):
    """ YUI css compressor  """
    return "cat %s |java -jar %s --type css" % (fname, YUI_JAR)

@compressor
def gclosure_compiler(fname, options=GCLOSURE_COMPILER_OPTIONS):
    """ google closure compiler js compressor  """
    return "java -jar %s --js %s %s" % (GCLOSURE_JAR, fname, options)

@compressor
def yui_js_compressor(fname):
    """ YUI css compressor  """
    return "cat %s |java -jar %s --type js" % (fname, YUI_JAR)

def punypng(file):
    """ punypng.com images compressor  """

    def punypng_json(file, key):
        log.debug("punypng key: %s"%key)
        datagen, headers = multipart_encode({"img": file, "key": key})
        request = urllib2.Request('http://www.punypng.com/api/optimize',
                    datagen, headers)
        response = urllib2.urlopen(request).read()
        log.debug("Punipng.com response: %s"%response)
        return simplejson.loads(response)

    while True:
        key = PUNYKEY_GEN.current()
        try:
            json = punypng_json(file, key)
        except IOError:
            return file
        if 'error' not in json:
            break
        if 'daily limit' not in json['error']:
            log.warn('Punipng.com error: %s'%json['error'])
            return file
        PUNYKEY_GEN.next()

    log.info("compression rate: %s%%"%(100-json["savings_percent"]))
    optimized_url = json["optimized_url"]
    try:
        output_file = temp_file(urllib2.urlopen(optimized_url).read())
    except IOError:
        return file
    return File(output_file)

compress_css    = yui_css_compressor
compress_js     = gclosure_compiler
compress_image  = punypng

def autocompress(filename, file_obj):
    """
        filename: relative filename in project directory, eg js/jquery.1.7.2.min.js
        file_obj: absolute filename from where it is about to be copied
    """
    log.debug("autocompress %s, content: %s"%(filename, file_obj))

    ext = filename.rpartition('.')[2].lower()

    if filename in NOCOMPRESS:
        pass
    if ext == 'css':
        try:
            return compress_css(file_obj.name)
        except RuntimeError, (e):
            log.warn(e)
    elif  ext == 'js':
        try:
            return compress_js(file_obj.name)
        except RuntimeError, (e):
            log.warn(e)
    elif ext in ('jpg', 'jpeg', 'png', 'gif'):
        try:
            return compress_image(file_obj)
        except RuntimeError, (e):
            log.warn(e)
    return file_obj

class FileSystemCompressStorage(StaticFilesStorage):
    def _save(self, name, content):
        content = autocompress(name, content)
        return super(FileSystemCompressStorage, self)._save(name, content)

    def path(self, name):
        if not name: #hack to make collectstatic consider it non-local storage
            raise NotImplementedError
        return super(FileSystemCompressStorage, self).path(name)
