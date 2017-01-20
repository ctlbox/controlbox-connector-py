from controlbox.conduit.discovery import PolledResourceDiscovery, ResourceAvailableEvent, ResourceUnavailableEvent
from controlbox.connector_maintainance import ConnectionManager


class ConnectorDiscovery:
    """
    Listens for events from a ResourceDiscovery instance and uses the connector_factory to create a connector
    corresponding to the resource type discovered.

    A resource might be a serial port, a local executable file or a TCP Server.
    Part of the responsibility of this class is to convert from raw
    resources (e.g. serial ports) to the corresponding Connector via
    the connector_factory

    The connector is left unconnected, and used to notify
    a ConnectorManager about the resource availability.

    :param discovery:   a resource discovery that is polled from time to time
        to discover new resources. The discovery watches for resources of interest,
        such as files in a directory, serial ports, TCP endpoints etc..
    :param connector_factory    a callable that is called with the key and resource discovered. Depending upon the type
        of resource discovery, the resource may already be a Connector, or it may be some other kind of
        resource, like a file, serial port or remote address.
    :param connector_manager   when a resource is discovered, it is
        registered with the connector manager as available, and when the
        resource is no longer available, it is unregistered.
    """
    def __init__(self, discovery: PolledResourceDiscovery, connector_factory,
                 connector_manager: ConnectionManager=None):
        """
        :param discovery A ResourceDiscovery instance that publishes events as resources become available.
        :param connector_factory A callable. Given the (key,target) info from the ResourceDiscovery,
            the factory is responsible for creating a connector.
        :param connector_manager The manager that is notified of resources changing availability. Should support
            available(resource, connector) and unavailable(resource)
        """
        self.discovery = discovery
        self._connector_factory = connector_factory
        self.manager = connector_manager    # the manager can be set externally
        discovery.listeners.add(self.resource_event)

    def dispose(self):
        self.discovery.listeners.remove(self.resource_event)

    def _create_connector(self, key, resource):
        return self._connector_factory(key, resource)

    def resource_event(self, event):
        """ receives resource notifications from the ResourceDiscovery.
            When a resource is available, the connector factory is invoked to create a connector for the resource.
            When a resource is unavailable, the connection manager is notified.
        """
        if not self.manager:
            return
        if type(event) is ResourceAvailableEvent:
            connector = self._create_connector(event.key, event.resource)
            if connector:
                self.manager.available(event.key, connector)
        elif type(event) is ResourceUnavailableEvent:
            self.manager.unavailable(event.key)

    def update(self):
        """
        Updates discovered resources.
        """
        self.discovery.update()


class ManagedConnectorDiscoveries:
    """
    Manages multiple ConnectorDiscovery instances associated
    with the same ConnectorManager instance
    """

    def __init__(self, controller_discoveries, manager:ConnectionManager):
        """
        :param controller_discoveries  iterable of ControllerDiscovery instances used to detect endpoints.
            See build_serial_discovery and build_tcp_server_discovery
        """
        self.manager = manager
        self.discoveries = controller_discoveries
        for d in self.discoveries:
            d.manager = self.manager

    def update(self):
        """
        updates all the discovery objects and updates the manager too.
        """
        for d in self.discoveries:
            d.update()
        self.manager.update()


