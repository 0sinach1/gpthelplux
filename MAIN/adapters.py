from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse  # <-- NEW IMPORT
from django.shortcuts import resolve_url, render      # <-- ADDED render
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth import get_user_model        # <-- NEW IMPORT

User = get_user_model()

class MyAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        # Get the 'next' parameter if it exists
        next_url = request.POST.get('next') or request.GET.get('next')

        # If they are a courier, route them to the courier dashboard
        if hasattr(request.user, 'courier_profile'):
            return reverse('courier_dashboard')
        
        # If 'next' exists, prioritize it (standard Django behavior)
        if next_url:
            return next_url

        # Custom Logic: Check if user is a vendor
        # (Assuming you have a way to check this, e.g., a group or profile field)
        if hasattr(request.user, 'vendor_profile') and request.user.vendor_profile.is_active:
            return resolve_url('vendash')
            
        # Default for everyone else
        return resolve_url('index')
    

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    
    # --- NEW: THE COLLISION INTERCEPTOR ---
    def pre_social_login(self, request, sociallogin):
        # 1. If the user is already connected to Google, do nothing
        if sociallogin.is_existing:
            return

        # 2. Grab the email Google just sent us
        if 'email' not in sociallogin.account.extra_data:
            return
        
        email = sociallogin.account.extra_data['email'].lower()
        
        # 3. Check if a local user with this email already exists
        try:
            user = User.objects.get(email__iexact=email)
            
            # 4. If they exist but aren't connected to this Google account...
            if not sociallogin.is_existing:
                # INTERCEPT! Stop the crash and render our beautiful custom page instead.
                response = render(request, 'MAIN/authentication/social_link_error.html', {'email': email})
                raise ImmediateHttpResponse(response)
                
        except User.DoesNotExist:
            pass # Email is brand new, let Allauth proceed with standard registration

    # --- EXISTING: YOUR ONBOARDING LOGIC ---
    def save_user(self, request, sociallogin, form=None):
        # This saves the user first
        user = super().save_user(request, sociallogin, form)
        
        # Now trigger the popup message
        messages.success(
            request, 
            "Welcome to Luxa.ng! Please click the 'Edit Profile' button to complete your setup.",
            extra_tags='onboarding_popup' # We use this tag to identify this specific message in HTML
        )
        return user
    
    # --- EXISTING: YOUR DEBUGGING LOGIC ---
    def on_authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        print("\n\n❌ SOCIAL AUTH FAILURE ❌")
        print(f"Provider: {provider_id}")
        print(f"Error: {error}")
        print(f"Exception: {exception}")
        if extra_context:
            print(f"Context: {extra_context}")
        print("\n\n")