import threading


def quote(val):
    return "'" + str(val) + "'" if val is not None else "None"


class StringerMixin:

    def __str__(self):
        """
        outputs the base class string representation and the object dictionary
        in key sorted order
        :return:
        """
        return super().__str__() + ':' + self._sorted_items_string()

    def _sorted_items_string(self):
        return "{" + ", ".join([("'" + str(key)) + "'" + ": " + (quote(val))
                                for key, val in sorted(self.__dict__.items())]) + "}"


class CommonEqualityMixin(object):
    """  a deep equals comparison for value objects. """
    local = threading.local()

    def __eq__(self, other):
        if not hasattr(CommonEqualityMixin.local, 'seen'):
            CommonEqualityMixin.local.seen = []
        seen = CommonEqualityMixin.local.seen
        return hasattr(other, '__dict__') and isinstance(other, self.__class__) \
            and self._dicts_equal(other, seen)

    def _dicts_equal(self, other, seen):
        p = (id(self), id(other))
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


# def add_method(target, method, name=None):
#     if name is None:
#         name = method.__name__
#     setattr(target, name, method)
#
#
# def __str__(self):
#     return str(self.__dict__)
