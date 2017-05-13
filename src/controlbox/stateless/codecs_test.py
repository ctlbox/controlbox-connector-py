from unittest import TestCase

from controlbox.stateless.codecs import Codec, DictionaryMappingCodecRepo, IdentityCodec, TypeMappingCodecRepo


class ConnectorCodecTest(TestCase):
    def test_encode_throws_not_implemented_error(self):
        with self.assertRaises(NotImplementedError):
            Codec().encode(0)

    def test_decode_throws_not_implemented_error(self):
        with self.assertRaises(NotImplementedError):
            Codec().decode([])


class IdentityCodecTest(TestCase):
    def test_encode_returns_buffer(self):
        buf = [1, 2, 3]
        self.assertEqual(buf, IdentityCodec().encode(buf))

    def test_decode_returns_buffer(self):
        buf = [1, 2, 3]
        self.assertEqual(buf, IdentityCodec().decode(buf))


class TypeMappingCodecTest(TestCase):

    def test_retrieves_codec_by_type_using_the_callable(self):
        codec = Codec()
        codec.encode = lambda value: [value]
        codec.decode = lambda buf, mask: len(buf) * 2

        def mapping(type):
            return codec

        sut = TypeMappingCodecRepo(mapping)
        self.assertIs(codec, mapping(5))
        self.assertEqual([10], sut.encode(5, 10))
        self.assertEqual(6, sut.decode(5, [1, 2, 3]))


class DictionaryMappingCodecTest(TestCase):
    def setUp(self):
        codec = Codec()
        codec.encode = lambda value: [value]
        codec.decode = lambda buf, mask: len(buf) * 2
        mapping = {5: codec}
        self.sut = DictionaryMappingCodecRepo(mapping)
        self.assertIs(codec, mapping.get(5))

    def test_retrieves_codec_by_type_using_the_callable(self):
        self.assertEqual([10], self.sut.encode(5, 10))
        self.assertEqual(6, self.sut.decode(5, [1, 2, 3]))

    def test_throws_exception_when_the_type_isnot_recognised(self):
        with self.assertRaises(KeyError):
            self.sut.decode(6, [])
