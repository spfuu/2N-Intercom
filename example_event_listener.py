from pprint import pprint
from queue import Empty
import signal
from core import IPCam

'''
This example demonstrates a event listener implementation. Please change IP, username and password and (optional)
authentication method and.
Check your IP-Com settings to get the correct values.
'''

username = 'testuser'
password = 'testpassword'
ip = '192.168.0.1'
ssl = True
auth_type = 2 # 0=None, 1=Basic, 2=Digest


def stop(*args):
    sub.unsubscribe()
    exit()

ip_cam = IPCam(ip, ssl=ssl, auth_type=2, user=username, password=password)

sub = ip_cam.event.subscribe(requested_timeout=600, auto_renew=True, listener_port=19000)

# ############################################################
# Signal Handling
# ############################################################

signal.signal(signal.SIGHUP, stop)
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

ip_cam.commands.log_pull(sub.sid)

while True:
    try:
        event = sub.events.get(timeout=0.5)

        ''' event dictionary example:

        {
            'data': {
                'callid': '1',
                'direction': 'Outgoing',
                'peer': 'sip:**618@192.168.0.1',
                'sessionid': '1',
                'state': 'Ringing'},
            'id': '7',
            'name': 'CallStateChanged',
            'timestamp': '2016-12-03 12:10:10'
        }

        '''

        pprint(event)
    except Empty:
        pass
    except KeyboardInterrupt:
        break