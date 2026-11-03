"""Let django-axes work with Arches views that call authenticate() without a request.

Arches' LoginView calls ``authenticate(username=..., password=...)`` and never
passes ``request``, which AxesStandaloneBackend rejects. The middleware below
stores the active request so the backend can fall back to it.
"""

from contextvars import ContextVar

from axes.backends import AxesStandaloneBackend

_current_request = ContextVar("axes_current_request", default=None)


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)


class RequestFallbackAxesBackend(AxesStandaloneBackend):
    def authenticate(self, request=None, username=None, password=None, **kwargs):
        if request is None:
            request = _current_request.get()
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )


def record_failed_login_without_request(sender, credentials, request=None, **kwargs):
    """Count failures that Django reports with request=None.

    Django forwards the request given to authenticate() on the
    user_login_failed signal. Arches passes none, so axes' own receiver skips
    the attempt and nothing is ever counted. Replay it with the stored request.
    """
    if request is not None:
        return
    request = _current_request.get()
    if request is None:
        return
    from axes.handlers.proxy import AxesProxyHandler

    AxesProxyHandler.user_login_failed(sender, credentials, request, **kwargs)
