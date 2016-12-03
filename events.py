from http.server import BaseHTTPRequestHandler
import logging
from queue import Queue
import socket
import socketserver
import threading
from urllib.error import URLError
from urllib.request import urlopen
import time
import atexit
import requests
from datetime import datetime
import core

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

ns = {
    'event2n': 'http://www.2n.cz/2013/event',
    'wsnt': 'http://docs.oasis-open.org/wsn/b-2'
}

base_soap = \
    "<?xml version=\"1.0\" encoding=\"utf-8\"?>" \
    "<s:Envelope xmlns:s=\"http://www.w3.org/2003/05/soap-envelope\"" \
    "xmlns:wsnt=\"http://docs.oasis-open.org/wsn/b-2\"" \
    "xmlns:a=\"http://www.w3.org/2005/08/addressing\"" \
    "xmlns:event2n=\"http://www.2n.cz/2013/event\">" \
    "<s:Header>" \
    "{add_header}" \
    "</s:Header>" \
    "<s:Body>" \
    "{add_body}" \
    "</s:Body>" \
    "</s:Envelope>"


def parse_event(xml):

    """
    Parses the raw xml data to a event data dictionary.
    :param xml: xml data
    :return: event data as a dictionary.

    Example:
    {
        'data': {
            'callid': '1',
            'direction': 'Outgoing',
            'peer': 'sip:**611@192.168.178.1',
            'sessionid': '1',
            'state': 'Ringing'},
        'id': '7',
        'name': 'CallStateChanged',
        'timestamp': '2016-12-03 12:10:10'}
    """

    try:
        tree = XML.fromstring(xml)
    except Exception:
        log.warning("Unknown event response. Ignoring.")
        return

    event_dict = {}

    event_element = tree.find(".//event2n:EventName", ns)
    if event_element is None:
        return
    event_dict['name'] = event_element.text.strip('event2n:')

    element_id = tree.find(".//event2n:Id", ns)
    if element_id is not None:
        event_dict['id'] = element_id.text

    element_timestamp = tree.find(".//event2n:Timestamp", ns)
    if element_timestamp is not None:
        event_dict['timestamp'] = str(datetime.strptime(element_timestamp.text, "%Y-%m-%dT%H:%M:%SZ"))

    log.info("Event %s received for %s service on thread %s at %s",
             event_dict['name'], threading.current_thread(), event_dict['timestamp'])

    event_data = {}
    element_event_data = tree.find(".//event2n:Data", ns)
    if element_id is None:
        return
    # find children
    for child in element_event_data:
        # remove xml namespace
        if '}' in child.tag:
            tag_name = child.tag.split('}', 1)[1].lower()
            # get value
            event_data[tag_name] = child.text
    event_dict['data'] = event_data
    return event_dict

class EventNotifyHandler(BaseHTTPRequestHandler):
    """Handles HTTP ``NOTIFY`` Verbs sent to the listener server."""

    def do_POST(self):  # pylint: disable=invalid-name
        headers = requests.structures.CaseInsensitiveDict(self.headers)
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)

        if queue is not None:
            queue.put((parse_event(content)))

        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        # Divert standard webserver logging to the debug log
        log.debug(fmt, *args)

class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """A TCP server which handles each new request in a new thread."""
    allow_reuse_address = True

class EventServerThread(threading.Thread):
    """The thread in which the event listener server will run."""

    def __init__(self, address):
        """
        Args:
            address (tuple): The (ip, port) address on which the server
                should listen.
        """
        super(EventServerThread, self).__init__()
        #: `threading.Event`: Used to signal that the server should stop.
        self.stop_flag = threading.Event()
        #: `tuple`: The (ip, port) address on which the server is
        #: configured to listen.
        self.address = address

    def run(self):
        """Start the server on the local IP at port 1400 (default).

        Handling of requests is delegated to an instance of the
        `EventNotifyHandler` class.
        """
        listener = EventServer(self.address, EventNotifyHandler)
        log.info("Event listener running on %s", listener.server_address)
        # Listen for events until told to stop
        while not self.stop_flag.is_set():
            listener.handle_request()

class EventListener(object):
    def __init__(self):
        super(EventListener, self).__init__()
        #: `bool`: Indicates whether the server is currently running
        self.is_running = False
        self._start_lock = threading.Lock()
        self._listener_thread = None

    def start(self, listener_ip, listener_port):
        """Start the event listener listening on the local machine
        Make sure that your firewall allows connections to this port
        """
        with self._start_lock:
            if not self.is_running:
                # Start the event listener server in a separate thread.
                self.address = (listener_ip, listener_port)
                self._listener_thread = EventServerThread(self.address)
                self._listener_thread.daemon = True
                self._listener_thread.start()
                self.is_running = True
                log.info("Event listener started")

    def stop(self):
        """Stop the event listener."""
        # Signal the thread to stop before handling the next request
        self._listener_thread.stop_flag.set()
        # Send a dummy request in case the http server is currently listening
        try:
            urlopen('http://%s:%s/' % (self.address[0], self.address[1]))
        except URLError:
            # If the server is already shut down, we receive a socket error,
            # which we ignore.
            pass
        # wait for the thread to finish
        self._listener_thread.join()
        self.is_running = False
        log.info("Event listener stopped")


class Subscription(object):
    def __init__(self, service, event_queue=None):
        """
        Args:
            service (Service): The SoCo `Service` to which the subscription
                 should be made.
            event_queue (:class:`~queue.Queue`): A queue on which received
                events will be put. If not specified, a queue will be
                created and used.
        """
        super(Subscription, self).__init__()
        global queue
        self.service = service
        #: `str`: A unique ID for this subscription
        self.sid = None
        #: `int`: The amount of time in seconds until the subscription expires.
        self.timeout = None
        #: `bool`: An indication of whether the subscription is subscribed.
        self.is_subscribed = False
        #: :class:`~queue.Queue`: The queue on which events are placed.
        self.events = Queue() if event_queue is None else event_queue
        queue = self.events
        #: `int`: The period (seconds) for which the subscription is requested
        self.requested_timeout = None
        # A flag to make sure that an unsubscribed instance is not
        # resubscribed
        self._has_been_unsubscribed = False
        # The time when the subscription was made
        self._timestamp = None
        # Used to keep track of the auto_renew thread
        self._auto_renew_thread = None
        self._auto_renew_thread_flag = threading.Event()

        self._default_subscription_timeout = 600
        self.default_listener_port = 19000
        self._listener_port = self.default_listener_port
        self._listener_ip = core.get_lan_ip()

    def subscribe(self, requested_timeout=None, auto_renew=False, listener_ip=None, listener_port=None):
        """Subscribe to the service.

        If requested_timeout is provided, a subscription valid for that number
        of seconds will be requested, but not guaranteed. Check
        `timeout` on return to find out what period of validity is
        actually allocated.

        Args:
            requested_timeout(int, optional): The timeout to be requested. Default: 600
            auto_renew (bool, optional): If `True`, renew the subscription
                automatically shortly before timeout. Default `False`.
            listener_ip (str, optional): listener ip to handle events. Default: guessing local ip in the network
            listener_port (int, optional): listener port. Default: 19000
        """

        class AutoRenewThread(threading.Thread):
            """Used by the auto_renew code to renew a subscription from within
            a thread.

            """

            def __init__(self, interval, stop_flag, sub, *args, **kwargs):
                super(AutoRenewThread, self).__init__(*args, **kwargs)
                self.interval = interval
                self.sub = sub
                self.stop_flag = stop_flag
                self.daemon = True

            def run(self):
                sub = self.sub
                stop_flag = self.stop_flag
                interval = self.interval
                while not stop_flag.wait(interval):
                    log.info("Autorenewing subscription %s", sub.sid)
                    sub.renew()

        if listener_port is not None:
            self._listener_port = listener_port
            if self._listener_port not in range(1, 65536):
                log.warning("Port must be in a int between 1-65535. Using default port {port}.".format(
                    port=self.default_listener_port
                ))
                self._listener_port = self.default_listener_port

        if listener_ip is not None:
            # check for valid ip address
            try:
                socket.inet_aton(listener_ip)
            except socket.error:
                log.warning("Invalid listener IP. Using local IP {ip}.".format(ip=self._listener_ip))
            self._listener_ip = listener_ip

        self.requested_timeout = requested_timeout
        if self._has_been_unsubscribed:
            raise Exception('Cannot resubscribe instance once unsubscribed')
        # The event listener must be running, so start it if not
        if not event_listener.is_running:
            event_listener.start(self._listener_ip, self._listener_port)

        sub_timout = self._default_subscription_timeout
        if requested_timeout is not None:
            sub_timout = requested_timeout
        subscription_timeout = "PDT{timeout}S".format(timeout=sub_timout)

        headers = {
            'Content-Type': 'application/soap+xml'
        }

        add_header = ""
        add_body = "<wsnt:Subscribe>" \
                   "<wsnt:ConsumerReference>" \
                   "<a:Address>" \
                   "http://{IP}:{PORT}/" \
                   "</a:Address>" \
                   "</wsnt:ConsumerReference>" \
                   "<wsnt:Filter>" \
                   "<wsnt:TopicExpression Dialect=\"http://www.2n.cz/2013/TopicExpression/Multiple\">" \
                   "{EVENTS_LIST}" \
                   "</wsnt:TopicExpression>" \
                   "</wsnt:Filter>" \
                   "<wsnt:InitialTerminationTime>" \
                   "{DATETIME_OR_DURATION}" \
                   "</wsnt:InitialTerminationTime>" \
                   "<wsnt:SubscriptionPolicy>" \
                   "<event2n:MaximumNumber>" \
                   "{MAX_NUMBER_OF_MSGS_AT_ONCE}" \
                   "</event2n:MaximumNumber>" \
                   "<event2n:StartRecordId>" \
                   "{START_RECORD_ID}" \
                   "</event2n:StartRecordId>" \
                   "<event2n:StartTimestamp>" \
                   "{START_TIMESTAMP}" \
                   "</event2n:StartTimestamp>" \
                   "</wsnt:SubscriptionPolicy>" \
                   "</wsnt:Subscribe>"

        add_body = add_body.format(
            IP=self._listener_ip,
            PORT=self._listener_port,
            DATETIME_OR_DURATION=subscription_timeout,
            EVENTS_LIST="",
            MAX_NUMBER_OF_MSGS_AT_ONCE="",
            START_TIMESTAMP="2016-11-29T10:18:59Z",
            START_RECORD_ID=""
        )

        payload = base_soap.format(add_header=add_header, add_body=add_body)

        response = requests.request('POST', self.service.base_url + self.service.event_url,
                                    headers=headers, data=payload, verify=False)
        response.raise_for_status()
        tree = XML.fromstring(response.text)

        # property values are just under the propertyset, which
        # uses this namespace
        subscription_element = tree.find(".//event2n:SubscriptionId", ns)

        if subscription_element is None:
            raise Exception("Could not find subscription id in subscription response.")
        self.sid = subscription_element.text

        current_time_element = tree.find(".//wsnt:CurrentTime", ns)
        if current_time_element is None:
            raise Exception("Could not find current time in subscription response.")
        current_time = current_time_element.text

        term_time_element = tree.find(".//wsnt:TerminationTime", ns)
        if term_time_element is None:
            raise Exception("Could not find termination time in subscription response.")
        term_time = term_time_element.text

        ctime = datetime.strptime(current_time, "%Y-%m-%dT%H:%M:%SZ")
        ttime = datetime.strptime(term_time, "%Y-%m-%dT%H:%M:%SZ")
        self.timeout = (ttime - ctime).seconds
        # datetime to time.time()
        self._timestamp = time.time()
        self.is_subscribed = True
        log.info("Subscribed to %s, sid: %s", self.service.base_url + self.service.event_url, self.sid)

        # Register this subscription to be unsubscribed at exit if still alive
        # This will not happen if exit is abnormal (eg in response to a
        # signal or fatal interpreter error - see the docs for `atexit`).
        atexit.register(self.unsubscribe)

        # Set up auto_renew
        if not auto_renew:
            return
        # Autorenew just before expiry, say at 85% of self.timeout seconds
        interval = self.timeout * 85 / 100
        auto_renew_thread = AutoRenewThread(
            interval, self._auto_renew_thread_flag, self)
        auto_renew_thread.start()

    def renew(self, requested_timeout=None):
        """Renew the event subscription.

        You should not try to renew a subscription which has been
        unsubscribed, or once it has expired.

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made. If None (the default), use the timeout
                requested on subscription.
        """
        # NB This code is sometimes called from a separate thread (when
        # subscriptions are auto-renewed. Be careful to ensure thread-safety

        if self._has_been_unsubscribed:
            raise Exception(
                'Cannot renew subscription once unsubscribed')
        if not self.is_subscribed:
            raise Exception(
                'Cannot renew subscription before subscribing')
        if self.time_left == 0:
            raise Exception(
                'Cannot renew subscription after expiry')

        add_header = "<event2n:SubscriptionId a:IsReferenceParameter=\"true\">" \
                     "{SUBSCRIPTION_ID}" \
                     "</event2n:SubscriptionId>"
        add_body = "<wsnt:Renew>" \
                   "<wsnt:TerminationTime>" \
                   "{DATETIME_OR_DURATION}" \
                   "</wsnt:TerminationTime>" \
                   "</wsnt:Renew>"

        sub_timout = self._default_subscription_timeout
        if requested_timeout is not None:
            sub_timout = requested_timeout
        subscription_timeout = "PDT{timeout}S".format(timeout=sub_timout)

        headers = {
            'Content-Type': 'application/soap+xml'
        }

        add_header = add_header.format(SUBSCRIPTION_ID=self.sid)
        add_body = add_body.format(DATETIME_OR_DURATION=subscription_timeout)

        payload = base_soap.format(add_header=add_header, add_body=add_body)
        response = requests.request('POST', self.service.base_url + self.service.event_url,
                                    headers=headers, data=payload, verify=False)

        response.raise_for_status()

        tree = XML.fromstring(response.text)

        current_time_element = tree.find(".//wsnt:CurrentTime", ns)
        if current_time_element is None:
            raise Exception("Could not find current time in subscription response.")
        current_time = current_time_element.text

        term_time_element = tree.find(".//wsnt:TerminationTime", ns)
        if term_time_element is None:
            raise Exception("Could not find termination time in subscription response.")
        term_time = term_time_element.text

        ctime = datetime.strptime(current_time, "%Y-%m-%dT%H:%M:%SZ")
        ttime = datetime.strptime(term_time, "%Y-%m-%dT%H:%M:%SZ")

        self.timeout = (ttime - ctime).seconds
        # datetime to time.time()
        self._timestamp = time.time()

        self.is_subscribed = True
        log.info("Renewed subscription to %s, sid: %s", self.service.base_url + self.service.event_url, self.sid)

    def unsubscribe(self):
        """Unsubscribe from the service's events.

        Once unsubscribed, a Subscription instance should not be reused
        """
        # Trying to unsubscribe if already unsubscribed, or not yet
        # subscribed, fails silently
        if self._has_been_unsubscribed or not self.is_subscribed:
            return

        # Cancel any auto renew
        self._auto_renew_thread_flag.set()
        headers = {
            'Content-Type': 'application/soap+xml'
        }

        add_header = "<event2n:SubscriptionId a:IsReferenceParameter=\"true\">" \
                     "{SUBSCRIPTION_ID}" \
                     "</event2n:SubscriptionId>"

        add_body = "<wsnt:Unsubscribe></wsnt:Unsubscribe>"

        add_header = add_header.format(
            SUBSCRIPTION_ID=self.sid
        )

        payload = base_soap.format(add_header=add_header, add_body=add_body)
        response = requests.request('POST', self.service.base_url + self.service.event_url,
                                    headers=headers, data=payload, verify=False)
        response.raise_for_status()
        self.is_subscribed = False
        self._timestamp = None
        log.info("Unsubscribed from %s, sid: %s", self.service.base_url + self.service.event_url, self.sid)
        self._has_been_unsubscribed = True
        event_listener.stop()

    @property
    def time_left(self):
        """
        `int`: The amount of time left until the subscription expires (seconds)

        If the subscription is unsubscribed (or not yet subscribed),
        `time_left` is 0.
        """
        if self._timestamp is None:
            return 0
        else:
            time_left = self.timeout - (time.time() - self._timestamp)
            return time_left if time_left > 0 else 0

event_listener = EventListener()
