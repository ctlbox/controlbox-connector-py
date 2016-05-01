"""


Controller Connections

- Conduit: abstraction of a bi-directional channel. Combines 2 streams for reading and writing.
- Connector: binds a conduit and a protocol to connect to an endpoint such as a controller
- connection endpoints
 - local serial ports
 - local mDNS servers

- resource discovery - watches/scans local connection endpoints for available resources.
    SerialDiscovery, ServerDiscovery
- discovery events - posted by discovery objects -
    ResourceAvailableEvent, ResourceUnavailableEvent. The event indicates the endpoint that
    changed, such as a Serial instance or a IP/port for a server.
- ConnectionDiscovery listens to discovery events from a resource discovery instance.
    creates a connector instance to provide the connection to the endpoint and registers
    the connection with the connection manager.
- ConnectionManager - keeps track of the known potential connections to endpoints and
  attempts to open any that are not presently open. This allows for outages in the underlying
  connection. The manager tries to maintain a connection until the endpoint is no longer
  available (e.g. serial port no longer present, mDNS TTL expired and not refreshed.)
"""
