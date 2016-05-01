from unittest.mock import Mock

from hamcrest import assert_that, calling, raises, is_

from controlbox.support.proxy import MethodWrappingProxy, no_op_method_wrapper, \
    make_exception_notify_proxy
import unittest


class TestTarget:
    """
    a proxy target used to help with the
    """
    def __init__(self):
        self.a = 10

    def someFunc(self, offset):
        return 42 + offset

    def delegateFunc(self, offset):
        return self.someFunc(offset)

    def setA(self, v):
        self.a = v

    def getA(self):
        return self.a

    def raiseException(self, hell, raise_hell=True):
        if raise_hell:
            raise hell


class MethodWrappingProxyTest(unittest.TestCase):

    def test_proxy_behaves_the_same(self):
        target = TestTarget()
        wrapper = no_op_method_wrapper()
        p = MethodWrappingProxy(target, wrapper)
        self.assertEqual(p.someFunc(10), 52)
        self.assertEqual(p.delegateFunc(10), 52)
        self.assertEqual(p.a, 10)

        # no _target attribute available externally
        success = False
        try:
            target = p._target
        except AttributeError:
            success = True
        assert_that(success, is_(True))

    def test_proxy_wrap_exception(self):
        mock = Mock()
        p = make_exception_notify_proxy(TestTarget(), mock)
        mock.assert_not_called()
        # first try a benign method
        assert_that(p.someFunc(10), is_(52))
        mock.assert_not_called()
        assert_that(calling(p.raiseException).with_args(ValueError), raises(ValueError))
        mock.assert_called_once_with()


# @unittest.skip("wip")
# class ProxyTst(unittest.TestCase):
#
#     def test_proxy_behaves_the_same(self):
#         p = Proxy(TestTarget())
#         self.assertEqual(p.someFunc(10), 52)
#         self.assertEqual(p.delegateFunc(10), 52)
#         self.assertEqual(p.a, 10)
#
#     def test_proxyOverrideDelegateMethod(self):
#         """
#         overrides one method in the proxy.
#         """
#         class OverrideDelegateProxy(Proxy):
#
#             def someFunc(self, offset):
#                 return self.a + offset
#
#         p = OverrideDelegateProxy(TestTarget())
#         # a=10, offset 0, result is 10
#         self.assertEqual(p.someFunc(0), 10)
#         p.a = 20
#         # a=20, offset 15, result is 35
#         self.assertEqual(p.someFunc(15), 35)
#         # self.assertEqual(p.delegateFunc(15), 35)    # direct call - if it's
#         # 57, that means the original method is called, and not the proxy
#
#     def test_makeProxy(self):
#         TestTargetProxy = Proxy(TestTarget())
#
#         class OverrideDelegate(TestTargetProxy):
#
#             def __init__(self):
#                 TestTargetProxy.__init__(self)
#
#             def someFunc(self, offset):
#                 return self.getA() + offset
#
#         p = OverrideDelegate()
#         p.delegate_TestTarget(TestTarget())
#         # a=10, offset 0, result is 10
#         self.assertEqual(p.someFunc(0), 10)
#         p.setA(20)
#         # a=20, offset 15, result is 35
#         self.assertEqual(p.someFunc(15), 35)
#         # self.assertEqual(p.delegateFunc(15), 35)    # direct call - if it's
#         # 57, that means the original method is called, and not the proxy


if __name__ == '__main__':
    unittest.main()
