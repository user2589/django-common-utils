# -*- coding: utf-8 -*-
from django.conf import settings
import threading, Queue

queue = Queue.Queue()

def worker_thread():
    while True:
        target, target_args, target_kwargs, callback, callback_args, \
            callback_kwargs = queue.get()
        try:
            result = target(*target_args, **target_kwargs)
        except:
            pass # <-- log error here
        else:
            if callback:
                try:
                    callback(result, *callback_args, **callback_kwargs)
                except:
                    pass # <- another good chance to log something
        finally:
            queue.task_done()

def wait_all():
    queue.join()

def async(callback=None, *callback_args, **callback_kwargs):
    """executes function asynchronously in a separate thread """
    def decorator(target):
        def call_func(*target_args, **target_kwargs):
            queue.put(
                (target, target_args, target_kwargs, callback,
                 callback_args, callback_kwargs)
            )
        return call_func
    return decorator

for i in range(getattr(settings, 'DJANGO_UTILS_WORKER_THREADS', 10)):
    thread = threading.Thread(target=worker_thread)
    thread.daemon = True
    thread.start()
