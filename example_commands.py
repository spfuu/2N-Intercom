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
# to service.py within the EventService class.
# The repsonse is a requests.response (data as a dictionary).

response = ip_cam.commands.info()  # basic device information
response.raise_for_status()
print(response.text)

print(ip_cam.commands.status().text)  # current intercom status
print(ip_cam.commands.dial('**618').text)  # dial number

#  and many more
