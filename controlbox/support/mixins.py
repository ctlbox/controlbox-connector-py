import threading


class CommonEqualityMixin(object):
    """  a deep equals comparison for value objects. """
    local = threading.local()

    def __eq__(self, other):
        if not hasattr(CommonEqualityMixin.local, 'seen'):
            CommonEqualityMixin.local.seen = []
        seen = CommonEqualityMixin.local.seen
        return hasattr(other, '__dict__') and isinstance(other, self.__class__) \
            and self._dicts_equal(other, seen)

    def __str__(self):
        return super().__str__() + ':' + str(self.__dict__)

    def _dicts_equal(self, other, seen):
        p = (self, other)
        if p in seen:
            raise ValueError("recursive call " + p)

        d1 = self.__dict__
        d2 = other.__dict__
        try:
            seen.append(p)
            result = d1 == d2
        finally:
            seen.pop()
        return result

    def __ne__(self, other):
        return not self.__eq__(other)


def add_method(target, method, name=None):
    if name is None:
        name = method.__name__
    setattr(target, name, method)


def __str__(self):
    return str(self.__dict__)
