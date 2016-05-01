import types
from functools import wraps


def no_op_method_wrapper():
    def wrapper_factory(func):
        """
        the wrapper just invokes the wrapped function.
        """
        @wraps(func)
        def wrapped(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapped
    return wrapper_factory


def notify_exception_method_wrapper(listener):

    def wrapper_factory(func):
        """
        wraps a function to provide a callback when an exception occurs.
        The actual exception isn't passed.
        """
        @wraps(func)
        def wrapped(*args, **kwargs):
            success = False
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            finally:
                if not success:
                    listener()

        return wrapped

    return wrapper_factory


def make_exception_notify_proxy(target, listener):
    return MethodWrappingProxy(target, notify_exception_method_wrapper(listener))


class MethodWrappingProxy(object):

    def __init__(self, target, wrapper):
        self._wrapper = wrapper
        self._target = target

    def __getattribute__(self, name):
        target = object.__getattribute__(self, "_target")
        attr = target.__getattribute__(name)
        if isinstance(attr, types.MethodType):
            wrapper = object.__getattribute__(self, "_wrapper")
            attr = wrapper(attr)
        return attr
