# controlbox-py
API to the objects running in a controlbox microcontainer on an embedded device, implemented in Python.


## Installing

OSX needs

```
export ARCHFLAGS="-arch x86_64"
export CC=gcc
```

defined before installing sphinx-autodoc. 

## Architecture

The connector provides proxy objects that correspond to
objects running inside an embedded container.

Controller (Typically embedded, C++):

 - application object (stateful)
 - controlbox object (stateful - maybe the same instance as the app object)
 - protocol driver (encodes to the protocol format/decodes from protocol format.)
 - protocol bytes to wire format
 - Conduit - send/receive bytes

     ↑   |
     |   |
     |   |   (serial/TCP/stdIO...)
     |   |
     |   ↓

 - Conduit - send/receive bytes

 Connector (this repo, python):

  - wire format to bytes
  - protocol driver
  - controlbox bridge (stateless)
  - application proxy object (stateful) - [optional]


### Application Object

This is a regular object owned and coded by the application developer. It implements the application
functionality. The application functionality can be contained within this object, or any other objects
that this object instantiates.

### Controlbox Object

The controlbox object is responsible for:

- instantiating and configuring the application object from the object definition
- encoding object state to a byte stream when `read()` is called
- decoding the byte stream and updating the object state when `write()` is called.
- performing the necessary action when `udpate()` is called, such as invoking an application method.

The controlbox object can use any strategy as desired for obtaining and configuring the application object:

- controlbox object and application object are one and the same class, performing both functions
- controlbox object is a subclass of the application object
- controlbox object composes the application object directly as a member
- controlbox object instantiates the application object and holds a pointer to it
- controlbox object fetches the application object from a pool
- ...etc...


### Protocol Driver

This class is responsible for framing commands and data to be sent and reading framed commands
and data from the data stream.

### Bytes <> Wire format

The data bytes making up the command + data are converted to the on-wire format.

### Conduit

This is a bi-directional stream of bytes, such as a serial port, TCP socket, stdio.
Data written by the controller is read by the connector, and vice versa.

### Connector Wire <> Bytes format

Converts between the wire format and octets that make up the encoded commands and data.

### Connector Protocol Driver

Implements an asynchronous protocol manager. It pairs requests with responses,
and handles unsolicited responses from the controller.

When a method on the protocol object is called it is converted to a stream of data bytes and sent over the conduit.
When the result is received it is decoded and converted to a value that is the result of the command.

### Controlbox codec object

The controlbox codec object parallels the controlbox object in the controller.
It is responsible for interfacing between the protocol data and application objects. It
knows how to decode the data blocks send from the controller to application objects/properties.

### Application Proxy Object

This exposes the state and convenience operations that change state for application objects.


## Container Hierarchy

The container hierarchy on the connector mirrors the container hierarchy on the controller.
The root container provides object enumeration and the ability to add/delete objects.

The level of the API is that applications work with application objects. For example,

```
   root = ...  # root container
   time = ScaledTime()
   proxy = root.add(time)

```
The time object is stored in the container, and the controlbox object for the application object returned.

The controlbox object manages updating the application object state from information provided from the controller.

As with the controller, the connector may chose to combine the controlbox and application functionality in one class.
Or they may be separate. This is just a matter of whether separation is beneficial/needed or not.

When the controller is first connected to a root proxy container, the objects already present in the
controller are read and proxies created for them.

- for each object type, there is a registration of the corresponding controlbox object.
- the controlbox object can instantiate the application object from the object definition bytes
- the controlbox object can update the application object from the object state bytes. When the application object
is updated, events may be fired.
- changes to the application object happen via properties/methods (encapsulated) - the application object delegates
to the controlbox object to make the change. The controlbox object determines the write request needed to affect the change.
The request may require a mask to be set if only some of the state is updated.

When the client enumerates objects in a proxy container, what is returned - the controlbox object or the application object?
Probably makes sense to return the applicatino object. If the proxy is required, the container can provide
that on request (or it's added dynamically to the application object.)


serivce layer is source of truth

Contstructing
 - application fires an object created events which represents the object and the construction parameters
  - e.g. a dict containing construction values and the application id of the object
 - controlbox bridge layer listens for that event (by registering as a listener to the application layer), and propagates this to controlbox

Uppdates from Controller
 - the controlbox bridge fires an application defined event to subscribers on an app object
 - application takes care of subscribing to the event and managing the update

Changes to app state (from elsewhere in the system)
- app classes fires a changed event describing the change (such as a dictionary of changed fields and the id of the object)
- controlbox bridge listens for that, and propagates the change to controlbox via a masked write

Deleting
- application fires an object deleted event with at least the application defined ID for the object that corresponds to the construction event
- controlbox bridge listens for that, locates the corresponding object and issues a delete request to controlbox


Application objects for the controller:
- e.g. controller, temperature sensors, PIDs actuators, profile, profile executor
- these are instantiated by the service layer:
  - a controller enumerator.
    - fires connected/disconnected events and the global ID of the controller.
    - may need to assign an ID for controller types that don't have a unique ID.
    - enumerates connected controllers from various sources
    - serial:
     - uses support code in the connector to scan serial busses
     - keeps track of which busses are already connected and in use by the system
     - free busses are "sniffed" to determine if they are a controller
      - real controllers are inspected retrieving their ID.
     - fires events for controller connected/disconnected as controllers are connected/disconnected
    - wifi:
     - zero conf/tcp server etc..
     - when a controller is identified, controller connected event is fired.
   - a controller manager listens for connected/disconnected events from the controller enumerator
     - on connected, the manager looks for a persisted controller instance matching the ID of the connected hardware
      - if one is found, then the application Controller object is passed a reference to the
         controlbox instance.
      - if one is not found, then "new controller detected" event is fired.
      - if one is found, a "controller connected" event is fired.

By arranging it like this, we keep the application in sync with the connected controllers.

Resynching the application and controller
