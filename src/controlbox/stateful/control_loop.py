from controlbox.stateful.api import DynamicContainer, ContainedObject, ValueObject
from controlbox.stateless.codecs import Codec, ShortCodec, is_mask_complete
from controlbox.support.mixins import CommonEqualityMixin


class ControllerLoopState(CommonEqualityMixin):
    """
    Configuration of a controller loop.
    """

    def __init__(self, enabled=None, log_period=None, period=None):
        if log_period is not None and (log_period < 0 or log_period > 7):
            raise ValueError("invalid log period " + str(log_period))
        if period is not None and (period < 0 or period > 65535):
            raise ValueError("invalid period " + period)
        self._enabled = enabled
        # range from 0..7. The log period is 0 if zero, else 2^(n-1)
        self._log_period = log_period
        self._period = period


class ControllerLoopStateCodec(Codec):
    period_codec = ShortCodec()

    @staticmethod
    def log_periods():
        return {x: 1 << (x - 1) if x else x for x in range(8)}

    def encoded_len(self):
        return 3

    def decode(self, buf, mask=None):
        return self._decode(ControllerLoopState(), buf, mask)

    def _decode(self, value: ControllerLoopState, buf, mask):
        if not mask or ((mask[0] & 0x08) != 0):
            value._enabled = (buf[0] & 0x08) != 0

        if not mask or ((mask[0] & 0x07) == 0x07):
            value._log_period = buf[0] & 0x07

        if not mask or is_mask_complete(mask[1:3]):
            value._period = self.period_codec.decode(buf[1:3])

        return value

    def encode(self, value: ControllerLoopState):
        mask = bytearray(3)
        data = bytearray(3)

        mask[0] = 0xF0      # upper nibble not presently used
        if value._enabled is not None:
            mask[0] |= 8
            data[0] |= 8 if value._enabled else 0

        if value._log_period is not None:
            mask[0] |= 7
            data[0] |= value._log_period & 7

        if value._period is not None:
            mask[1] = 0xFF
            mask[2] = 0xFF
            period_buf, period_mask = self.period_codec.encode(value._period)
            data[1:3] = period_buf

        return data, mask


class ControllerLoop(ValueObject):
    """ Represents a control loop in the ControllerLoopContainer. """


class ControllerLoopContainer(DynamicContainer):
    """
    Describes a controller loop container.
    """
    def __init__(self, parent):
        super().__init__()
        self.config_container = DynamicContainer(self.controller, self, 0)
        self.configs = dict()

    def configuration_for(self, o: ContainedObject) -> ControllerLoop:
        if o.container != self:
            raise ValueError()
        return self.configurations[o.slot]

    @property
    def configurations(self):
        """
        :return: a dictionary mapping item slots to the ControllerLoop object that controls that loop.
        """
        return self.configs

    def notify_added(self, obj: ContainedObject):
        """ When an object is added, the controller also adds a config object to the config container. """
        self.configs[obj.slot] = ControllerLoop(
            self.controller, self.config_container, obj.slot)

    def notify_removed(self, obj: ContainedObject):
        del self.configs[obj.slot]
