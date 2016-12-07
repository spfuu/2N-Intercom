import json

class InvalidCommandError(Exception):
    def __init__(self, error_code):
        message = 'Unknown error occurred.'
        if error_code in err_code:
            message=err_code[error_code][1]
        super(InvalidCommandError, self).__init__(message)


def raise_for_intercom_error(intercom_response):
    status = json.loads(intercom_response)
    if 'error' not in status:
        return
    raise InvalidCommandError(status['error']['code'])

err_code = {
    1: ['function is not supported', 'The requested function is unavailable in this model.'],
    2: ['invalid request path',
        'The absolute path specified in the HTTP request does not match any of the HTTP API functions.'],
    3: ['invalid request method', 'The HTTP method used is invalid for the selected function.'],
    4: ['function is disabled',
        'The function (service) is disabled. Enable the function on the Services / HTTP API '
        'configuration interface page.'],
    5: ['function is licensed', 'The function (service) is subject to licence and available with a licence key only.'],
    7: ['invalid connection type', 'HTTPS connection is required.'],
    8: ['invalid authentication method',
        'The authentication method used is invalid for the selected service. This error happens when the Digest method '
        'is only enabled for the service but the client tries to authenticate via the Basic method.'],
    9: ['authorisation required',
        'User authorisation is required for the service access. This error is sent together with the HTTP status code '
        'Authorisation Required.'],
    10: ['insufficient user privileges', 'The user to be authenticated has insufficient privileges for the function.'],
    11: ['missing mandatory parameter',
         'The request lacks a mandatory parameter. Refer to param for the parameter name.'],
    12: ['invalid parameter value', 'A parameter value is invalid. Refer to param for the parameter name.'],
    13: ['parameter data too big',
         'The parameter data exceed the acceptable limit. Refer to param for the parameter name.'],
    14: ['unspecified processing error', 'An unspecified error occurred during request processing.'],
    15: ['no data available', 'The required data are not available on the server.']
}
