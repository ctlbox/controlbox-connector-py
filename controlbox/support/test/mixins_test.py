import unittest

from hamcrest import equal_to, is_, assert_that, is_not, calling, raises, matches_regexp

from controlbox.support.mixins import CommonEqualityMixin, StringerMixin


class TestEquals(CommonEqualityMixin, StringerMixin):
    def __init__(self, a=None, b=None):
        self.a = a
        self.b = b


class StringerMixinTest(unittest.TestCase):
    def test_stringer(self):
        sut = TestEquals("123")
        # <controlbox.support.test.mixins_test.TestEquals object at 0x10573ef60>:{'a': '123', 'b': None}
        assert_that(str(sut), matches_regexp("<controlbox.support.test.mixins_test.TestEquals object at 0x.*>:"
                                             "{'a': '123', 'b': None}"))


class CommonEqualityMixinTest(unittest.TestCase):

    def test_value_equivalence(self):
        e1 = TestEquals()
        e2 = TestEquals()
        e1.a = "123"
        e1.b = 123
        e2.a = "12"+"3"
        e2.b = 123
        assert_that(e1, is_(equal_to(e2)))
        assert_that(e1 == e2, is_(True))
        assert_that(e1 != e2, is_(False))

        e1.b = 0
        assert_that(e1, is_not(equal_to(e2)))
        assert_that(e1 != e2, is_(True))
        assert_that(e1 == e2, is_(False))

    def test_recursive_call(self):
        e1 = TestEquals()
        e2 = TestEquals()
        e2.a = e1
        e1.a = e2

        def compare():
            return e2 == e1

        # todo - find out why the ValueError is converted to a TypeError
        assert_that(calling(compare), raises(TypeError))
