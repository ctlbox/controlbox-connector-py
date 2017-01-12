from unittest import TestCase

from controlbox.stateless.codecs import ConnectorCodec, DictionaryMappingCodec, IdentityCodec, TypeMappingCodec


class ConnectorCodecTest(TestCase):
    def test_encode_throws_not_implemented_error(self):
        with self.assertRaises(NotImplementedError):
            ConnectorCodec().encode(0, 0)

    def test_decode_throws_not_implemented_error(self):
        with self.assertRaises(NotImplementedError):
            ConnectorCodec().decode(0, [])


class IdentityCodecTest(TestCase):
    def test_encode_returns_buffer(self):
        buf = [1, 2, 3]
        self.assertEqual(buf, IdentityCodec().encode(0, buf))

    def test_decode_returns_buffer(self):
        buf = [1, 2, 3]
        self.assertEqual(buf, IdentityCodec().decode(0, buf))


class TypeMappingCodecTest(TestCase):

    def test_retrieves_codec_by_type_using_the_callable(self):
        codec = ConnectorCodec()
        codec.encode = lambda type, value: [type * value]
        codec.decode = lambda type, buf, mask: type * len(buf) * 2

        def mapping(type):
            return codec

        sut = TypeMappingCodec(mapping)
        self.assertIs(codec, mapping(5))
        self.assertEqual([50], sut.encode(5, 10))
        self.assertEqual(30, sut.decode(5, [1, 2, 3]))


class DictionaryMappingCodecTest(TestCase):
    def setUp(self):
        codec = ConnectorCodec()
        codec.encode = lambda type, value: [type * value]
        codec.decode = lambda type, buf, mask: type * len(buf) * 2
        mapping = {5: codec}
        self.sut = DictionaryMappingCodec(mapping)
        self.assertIs(codec, mapping.get(5))

    def test_retrieves_codec_by_type_using_the_callable(self):
        self.assertEqual([50], self.sut.encode(5, 10))
        self.assertEqual(30, self.sut.decode(5, [1, 2, 3]))

    def test_throws_exception_when_the_type_isnot_recognised(self):
        with self.assertRaises(KeyError):
            self.sut.decode(6, [])
