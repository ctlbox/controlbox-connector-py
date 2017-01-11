[![Build Status](https://travis-ci.org/m-mcgowan/controlbox-connect-py.svg?branch=master)](https://travis-ci.org/m-mcgowan/controlbox-connect-py) [![Coverage Status](https://coveralls.io/repos/github/m-mcgowan/controlbox-connect-py/badge.svg?branch=develop)](https://coveralls.io/github/m-mcgowan/controlbox-connect-py?branch=develop)

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

The controlbox connector provides a stack of interfaces at different levels
for communicating with objects running inside a controlbox container.

The application object (both in the controller and the remote proxy) are considered
the highest level

The next layer is the controlbox wrapper that provides the controlbox interface
to that object. This covers creating new instances (with a given configuration),
and reading/writing object state.

The controlbox framework uses all the registered controlbox wrappers to manage profiles,
and within each profile the objects that have been created.

Controller (Typically embedded, C++):

 - application API (not touched by controlbox)
 - application classes/objects (stateful)
 - controlbox adapter (may be the same instance as the app object, stateful or stateless)
 - controlbox framework - manages the controlbox objects, persistence, performs commands
   as instructed by the protocol
 - wire protocol: data bytes to wire format and message chunking
 - Conduit - send/receive raw bytes to an endpoint

     ↑   |
     |   |   Conduit
     |   |   (serial/TCP/stdio...)
     |   |
     |   ↓

 Connector (this repo, python):

 - Conduit - send/receive bytes
 - Wire protocol: wire format to data bytes and message chunking
 - asynchronous protocol: encodes/decodes controlbox commands/results to/from the wire
 - controlbox adapter - encodes/decodes application types
 - application proxy object (stateful) - [optional] an OO API to the application adapter
 - application API (all application functionality, no controlbox exposure)

## In the Controller

This is the endpoint where controlbox is implemented. Currently
controlbox is available as a C++ framework, but no reason it cannot be ported to other
languages.

### Application Object

This is a regular object owned and coded by the application developer in C/C++.
It implements the application functionality. The application functionality can be contained within this object,
or any other objects that this object instantiates.

### Controlbox Adapter

The controlbox adapter is responsible for:

- instantiating and configuring the application object from the object definition
- encoding object state to a byte stream when `read()` is called
- decoding the byte stream and updating the object state when `write()` is called.
- performing the necessary action when `udpate()` is called, such as invoking an application method.

The controlbox adapter can use any strategy as desired for obtaining and configuring the application object:

- controlbox adapter and application object are one and the same class, performing both functions
- controlbox adapter is a subclass of the application object
- controlbox adapter composes the application object directly as a member
- controlbox adapter instantiates the application object and holds a pointer to it
- controlbox adapter fetches the application object from a pool
- ...etc...


### Controlbox Framework

This layer is responsible for framing responses and data to be sent and reading framed commands
and data from the data stream and co-ordinating execution
of the requested command.

### Bytes <> Wire format

The data bytes making up the command + data are converted to the on-wire format.
The wire format is plain text, with each byte encoded as a hex pair, and optional annotations
encoded between square brackets.

### Conduit

This is a bi-directional stream of bytes, such as a serial port, TCP socket, stdio.
Data written by one end of the conduit is read by the other, and vice versa.

### Connector Wire <> Bytes format

Converts between the wire format and octets that make up the encoded commands and data.
This ignores annotations, and converts the hex pairs to single octets.

### Controlbox Protocol

Implements an asynchronous protocol driver. It pairs requests with responses,
and handles unsolicited responses from the controller.

When a method on the protocol object is called it is converted to a stream of data bytes and sent to the wire (which is
then further encoded to the wire format).

When the result is received it is decoded and converted to a value that is the result of the command.

It provides a low-level python interface that describes the controlbox protocol. Methods such as
`create_object` map directly to the protocol with only minimal encoding to make the syntax more convenient.

For example, `create object` has these parameters:
- the object ID chain (an iterable of numbers - this is converted to the chain-id list encoding in controlbox where the
   bit 7 is used to indicate if there is another item in the chain),
- the object type (a number)
- object configuration block (a byte array).

Application-specific types and instances do not feature at this level.


### Controlbox codec object

The controlbox codec object parallels the controlbox adapter in the controller.
It is responsible for interfacing between the controlbox representation (byte arrays) and application types. It
knows how to decode the data blocks that represent object state and configuration to application objects/properties.

### Controlbox Statless API

This provides an application-centric view of controlbox operations.
This raises the level of the python interface from byte buffers representing encoded object state
to python values that are meaningful to the application.
It uses the codecs to convert between application state and the encoded format.

The application state is lightweight in the sense that a value representing
object state or construction configuration does not have any form of reference to the remote
controlbox object. For example, reading the current time only returns the time. That value has no
connection to the time object on the controller, and only represents the state - the current time.

All commands to the controller are asynchronous and return a Future. The command can be made synchronous by calling `result(timeout=None)`
on the returned Future.

The application can add event listeners for events which are fired for all responses
received from the controller.

### Controlbox Stateful API

This builds on the exposes API, exposing the state and convenience operations that change state for application objects.
Rather than returning lightweight statless objets, the objects function like proxies. They have
methods that can directly interact with the controller, such as reading and writing state. It's an
object-oriented application API.

Each object maintains a reference to the remote object by maintaining the controlbox connector, the
id chain and the object type.

The API builds on the lightweight API, and binds the state for a given remote
object with a proxy that maintains the location of that object. Given a proxy object, the current
value is available via:

```
  proxy.value
```

And the latest value can be fetched via

```
    future = proxy.update
    future.value
```

Application specific methods may also be provided on the object,

```
    onewire = ...
    onewire.search_bus()
```

The application object can add additional functionality. For example,
the onewire bus could post device_added/removed events as it detects devices
coming and going on the bus.


## Application API

The top-level API provided by the application is decided by the application designer.
It may abstract all the controlbox details, providing an API that is application-centric,
and where controlbox is an implementation detail. The application
decides how controlbox concepts such as object IDs and types map to
application object location and type.

If the final interface is external to the process, such as a REST API
or a CLI, then the stateless API is probably simplest to use.

If the interface provides application objects for long running processes, then the
stateful API is most useful.



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


Todo - document the key distinction between the system space and user space:
The types of system objects and user objects come from the same namespace

System objects
- System objects typically pre-instantiated by the system and are always available
- system space is created and managed by the system. Only the system creates these objects and destroys them
- the system space is typically not persisted  (although this is an implementation detail - an app may choose
to persist object in custom storage, but the controlbox framework doesn't provide for that out the box.)
- The system container may optionally list the object definitions if the application
supports that.
- the framework provides for logging vales from the system container
- typically the same system objects are available regardless of which profile is loaded, although the application
may take steps to change system objects with the loaded profile if that is meaningful to the application.

User objects
- created by the application, either code on the controller or external code using the protocol
- created object definitions are persisted (todo, add a way to specifiy creation of a non-persisted object.)
- user objects are stored in a container associated with a profile. the system supports multiple configurations
via multiple profiles
- listing the object definitions is done by enumerating them in persistent storage
- the values of objects in the root or any other container can be logged


