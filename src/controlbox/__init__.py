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


More rough notes:

- Connectors can be arranged as a chain of aggregates, with outer connectors wrapping
inner connectors. For example, ProtocolConnector wraps a connector and decodes the protocol.
CloseOnErrorConnector wraps a connector and closes it on error.

On connecting, the inner connector is connected first, all the way down the chain.
On disconnecting, the outer connector is disconnected first, and then on to the next inner connector.

Outer connectors listen to their inner connectors for disconnected events, in case of
spontaneous disconnection (e.g. a stream error.)


## Threading

Initially everything was set to run on the main thread. Socket/Serial operations are blocking
and setting them to non-blocking doesn't work (e.g. readline() still blocks.)

The protocol is currently asynchronous - a separate thread is used to pump events. Hmm...
actually send requests are synchronous. Responses are received asynchronously by a background thread.

The protocol implementation is simple so doesn't _have_ to be asynchronous or use it's own thread.
Could add factories for futures and other things to fit with threading/multiprocessing.

Currently the zeroconf browser runs on a separate thread.
Resource discovery runs on the main thread. It uses a queue for notifications from the
zeroconf discory and enumerates serial ports. They are non-blocking so this can stay on one thread.

Connection manager runs on the main thread. It iterates through all known connectors and periodically
opens any that are not open. This is a candidate for threading, since opening connectors and
detecting the protocol can be a blocking operation.

The managed connection instance could be threaded. This means that for each detected device
there will be a thread to manage it. This is workable for a personal rpi but not for a public server.

Once the protocol has been detected, the thread could then move on to running the protocol loop.
If the protocol loop fails (such as I/O error.) then control returns to connection management.




"""
