from core import IPCam

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

# subscribe for pulling events from Intercom
data = ip_cam.commands.log_subscribe()
id = data['id']

while True:
    try:
        result = ip_cam.commands.log_pull(id)
        print(result)
    except KeyboardInterrupt:
        ip_cam.commands.log_unsubscribe(id)
        break
