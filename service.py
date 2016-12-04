import logging
from events import Subscription
import os
from urllib.parse import urljoin
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import error
from requests import Request, Session

log = logging.getLogger(__name__)

class send_command(object):
    def __init__(self, func):
        self.func = func
        self.func_name = func.__name__

    def __get__(self, instance, owner):
        self.cls = owner
        self.obj = instance
        return self.__call__

    def __call__(self, *args, **kwargs):
        command = self.func.__call__(self, *args, **kwargs)
        prepared_request = self.__prepare_request(command)
        # pass it to requests.Session object
        prepared_request = self.obj._session.prepare_request(prepared_request)

        stream = False
        if 'stream' in command:
            if command['stream'] in ['1', True]:
                stream = True
        return self.obj._session.send(prepared_request, verify=False, timeout=60, proxies=None, stream=stream)

    def __prepare_request(self, command):
        """
        Prepare HTTP-API request
        :param command:
        :return: requests.Request
        :raise error.InvalidCommandError:
        """

        if 'method' not in command:
            raise error.InvalidCommandError("No 'method' key for command '{name}.".format(name=self.func_name))

        method = command['method'].upper()
        if method not in ['GET', 'PUT', 'POST', 'DELETE']:
            raise error.InvalidCommandError("Invalid method '{method}' for command '{name}.".format(
                method=method, name=self.func_name))

        if 'call' not in command:
            raise error.InvalidCommandError("No 'call' key for command '{name}.".format(name=self.func_name))

        call = command['call']

        payload = None
        if method == 'POST':
            if 'parameter' in command:
                # remove keys with empty values
                payload = {i: j for i, j in command['parameter'].items() if j is not None}
        auth = None

        if self.obj.ip_cam.auth_type == 1:
            auth = HTTPBasicAuth(self.obj.ip_cam.user, self.obj.ip_cam.password)
        if self.obj.ip_cam.auth_type == 2:
            auth = HTTPDigestAuth(self.obj.ip_cam.user, self.obj.ip_cam.password)

        if auth:
            if not self.obj.ip_cam.user or not self.obj.ip_cam.password:
                print("Authentication method set with empty user and/or password. Fallback to non-auth.")
                auth = None

        if method == 'PUT':
            if 'filename' not in command:
                raise error.InvalidCommandError("No 'filename' key for command '{name}.".format(name=self.func_name))
            filename = os.path.realpath(command['filename'])
            if not os.path.exists(filename):
                raise Exception("File '{file}' not found-".format(file=filename))

            if 'name' not in command:
                raise error.InvalidCommandError("No 'name' key for command '{name}.".format(name=self.func_name))

            return Request(
                method=method,
                url=urljoin(self.obj.ip_cam.commands.base_url, call),
                files={command['name']: (os.path.basename(filename), open(filename, 'rb'), 'application/octet-stream')},
                auth=auth
            )

        return Request(
            method=method,
            url=urljoin(self.obj.ip_cam.commands.base_url, call),
            data=payload,
            auth=auth
        )

class Service(object):
    def __init__(self, ip_cam):
        self.ip_cam = ip_cam
        #: str: The UPnP service type.
        self.service_type = self.__class__.__name__
        #: str: The UPnP service version.
        self.version = 1
        self.service_id = self.service_type
        #: str: The base URL for sending UPnP Actions.

        schema = 'http'
        if self.ip_cam.ssl:
            schema = 'https'
        self.base_url = "{schema}://{ip}".format(schema=schema, ip=self.ip_cam.ip_address)

    def subscribe(self, requested_timeout=None, auto_renew=False, listener_ip=None, listener_port=None):
        """Subscribe to the service's events.
        Args:
            requested_timeout (int, optional): If requested_timeout is
                provided, a subscription valid for that
                number of seconds will be requested, but not guaranteed. Check
                `Subscription.timeout` on return to find out what period of
                validity is actually allocated. Default: 600 seconds
            auto_renew (bool): If auto_renew is `True`, the subscription will
                automatically be renewed just before it expires, if possible.
                Default is `False`.
            event_queue (:class:`~queue.Queue`): a thread-safe queue object on
                which received events will be put. If not specified,
                a (:class:`~queue.Queue`) will be created and used.
        Returns:
            `Subscription`: an insance of `Subscription`, representing
                the new subscription.
        To unsubscribe, call the `unsubscribe` method on the returned object.
        """
        subscription = Subscription(self)
        subscription.subscribe(requested_timeout=requested_timeout,
                               auto_renew=auto_renew,
                               listener_ip=listener_ip,
                               listener_port=listener_port)
        return subscription

    def __getattr__(self, action):
        """Called when a method on the instance cannot be found.

        Causes an action to be sent to UPnP server. See also
        `object.__getattr__`.

        Args:
            action (str): The name of the unknown method.
        Returns:
            callable: The callable to be invoked. .
        """

        # Define a function to be invoked as the method, which calls
        # send_command.
        def _dispatcher(self, *args, **kwargs):
            """Dispatch to send_command."""
            return self.send_command(action, *args, **kwargs)

        # rename the function so it appears to be the called method. We
        # probably don't need this, but it doesn't harm
        _dispatcher.__name__ = action

        # _dispatcher is now an unbound menthod, but we need a bound method.
        # This turns an unbound method into a bound method (i.e. one that
        # takes self - an instance of the class - as the first parameter)
        # pylint: disable=no-member
        method = _dispatcher.__get__(self, self.__class__)
        # Now we have a bound method, we cache it on this instance, so that
        # next time we don't have to go through this again
        setattr(self, action, method)
        log.debug("Dispatching method %s", action)

        # return our new bound method, which will be called by Python
        return method

class CommandService(Service):
    def __init__(self, ip_cam):
        super(CommandService, self).__init__(ip_cam)
        self._session = Session()

    @send_command
    def info(self):
        """
        The /api/system/info function provides basic information on the device: type, serial
        number, firmware version, etc. The function is available in all device types regardless
        of the set access rights.
        :return: The reply is in the application/json format.

        Example:
        GET /api/system/info
        {
            "success" : true,
            "result" : {
            "variant" : "2N Helios IP Vario",
            "serialNumber" : "08-1860-0035",
            "hwVersion" : "535v1",
            "swVersion" : "2.10.0.19.2",
            "buildType" : "beta",
            "deviceName" : "2N Helios IP Vario"
            }
        }

        variant: Model name (version)
        SerialNumber: Serial number
        hwVersion: Hardware version
        swVersion: Firmware version
        buildType: Firmware build type (alpha, beta, or empty value for official versions)
        deviceName: Device name set in the configuration interface on the Services / Web Server tab

        """
        return {
            'method': 'get',
            'call': '/api/system/info',
            'parameter': {},
        }

    @send_command
    def status(self):
        """
        The /api/system/status function returns the current intercom status.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only.

        :return: The reply is in the application/json format and includes the current device status.

        Example:
        GET /api/system/status
        {
            "success" : true,
            "result" : {
            "systemTime" : 1418225091,
            "upTime" : 190524
            }
        }

        systemTime: Device real time in seconds since 00:00 1.1.1970 (unix time)
        upTime: Device operation time since the last restart in seconds
        """
        return {
            'method': 'get',
            'call': '/api/system/status',
            'parameter': {},
        }

    @send_command
    def restart(self):
        """
        The /api/system/restart restarts the intercom.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only .

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        GET /api/system/restart
        {
            "success" : true
        }

        """
        return {
            'method': 'get',
            'call': '/api/system/restart',
            'parameter': {},
        }

    @send_command
    def upload_firmware(self, filename):
        """
        The /api/firmware function helps you upload a new firmware version to the device.
        When the upload is complete, use /api/firmware/apply to confirm restart and FW change.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :type filename: firmware file to upload
        :return: The reply is in the application/json format.

        Example:
        PUT /api/firmware
        {
            "success" : true,
            "result" : {
            "version" : "2.10.0.19.2",
            "downgrade" : false
            }
        }

        version: Firmware version to be uploaded
        downgrade: Flag set if the FW to be uploaded is older than the current one

        If the FW file to be uploaded is corrupted or not intended for your device, the intercom
        returns error code 12 – invalid parameter value.
        """
        return {
            'method': 'put',
            'call': '/api/firmware',
            'name': 'blob-fw',
            'filename': filename
        }

    @send_command
    def apply_firmware(self):
        """
        The /api/firmware/apply function is used for earlier firmware upload ( PUT
        /api/firmware ) confirmation and subsequent device restart.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only.

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        GET /api/firmware/apply
        {
            "success" : true
        }
        """
        return {
            'method': 'get',
            'call': '/api/firmware/apply',
            'parameter': {},
        }

    @send_command
    def get_config(self):
        """
        The /api/config function helps you to download the device configuration.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :return: For configuration download, the reply is in the application/xml format and contains a
        complete device configuration file.

        Example:
        GET /api/config
        <?xml version="1.0" encoding="UTF-8"?>
        <!--
            Product name: 2N Helios IP Vario
            Serial number: 08-1860-0035
            Software version: 2.10.0.19.2
            Hardware version: 535v1
            Bootloader version: 2.10.0.19.1
            Display: No
            Card reader: No
        -->
        <DeviceDatabase Version="4">
        <Network>
        <DhcpEnabled>1</DhcpEnabled>
        ...
        ...

        """
        return {
            'method': 'get',
            'call': '/api/config',
            'parameter': {},
        }

    @send_command
    def upload_config(self, filename):
        """
        The /api/config function helps you to upload the device configuration.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :type filename: config file to upload (xml)
        :return: The reply is in the application/json format and includes no other parameters.

        Example:
        PUT /api/config
        {
            "success" : true
        }
        """
        return {
            'method': 'put',
            'call': '/api/config',
            'name': 'blob-cfg',
            'filename': filename,
        }

    @send_command
    def factory_reset(self):
        """
        The /api/config/factoryreset function resets the factory default values for all the
        intercom parameters. This function is equivalent to the function of the same name in
        the System / Maintenance / Default setting section of the configuration web interface .

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only.

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        GET /api/config/factoryreset
        {
            "success" : true
        }
        """
        return {
            'method': 'get',
            'call': '/api/config/factoryreset',
            'parameter': {},
        }

    @send_command
    def switch_caps(self):
        """
        The /api/switch/caps function returns the current switch settings and control
        options. Define the switch in the optional switch parameter. If the switch parameter
        is not included, settings of all the switches are returned.

        The function is part of the Switch service and the user must be assigned the Switch
        Monitoring privilege for authentication if required . The function is available with the Enhanced Integration
        licence key only.

        :return: The reply is in the application/json format and includes a switch list ( switches )
        including current settings. If the switch parameter is used, the switches field includes
        just one item.

        Example:
        GET /api/switch/caps
        {
            "success" : true,
            "result" : {
                "switches" : [
                {
                    "switch" : 1,
                    "enabled" : true,
                    "mode" : "monostable",
                    "switchOnDuration" : 5,
                    "type" : "normal"
                },
                {
                    "switch" : 2,
                    "enabled" : true,
                    "mode" : "monostable",
                    "switchOnDuration" : 5,
                    "type" : "normal"
                },
                {
                    "switch" : 3,
                    "enabled" : false
                },
                {
                    "switch" : 4,
                    "enabled" : false
                }]
            }
        }

        switch: Switch Id (1 to 4)
        enabled: Switch control enabled in the configuration web interface
        mode: Selected switch mode ( monostable , bistable )
        switchOnDuration: Switch activation time in seconds (for monostable mode only)
        type: Switch type ( normal , security )

        """
        return {
            'method': 'get',
            'call': '/api/switch/caps',
            'parameter': {},
        }

    @send_command
    def switch_status(self, switch=None):
        """
        The /api/switch/status function returns the current switch statuses.

        The function is part of the Switch service and the user must be assigned the Switch
        Monitoring privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only.

        :type switch: Optional switch parameter. If the switch parameter is not included,
        states of all the switches are returned.
        :return: The reply is in the application/json format and includes a switch list (switches)
        including current statuses ( active) . If the switch parameter is used, the switches field
        includes just one item.

        Example:
        POST /api/switch/status
        {
            "success" : true,
            "result" : {
                "switches" : [
                {
                    "switch" : 1,
                    "active" : false
                },
                {
                    "switch" : 2,
                    "active" : false
                },
                {
                    "switch" : 3,
                    "active" : false
                },
                {
                    "switch" : 4,
                    "active" : false
                }]
            }
        }
        """

        return {
            'method': 'POST',
            'call': '/api/switch/status',
            'parameter': {
                'switch': switch
            },
        }

    @send_command
    def switch_control(self, switch, action, response=None):
        """
        The /api/switch/ctrl function controls the switch statuses. The function has two
        mandatory parameters: switch , which determines the switch to be controlled, and
        action , defining the action to be executed over the switch (activation, deactivation,
        state change).

        The function is part of the Switch service and the user must be assigned the Switch
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :param switch: Mandatory switch identifier (typically, 1 to 4). Use also/api/switch/caps
        to know the exact count of switches .
        :param action: Mandatory action defining parameter ( on – activate switch, off – deactivate switch,
        trigger – change switch state).
        :param response: Optional parameter modifying the intercom response to include the text
        defined here instead of the JSON message.
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/switch/ctrl
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/switch/ctrl',
            'parameter': {
                'switch': switch,
                'action': action,
                'response': response
            }
        }

    @send_command
    def io_caps(self, port=None):
        """
        The /api/io/caps function returns a list of available hardware inputs and outputs
        (ports) of the device. Define the input/output in the optional port parameter. If the
        port parameter is not included, settings of all the inputs and outputs are returned .

        The function is part of the I/O service and the user must be assigned the I/O
        Monitoring privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :param port: Optional input/output identifier
        :return: The reply is in the application/json format and includes a port list (ports) including
        current settings. If the port parameter is used, the ports field includes just one item.

        Example:
        POST /api/io/caps
        {
            "success" : true,
            "result" : {
                "ports" : [
                {
                    "port" : "relay1",
                    "type" : "output"
                },
                {
                    "port" : "relay2",
                    "type" : "output"
                }]
            }
        }

        port: Input/output identifier
        type: Type ( input – for digital inputs, output – for digital outputs)
        """
        return {
            'method': 'POST',
            'call': '/api/io/caps',
            'parameter': {
                'port': port
            }
        }

    @send_command
    def io_status(self, port=None):
        """
        The /api/io/status function returns the current statuses of logic inputs and outputs
        (ports) of the device. Define the input/output in the optional port parameter. If the
        port parameter is not included, statuses of all the inputs and outputs are returned.

        The function is part of the I/O service and the user must be assigned the I/O
        Monitoring privilege for authentication if required . The function is available with the

        :param port: Optional input/output identifier. Use also /api/io/caps to get
        identifiers of the available inputs and outputs.
        :return: The reply is in the application/json format and includes a port list (ports) including
        current settings ( state ). If the port parameter is used, the ports field includes just
        one item.

        Example:
        POST /api/io/status
        {
            "success" : true,
            "result" : {
            "ports" : [
                {
                    "port" : "relay1",
                    "state" : 0
                },
                {
                    "port" : "relay2",
                    "state" : 0
                }]
            }
        }
        """
        return {
            'method': 'POST',
            'call': '/api/io/status',
            'parameter': {
                'port': port
            }
        }

    @send_command
    def io_control(self, port, action, response=None):
        """
        The /api/io/ctrl function controls the statuses of the device logic outputs. The
        function has two mandatory parameters: port, which determines the output to be
        controlled, and action, defining the action to be executed over the output (activation,
        deactivation).

        The function is part of the I/O service and the user must be assigned the I/O
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :param port: Mandatory I/O identifier. Use also /api/io/caps to get the identifiers of
        the available inputs and outputs.
        :param action: Mandatory action defining parameter (on – activate output, log. 1, off –
        deactivate output, log. 0)
        :param response: Optional parameter modifying the intercom response to include the text
        defined here instead of the JSON message.
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/io/ctrl
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/io/ctrl',
            'parameter': {
                'port': port,
                'action': action,
                'response': response
            }
        }

    @send_command
    def phone_status(self, account=None):
        """
        The /api/phone/status functions helps you get the current statuses of the device
        SIP accounts.

        The function is part of the Phone/Call service and the user must be assigned the
        Phone/Call Monitoring privilege for authentication if required . The function is
        available with the Enhanced Integration licence key only.

        :param account: Optional SIP account identifier (1 or 2). If the parameter is not included,
        the function returns statuses of all the SIP accounts.
        :return: The reply is in the application/json format and includes a list of device SIP accounts
        ( accounts ) including current statuses. I f the account parameter is used, the
        accounts field includes just one item .

        Example:
        POST /api/phone/status
        {
            "success" : true,
            "result" : {
                "accounts" : [
                {
                    "account" : 1,
                    "sipNumber" : "5046",
                    "registered" : true,
                    "registerTime" : 1418034578
                    },
                {
                    "account" : 2,
                    "sipNumber" : "",
                    "registered" : false
                }]
            }
        }

        account: Unique SIP account identifier (1 or 2)
        sipNumber: SIP account telephone number
        registered: Account registration with the SIP Registrar
        registerTime: Last successful registration time in seconds since 00:00 1.1.1970 (unix time)
        """
        return {
            'method': 'POST',
            'call': '/api/phone/status',
            'parameter': {
                'account': account
            }
        }

    @send_command
    def call_status(self, session=None):
        """
        The /api/call/status function helps you get the current states of active telephone
        calls. The function returns a list of active calls including parameters.

        The function is part of the Phone/Call service and the user must be assigned the
        Phone/Call Monitoring privilege for authentication if required . The function is
        available with the Enhanced Integration licence key only.

        :param session: Optional call identifier. If the parameter is not included, the function
        returns statuses of all the active calls.
        :return: The reply is in the application/json format and includes a list of active calls (
        sessions) including their current states. If the session parameter is used, the
        sessions field includes just one item. If there is no active call, the sessions field is
        empty.

        Example:
        POST /api/call/status
        {
            "success" : true,
            "result" : {
            "sessions" : [
            {
                "session" : 1,
                "direction" : "outgoing",
                "state" : "ringing"
            }]
        }

        session: Call identifier
        direction: Call direction ( incoming , outgoing )
        state: Call state ( connecting , ringing , connected )
        """
        return {
            'method': 'POST',
            'call': '/api/call/status',
            'parameter': {
                'session': session
            }
        }

    @send_command
    def dial(self, number):
        """
        The /api/call/dial function initiates a new outgoing call to a selected phone number
        or sip uri. After some test with a Fritzbox, it seems you have to call '**your_number/1'
        to call internal phones. '/2' seems to be necessary if you want to call number over sip account 2.

        The function is part of the Phone/Call service and the user must be assigned the
        Phone/Call Control privilege for authentication if required . The function is available
        with the Enhanced Integration licence key only.

        :param number: Mandatory parameter specifying the destination phone number or sip uri
        :return: The reply is in the application/json format and includes information on the outgoing
        call created.

        Example:
        GET /api/call/dial
        {
            "success" : true,
            "result" : {
                "session" : 2
            }
        }

        session: Call identifier, used, for example, for call monitoring with
        /api/call/status or call termination with /api/call/hangup
        """
        return {
            'method': 'POST',
            'call': '/api/call/dial',
            'parameter': {
                'number': number
            }
        }

    @send_command
    def answer(self, session):
        """
        The /api/call/answer function helps you answer an active incoming call (in the
        ringing state).

        The function is part of the Phone/Call service and the user must be assigned the
        Phone/Call Control privilege for authentication if required . The function is available
        with the Enhanced Integration licence key only.

        :param session: Active incoming call identifier
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/call/answer
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/call/answer',
            'parameter': {
                'session': session
            }
        }

    @send_command
    def hangup(self, session, reason=None):
        """
        The /api/call/hangup helps you hang up an active incoming or outgoing call.
        The function is part of the Phone/Call service and the user must be assigned the

        Phone/Call Control privilege for authentication if required . The function is available
        with the Enhanced Integration licence key only.

        :param session:
        :param reason: End call reason:
            normal - normal call end (default value) reason
            rejected - call rejection signalling
            busy - station busy signalling
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/call/hangup
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/call/hangup',
            'parameter': {
                'session': session,
                'reason': reason
            }
        }

    @send_command
    def camera_caps(self):
        """
        The /api/camera/caps function returns a list of available video sources and
        resolution options for JPEG snapshots to be downloaded via the
        /api/camera/snapshot function.

        The function is part of the Camera service and the user must be assigned the Camera
        Monitoring privilege for authentication if required.

        :return: The reply is in the application/json format and includes a list of supported
        resolutions of JPEG snapshots ( jpegResolution ) and a list of available video sources (
        sources ), which can be used in the /api/camera/snapshot parameters.

        Example:
        POST /api/camera/caps
        {
            "success" : true,
            "result" : {
                "jpegResolution" : [
                {
                    "width" : 160,
                    "height" : 120
                },
                {
                    "width" : 176,
                    "height" : 144
                },
                {
                    "width" : 320,
                    "height" : 240
                },
                {
                    "width" : 352,
                    "height" : 272
                },
                {
                    "width" : 352,
                    "height" : 288
                },
                {
                    "width" : 640,
                    "height" : 480
                }],
                "sources" : [
                {
                    "source" : "internal"
                },
                {
                    "source" : "external"
                }]
            }
        }

        width, height: Snapshot resolution in pixels
        source: Video source identifier
        """
        return {
            'method': 'POST',
            'call': '/api/camera/caps',
            'parameter': {}
        }

    @send_command
    def camera_snapshot(self, width, height, source=None, fps=None):
        """
        The /api/camera/snapshot function helps you download images from an internal or
        external IP camera connected to the intercom. Specify the video source, resolution and
        other parameters.

        The function is part of the Camera service and the user must be assigned the Camera
        Monitoring privilege for authentication if required.

        :param width: Mandatory parameter specifying the horizontal resolution of the JPEG image in pixels
        :param height: Mandatory parameter specifying the vertical resolution of the JPEG image in pixels.
        The snapshot height and width must comply with one of the supported options (see api/camera/caps ).
        :param source: Optional parameter defining the video source ( internal – internal camera,
        external – external IP camera). If the parameter is not included, the default video source included in
        the Hardware / Camera / Common settings section of the configuration web interface is selected.
        :param fps: Optional parameter defining the frame rate. If the parameter is set to >= 1, the intercom sends
        images at the set frame rate using the http server push method .
        :return: The reply is in the image/jpeg or multipart/x-mixed-replace (pro fps >= 1) format. If the request
        parameters are wrong, the function returns information in the application/json format.

        Example:
        POST /api/camera/snapshot
        {}
        """
        return {
            'method': 'POST',
            'call': '/api/camera/snapshot',
            'parameter': {
                'width': width,
                'height': height,
                'source': source,
                'fps': fps
            }
        }

    @send_command
    def display_caps(self):
        """
        The /api/display/caps function returns a list of device displays including their
        properties. Use the function for display detection and resolution.

        The function is part of the Display service and the user must be assigned the Display
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :return: The reply is in the application/json format and includes a list of available displays (displays).

        Example:
        POST /api/display/caps
        {
            "success" : true,
            "result" : {
                "displays" : [
                {
                    "display" : "internal",
                    "resolution" : {
                        "width" : 320,
                        "height" : 240
                    }
                }]
            }
        }

        display: Display identifier
        resolution: Display resolution in pixels
        """
        return {
            'method': 'POST',
            'call': '/api/display/caps',
            'parameter': {}
        }

    @send_command
    def display_upload_image(self, display, gif):
        """
        The /api/display/image function helps you upload content to be displayed.
        Note: The function is available only if the standard display function is disabled in the Hardware / Display
        section of the configuration web interface.

        The function is part of the Display service and the user must be assigned the Display
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :param display: Mandatory display identifier ( internal )
        :param gif: Mandatory parameter including a GIF image with display resolution
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        PUT /api/display/image
        {
            "success" : true
        }
        """
        return {
            'method': 'PUT',
            'call': '/api/display/image',
            'name': 'blob-image',
            'parameter': {
                'display': display
            },
            'filename': gif
        }

    @send_command
    def display_delete_image(self, display):
        """
        The /api/display/image function helps you delete content from the display.
        Note: The function is available only if the standard display function is disabled in the Hardware / Display
        section of the configuration web interface.

        The function is part of the Display service and the user must be assigned the Display
        Control privilege for authentication if required . The function is available with the
        Enhanced Integration licence key only.

        :param display: Mandatory display identifier ( internal )
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        DELETE /api/display/image
        {
            "success" : true
        }
        """
        return {
            'method': 'DELETE',
            'call': '/api/display/image',
            'parameter': {
                'display': display
            }
        }

    @send_command
    def log_caps(self):
        """
        The /api/log/caps function returns a list of supported event types that are recorded
        in the device. This list is a subset of the full event type list below:

        The function is part of the Logging service and requires no special user privileges.

        :return: The reply is in the application/json format.

        Example:
        GET /api/log/caps
        {
            "success" : true,
            "result" : {
                "events" : [
                    "KeyPressed",
                    "KeyReleased",
                    "InputChanged",
                    "OutputChanged",
                    "CardEntered",
                    "CallStateChanged",
                    "AudioLoopTest",
                    "CodeEntered",
                    "DeviceState",
                    "RegistrationStateChanged"
                ]
            }
        }

        events: Array of strings including a list of supported event types
        """
        return {
            'method': 'POST',
            'call': '/api/log/caps',
            'parameter': {}
        }

    @send_command
    def log_subscribe(self, include=None, filter=None, duration=None):
        """
        The /api/log/subscribe function helps you create a subscription channel and returns
        a unique identifier to be used for subsequent dialling of the /api/log/pull or
        /api/log/unsubscribe function.

        Each subscription channel contains an event queue of its own. All the new events that
        match the channel filter ( filter parameter) are added to the channel queue and read
        using the /api/log/pull function.
        At the same time, the device keeps the event history queue (last 500 events) in its
        internal memory. The event history queue is empty by default.
        Use the include parameter to specify whether the channel queue shall be empty after
        restart (storing of events occurring after the channel is opened), or be filled with all or
        some events from the event history records.
        Use the duration parameter to define the channel duration if it is not accessed via
        /api/log/pull . The channel will be closed automatically when the defined timeout
        passes as if the /api/log/unsubscribe function were used.

        The function is part of the Logging service and requires some user privileges for
        authentication. Unprivileged user events shall not be included in the channel queue.

        Event type / Required user privileges:
        ----
        DeviceState: None
        AudioLoopTest: None
        MotionDetected: None
        NoiseDetected: None
        KeyPressed: Keypad monitoring
        KeyReleased: Keypad monitoring
        CodeEntered: Keypad monitoring
        CardEntered: UID monitoring (cards/Wiegand)
        InputChanged: I/O monitoring
        OutputChanged: I/O monitoring
        SwitchStateChanged: I/O monitoring
        CallStateChanged: Call/phone monitoring
        RegistrationStateChanged: Call/phone monitoring

        :param include: (optional), type 'string', default: new
        Define the events to be added to the channel event queue:
            new - only new events occurring after
            all - all events recorded so far including those occurring after channel creation
            -t - all events recorded in the last t seconds including those occurring after channel creation (-10, e.g.)
        :param filter: optional, type 'list', default: no filter
        List of required event types separated with commas. The parameter is optional and if no value is
        entered, all available event types are transferred via the channel.
        :param duration: (optional), type 'uint32', default 90
        Define a timeout in seconds after which the channel shall be closed automatically if no
        /api/log/pull reading operations are in progress. Every channel reading automatically extends the channel
        duration by the value included here. Themaximum value is 3600 s.
        :return: The reply is in the application/json format subscription.

        Example:
        POST /api/log/subscribe
        {
            "success" : true,
            "result" : {
                "id" : 2121013117
            }
        }

        id: Unique identifier created by subscription
        """
        return {
            'method': 'POST',
            'call': '/api/log/subscribe',
            'parameter': {
                'include': include,
                'filter': filter,
                'duration': duration
            }
        }

    @send_command
    def log_unsubscribe(self, id):
        """
        The /api/log/unsubscribe function helps you close the subscription channel with the
        given identifier. When the function has been executed, the given identifier cannot be
        used, i.e. all subsequent /api/log/pull or /api/log/unsubscribe calls with the
        same identifier will end up with an error.

        The function is part of the Logging service and requires no special user privileges.

        :param id: Identifier of the existing channel obtained by preceding dialling of /api/log/subscribe
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/log/unsubscribe
        {
            "success" : true,
        }
        """
        return {
            'method': 'POST',
            'call': '/api/log/unsubscribe',
            'parameter': {
                'id': id
            }
        }

    @send_command
    def log_pull(self, id, timeout=None):
        """
        The /api/log/pull function helps you read items from the channel queue
        (subscription) and returns a list of events unread so far or an empty list if no new
        event is available.
        Use the timeout parameter to define the maximum time for the intercom to generate
        the reply. If there is one item at least in the queue, the reply is generated immediately.
        In case the channel queue is empty, the intercom puts off the reply until a new event
        arises or the defined timeout elapses.

        The function is part of the Logging service and requires no special user privileges .

        :param id: (uint32, mandatory) Identifier of the existing channel created by preceding dialling of
        /api/log/subscribe
        :param timeout: (uint32, optional, default: 0) Define the reply delay (in seconds) if the channel queue is
        empty. The default value 0 means that the intercom shall reply without delay.
        :return: The reply is in the application/json format and includes a list of events.

        Example:
        POST /api/log/pull
        {
            "success" : true,
            "result" : {
                "events" : [
                {
                    "id" : 1,
                    "utcTime" : 1437987102,
                    "upTime" : 8,
                    "event" : "DeviceState",
                    "params" : {
                        "state" : "startup"
                    }
                },
                {
                    "id" : 3,
                    "utcTime" : 1437987105,
                    "upTime" : 11,
                    "event" : "RegistrationStateChanged",
                    "params" : {
                        "sipAccount" : 1,
                        "state" : "registered"
                    }
                }]
            }
        }

        events: Event object array. If no event occurs during the timeout, the array is empty.
        """
        return {
            'method': 'POST',
            'call': '/api/log/pull',
            'parameter': {
                'id': id,
                'timeout': timeout
            }
        }

    @send_command
    def audio_test(self):
        """
        The /api/audio/test function launches an automatic test of the intecom built-in
        microphone and speaker. The test result is logged as an AudioLoopTest event.

        The function is part of the Audio service and the user must be assigned the
        Audio Control privilege for authetication if required. The function is only available with
        the Enhanced Integration and Enhanced Audio licence key.

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/audio/test
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/audio/test',
            'parameter': {}
        }

    @send_command
    def email_send(self, to, subject, body=None, picture_count=None, width=None, height=None):
        """
        The /api/email/send function sends an e-mail to the required address. Make sure
        that the SMTP service is configured correctly for the device (i.e. correct SMTP server
        address, login data etc.).

        The function is part of the Email service and the user must be assigned the Email
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only.

        :param to: Mandatory parameter specifying the delivery address.
        :param subject: Mandatory parameter specifying the subject of the message.
        :param body: Optional parameter specifying the contents of the message (including html marks if necessary).
        If not completed, the message will be delivered without any contents.
        :param picture_count: Optional parameter specifying the count of camera images to be enclosed.
        If not completed, no images are enclosed. Parameter values: 0 and 1.
        :param width: image width in pixel. Optional if picture_count = 0.
        :param height: image height in pixel. Optional if picture_count = 0.
        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/email/send
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/email/send',
            'parameter': {
                'to': to,
                'subject': subject,
                'body': body,
                'pictureCount': picture_count,
                'width': width,
                'height': height
            }
        }

    @send_command
    def pcap(self):
        """
        The /api/pcap function helps download the network interface traffic records (pcap
        file). You can also use the /api/pcap/restart a /api/pcap/stop functions for
        network traffic control.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only

        :return: The reply is in the application/json format and the downloaded file can be opened
        directly in Wireshark, for example.

        Example:
        POST /api/pcap
        {}
        """
        return {
            'method': 'GET',
            'call': '/api/pcap',
            'parameter': {},
            'stream': True
        }

    @send_command
    def pcap_restart(self):
        """
        The /api/pcap/restart function deletes all records and restarts the network interface
        traffic recording.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/pcap/restart
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/pcap/restart',
            'parameter': {},
        }

    @send_command
    def pcap_stop(self):
        """
        The /api/pcap/stop function stops the network interface traffic recording.

        The function is part of the System service and the user must be assigned the System
        Control privilege for authentication if required. The function is available with the
        Enhanced Integration licence key only

        :return: The reply is in the application/json format and includes no parameters.

        Example:
        POST /api/pcap/stop
        {
            "success" : true
        }
        """
        return {
            'method': 'POST',
            'call': '/api/pcap/stop',
            'parameter': {},
        }

class EventService(Service):
    def __init__(self, ip_cam):
        super(EventService, self).__init__(ip_cam)
        self.event_url = "/notification"