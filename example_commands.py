import json
from time import sleep
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from core import IPCam

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


'''
This example demonstrates some commands. Please change IP, username and password and (optional)
authentication method and.
Check your IP-Com settings to get the correct values.
'''

username = 'test'
password = 'testpassword'
ip = '192.168.0.2'
ssl = True
auth_type = 2  # 0=None, 1=Basic, 2=Digest

ip_cam = IPCam(ip, ssl=ssl, auth_type=2, user=username, password=password)

# For the complete list of commands anf their description please take a look
# to commands.py within the CommandService class.

print(ip_cam.commands.info())  # basic device information
print(ip_cam.commands.status())  # current intercom status
print(ip_cam.commands.dial('**618'))  # dial number


# this is an example implementation for an event listener (for all events) with an auto-renewing subscription

sid = None
event_timeout = 120

while True:
    try:
        if sid is None:
            # subscribe to pull channel
            # since the channel is extended automatically by accessing it with a pull requests,
            # we just have to make sure, the subscription timeout value is a bit higher than the timeout value
            data = json.loads(ip_cam.commands.log_subscribe(duration=event_timeout + 10))

            if 'success' not in data:
                raise Exception('Invalid subscription response: {err}'.format(err=data))
            if not data['success']:
                raise Exception('{err}'.format(err=data))

            if 'id' in data['result']:
                sid = data['result']['id']
                print('2n: sid={id}'.format(id=sid))
        if sid is not None:
            print(ip_cam.commands.log_pull(sid, timeout=event_timeout+10))
        else:
            raise Exception("no sid")
    except Exception as err:
        print("2N:" + str(err))
        sid = None
        sec = 20
        print("2N: retrying in {sec} seconds".format(sec=sec))
        sleep(sec)
    except KeyboardInterrupt:
        ip_cam.commands.log_unsubscribe(id)
        break
