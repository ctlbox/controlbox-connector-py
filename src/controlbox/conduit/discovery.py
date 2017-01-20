"""
    Resource discovery for serial ports, remote servers, executables in a folder etc.
    A given type of resource is monitored and events published as the resource
    becomes available or unavailable. For example, when a SerialDiscovery finds
    a new serial port, a ResourceAvailable event is posted with the serial port details.
"""

import logging

from controlbox.support.mixins import CommonEqualityMixin
from controlbox.support.events import EventSource

logger = logging.getLogger(__name__)


class ResourceEvent(CommonEqualityMixin):
    """ Notification about a resource. """
    def __init__(self, source, key, resource):
        """
        :param source   The ResourceDiscovery that posted this event
        :param key An identifier for the resource that is available.
        :param resource The resource itself, which may have instance-specific details beyond what is available in
            key.
        """
        self.source = source
        self.key = key
        self.resource = resource


class ResourceAvailableEvent(ResourceEvent):
    """ Signifies that a resource is available. """


class ResourceUnavailableEvent(ResourceEvent):
    """ Signifies that a resource has become unavailable. """


class ResourceDiscovery:
    """ Monitors resources for availability
        and posts notification when a new resource is available. """
    def __init__(self):
        self.listeners = EventSource()


class PolledResourceDiscovery(ResourceDiscovery):
    """
    Determines updates to the available resources in response to calling
    update()
    """

    def __init__(self):
        super().__init__()
        self.previous = {}      # the previous known resources

    def _is_allowed(self, key, device):
        """
        Template method to allow subclasses to pre-filter the set of
        recognized resources for any that should be excluded from
        discovery.

        :param
        """
        return True

    def _check_allowed(self, key, device):
        """ Determines if the given resource should be discoverable.
            This implementation calls the subclass template method.
            Other resource-neutral implementations might use additional
            criteria, such as a dictionary of excluded resources.
        """
        return self._is_allowed(key, device)

    def attached(self, key, device):
        """template method for subclasses to process a new resource"""
        logger.info("available device: %s" % key)

    def detached(self, key, device):
        """template method for subclasses to process a new resource"""
        logger.info("unavailable device: %s" % key)

    def _attach(self, key, device):
        self.attached(key, device)
        return key, device

    def _detach(self, key, device):
        self.detached(key, device)
        return key, device

    def _changed_events(self, available: dict) -> list:
        """
        Computes which resources have been added, removed or changed.
        :param available: dictionary of resource location to resource info. The key is a logical name for the
            resource, while the value is a physical attribute.
        :type available: dict
        :return: returns a list of events to send
        :rtype:
        """
        # build a map of { name: None } for all previous resources
        # after adding the list of current resources, any key that has a None value
        # has been removed.
        current_resources = {p: None for p in self.previous}
        current_resources.update(available)

        events = []  # the events to send
        for handle, current in current_resources.items():
            previous = self.previous.get(handle, None)
            if self._one_is_none(current, previous) or not self._device_eq(current, previous):
                not previous or events.append(ResourceUnavailableEvent(
                    self, *self._detach(handle, previous)))
                not current or events.append(ResourceAvailableEvent(
                    self, *self._attach(handle, current)))
        return events

    @staticmethod
    def _one_is_none(v1, v2):
        """ Determines if one of the values is None
        >>> PolledResourceDiscovery._one_is_none("a", "b")
        False
        >>> PolledResourceDiscovery._one_is_none("a", None)
        True
        >>> PolledResourceDiscovery._one_is_none(None, "b")
        True
        >>> PolledResourceDiscovery._one_is_none(None, None)
        False
        """
        return (v1 is None) != (v2 is None)

    def _device_eq(self, current, previous):
        return current == previous

    def _update(self, available: dict):
        """ given a new set of available resources, determines
            which resources have been added/changed/removed and
            fires the corresponding events.
        """
        events = self._changed_events(available)
        self.previous = available
        self._fire_events(events)

    def _fire_events(self, events):
        self.listeners.fire_all(events)

    def _fetch_available(self):
        """ Template method for subclasses to determine the current
            resources available.
        :return: a dictionary of resource handle to resource instance.
        """
        return {}

    def _filter_available(self, available: dict):
        return {k: v for k, v in available.items() if self._check_allowed(k, v)}

    def update(self):
        available = self._fetch_available()
        available = self._filter_available(available)
        self._update(available)


"""
    def _attach(self, key, device):
        connection = self.factory(key, device)
        try:
            connection.__enter__()
            self.connections[key] = connection
            return connection
        except Exception as e:
            logger.info(e)
            return None

    def _detach(self, port, device):
        conduit = self.connections.get(port, None)
        if conduit:
            try:
                del self.connections[port]
                conduit.__exit__()
            except Exception as e:
                logger.info(e)
        return conduit
"""
