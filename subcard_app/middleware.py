from django.shortcuts import redirect
from django.urls import reverse
from .models import SiteSetting

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Load settings
        settings = SiteSetting.load()
        
        if settings.maintenance_mode:
            # Allow access to admin and maintenance page itself
            # Also allow login/logout so admins can log in
            path = request.path
            allowed_paths = [
                reverse('admin:index') if 'admin' in path else None, # Rough check for django admin
                reverse('maintenance') if hasattr(request, 'resolver_match') and request.resolver_match and request.resolver_match.url_name == 'maintenance' else '/maintenance/',
                reverse('admin_login'),
                reverse('admin_logout'),
                reverse('login'),
                reverse('logout'),
            ]
            
            # If it's a staff user, they can access anything
            if request.user.is_authenticated and request.user.is_staff:
                return self.get_response(request)
            
            # Redirect if not in allowed paths
            if not any(path.startswith(p) for p in allowed_paths if p):
                if path != '/maintenance/':
                    return redirect('maintenance')

        return self.get_response(request)
