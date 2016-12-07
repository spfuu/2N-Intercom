import datetime
import json
import logging
from error import raise_for_intercom_error
from service import EventService, CommandService

log = logging.getLogger(__name__)

class IPCam(object):

    def __init__(self, ip, ssl=False, auth_type=0, user=None, password=None):
        self.ip_address = ip
        self.user = user
        self.password = password
        self.auth_type = int(auth_type)  # 0: none, 1: basic, 2: digest
        self.ssl = ssl
        self.commands = CommandService(self)

        # get system time
        response = self.commands.status()

        # check for critical connection errors
        response.raise_for_status()

        # check for internal errors
        raise_for_intercom_error(response.text)

        status = json.loads(response.text)

        if 'systemTime' not in status['result']:
            raise Exception("Unknown intercom response: 'systemTime' missing.")

        # we just want to have current events
        event_register_time = datetime.datetime.utcfromtimestamp(status['result']['systemTime'])
        self.event = EventService(self, event_register_time)

