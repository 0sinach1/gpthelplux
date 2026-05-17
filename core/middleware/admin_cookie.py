from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

class AdminSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Change cookie name *only* for /admin paths
        if request.path.startswith('/admin'):
            request.COOKIES['sessionid'] = request.COOKIES.get('sessionid_admin')
            settings.SESSION_COOKIE_NAME = 'sessionid_admin'
        else:
            settings.SESSION_COOKIE_NAME = 'sessionid_user'

    def process_response(self, request, response):
        if request.path.startswith('/admin'):
            # Set admin cookie name properly
            if 'sessionid' in response.cookies:
                response.cookies['sessionid'].key = 'sessionid_admin'
        else:
            if 'sessionid' in response.cookies:
                response.cookies['sessionid'].key = 'sessionid_user'
        return response
