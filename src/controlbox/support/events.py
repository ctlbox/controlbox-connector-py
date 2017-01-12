from queue import Queue


class EventSource(object):

    def __init__(self):
        self._handlers = []

    def __iadd__(self, handler):
        return self.add(handler)

    def __isub__(self, handler):
        return self.remove(handler)

    def add(self, handler):
        self._handlers.append(handler)
        return self

    def remove(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)
        return self

    def handlers(self):
        return tuple(self._handlers)

    def fire(self, *args, **kwargs):
        self._fire(*args, **kwargs)

    def fire_all(self, events):
        self._fire_all(events)

    def _fire_all(self, events):
        for e in events:
            self._fire(e)

    def _fire(self, *args, **kwargs):
        for handler in self._handlers:
            handler(*args, **kwargs)


class QueuedEventSource(EventSource):
    """
    the public fire() methods post events to the queue. These are fired when a thread
    calls publish()
    """
    def __init__(self):
        super().__init__()
        self.event_queue = Queue()

    def publish(self):
        """ publishes any queued events on the calling thread. """
        queue = self.event_queue
        if not queue.empty():
            events = []
            while not queue.empty():
                events.append(queue.get())
            self._fire_all(events)
