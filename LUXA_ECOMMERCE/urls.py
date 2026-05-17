"""
URL configuration for LUXA_ECOMMERCE project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from register import views as v
from register.forms import EmailCheckingPasswordResetForm
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from MAIN.views import check_notifications

urlpatterns = [
    path('admin/api/check-notifications/', check_notifications, name='check_notifications'), # admin notifications
    path('admin/', admin.site.urls),
    path('register/', v.register, name="register"),
    path("vendorcreate/", v.vendform, name="vendform"),
    path('login/', v.CustomLoginView.as_view(), name="login"),
    path('logout/', v.logout_view, name='logout'),
    path('', include("pages.urls")),
    path('', include("MAIN.urls")),
    path('escrow/', include("escrow.urls")),
    path('couriers/', include("couriers.urls")),
    # 3. Link clicked -> User enters new password
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='register/PasswordReset/password_reset_confirm.html'), 
         name='password_reset_confirm'),

    # 4. Password successfully changed
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='register/PasswordReset/password_reset_complete.html'), 
         name='password_reset_complete'),
    
    path('', include("django.contrib.auth.urls")),
    path('accounts/', include('allauth.urls')),
    path('password-change/', v.custom_password_change, name='change_password'),
    # 1. User requests a reset
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='register/PasswordReset/password_reset_form.html',
             form_class=EmailCheckingPasswordResetForm, 
             html_email_template_name='register/PasswordReset/password_reset_email.html',
         ), 
         name='password_reset'),

    # 2. Email sent success message
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='register/PasswordReset/password_reset_done.html'), 
         name='password_reset_done'),

]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Keep the old routing locally so you don't accidentally redirect to the live AWS site!
    urlpatterns += [
        path('luxa_crave/', include("luxa_crave.urls")),
    ]

if not settings.DEBUG:
    urlpatterns += [
        # 1. Redirect the exact base URL (luxa.ng/luxa_crave/ -> crave.luxa.ng/)
        path('luxa_crave/', RedirectView.as_view(url='https://crave.luxa.ng/', permanent=True)),
        
        # 2. Redirect any sub-pages dynamically (luxa.ng/luxa_crave/checkout/ -> crave.luxa.ng/checkout/)
        path('luxa_crave/<path:subpath>', RedirectView.as_view(url='https://crave.luxa.ng/%(subpath)s', permanent=True)),
    ]
