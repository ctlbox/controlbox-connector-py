from abc import abstractmethod

from controlbox.support.mixins import CommonEqualityMixin, StringerMixin


class ConnectorCodec:
    """
    Knows how to convert object state to/from the on-wire data format.
    """

    @abstractmethod
    def decode(self, type, data, mask=None):
        """
        decodes an object state representation.
        realm: either constructor or state
        """
        raise NotImplementedError()

    @abstractmethod
    def encode(self, type, value):
        """ returns (type, data, mask)
            Encodes a given value as a data buffer and a mask.
         """
        raise NotImplementedError()


class IdentityCodec(ConnectorCodec):
    """
    An identity codec - the input is returned as the result regardless of type
    """

    def encode(self, type, value):
        return value

    def decode(self, type, data, mask=None):
        return data


class TypeMappingCodec(ConnectorCodec):
    def __init__(self, codecs: callable):
        self.codecs = codecs

    def encode(self, type, value):
        delegate = self.fetch(type)
        return delegate.encode(type, value)

    def decode(self, type, data, mask=None):
        delegate = self.fetch(type)
        return delegate.decode(type, data, mask)

    def fetch(self, type):
        delegate = self.codecs(type)
        if not delegate:
            raise KeyError()
        return delegate


class DictionaryMappingCodec(TypeMappingCodec):
    def __init__(self, codecs: dict):
        super().__init__(self.lookup)
        self.codecs_dict = codecs

    def lookup(self, type):
        return self.codecs_dict.get(type)


class BaseState(CommonEqualityMixin, StringerMixin):
    """
    A value type that supports equality checking and to string conversion.
    """
    pass
