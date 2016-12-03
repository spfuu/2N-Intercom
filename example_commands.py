from core import IPCam

'''
This example demonstrates some commands. Please change IP, username and password and (optional)
authentication method and.
Check your IP-Com settings to get the correct values.
'''

username = 'testuser'
password = 'testpassword'
ip = '192.168.0.1'
ssl = True
auth_type = 2 # 0=None, 1=Basic, 2=Digest


ip_cam = IPCam(ip, ssl=ssl, auth_type=2, user=username, password=password)

# for the comple list of commands anf their description please take a look to service.py within the EventService class.

ip_cam.commands.info()  # basic device information
ip_cam.commands.status()  # current intercom status
ip_cam.commands.dial('**618') # dial number
