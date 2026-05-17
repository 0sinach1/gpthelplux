from django.shortcuts import render, redirect
from .forms import registerForm, vendorform
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from allauth.account.models import EmailAddress
from MAIN.models import Customer, Vendor
import logging

logger = logging.getLogger(__name__)

# Create your views here.
# views.py

def register(request):
    if request.method == "POST": 
        form = registerForm(request.POST)
        if form.is_valid():
            dob = form.cleaned_data.get('date_of_birth')
            username = form.cleaned_data.get('username')
            
            try:
                with transaction.atomic():
                    user = form.save()
                    
                    # Create or get customer profile
                    customer, created = Customer.objects.get_or_create(
                        user_account=user,
                        defaults={
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'username': username,
                            'email': user.email,
                            'date_of_birth': dob,
                        }
                    )
                    
                    if not created:
                        customer.first_name = user.first_name
                        customer.last_name = user.last_name
                        customer.username = username
                        customer.email = user.email
                        customer.date_of_birth = dob
                        customer.save()

                # --- EMAIL VERIFICATION LOGIC (CORRECTED) ---
                email_address, created = EmailAddress.objects.get_or_create(
                    user=user, 
                    email=user.email, 
                    defaults={'primary': True, 'verified': False}
                )

                # Now 'request' is valid because we fixed the function definition
                email_address.send_confirmation(request) 

                return redirect('account_email_verification_sent')
            
            except IntegrityError as e:
                logger.error(f"Registration IntegrityError: {e}", exc_info=True)
                form.add_error(None, "An account with this email or username already exists.")
            except ValidationError as e:
                logger.error(f"Registration ValidationError: {e}", exc_info=True)
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        for error in errors:
                            form.add_error(field, error)
                else:
                    form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Registration error: {e}", exc_info=True)
                form.add_error(None, "An error occurred during registration.")
    else:
        form = registerForm()

    context = {"form": form}
    return render(request, 'register/register.html', context)

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    
    def get_success_url(self):
        user = self.request.user
        
        # Check if user has a vendor profile
        if hasattr(user, 'vendor_profile'):
            return '/vendash/'  # Placeholder for now
        
        # Default to index for customers or users without profiles
        return '/index/'
    
def logout_view(request):
    logout(request)
    return redirect('/index/')

@login_required(login_url='/login/')
def vendform(request):
    # 1. CHECK EXISTING STATUS
    if hasattr(request.user, 'vendor_profile'):
        vendor_profile = request.user.vendor_profile
        
        # If they are already an ACTIVE vendor, send them to the vendor dashboard
        if vendor_profile.is_active:
            return redirect('/vendash/')
        
        # If they exist but are NOT active (Pending), show the "Pending" popup immediately.
        # This prevents the "redirect loop" or error you were seeing.
        return render(request, "registration/vendorcreate.html", {
            "form": vendorform(), # Pass empty form
            "success": True       # Trigger the popup
        })

    # 2. HANDLE NEW FORM SUBMISSION
    if request.method == 'POST':
        form = vendorform(request.POST, request.FILES)

        if form.is_valid():
            try:
                vendor = form.save(commit=False)
                vendor.user_account = request.user
                
                # CRITICAL: Force them to be inactive so they don't become vendors immediately
                vendor.is_active = False 

                if not vendor.image:
                    # ...check if they have a Customer Profile with a picture
                    if hasattr(request.user, 'customer_profile') and request.user.customer_profile.profile_picture:
                        # Assign the customer's profile picture to the vendor image field
                        vendor.image = request.user.customer_profile.profile_picture
                
                vendor.save()
                
                # CRITICAL: Do NOT redirect. Render the page again with success=True
                return render(request, "registration/vendorcreate.html", {
                    "form": vendorform(), # Clear the form
                    "success": True       # This triggers the popup in the HTML
                })

            except IntegrityError as e:
                logger.error(f"Vendor registration IntegrityError: {e}", exc_info=True)
                form.add_error(None, "A vendor with this business name or email already exists.")
            except ValidationError as e:
                logger.error(f"Vendor registration ValidationError: {e}", exc_info=True)
                
                if hasattr(e, 'message_dict'):
                    for field, errors in e.message_dict.items():
                        for error in errors:
                            form.add_error(field, error)
                else:
                    form.add_error(None, str(e))
            except Exception as e:
                logger.error(f"Vendor registration error: {e}", exc_info=True)
                form.add_error(None, "An error occurred. Please try again.")
    else:
        form = vendorform()

    context = {"form":form}

    return render(request, "registration/vendorcreate.html", context)

@login_required
def custom_password_change(request):
    user = request.user
    
    # 1. Decide which form to use
    if user.has_usable_password():
        FormClass = PasswordChangeForm
    else:
        FormClass = SetPasswordForm

    if request.method == 'POST':
        form = FormClass(user, request.POST)
        if form.is_valid():
            form.save()
            # 2. Critical: Update session so they don't get logged out
            update_session_auth_hash(request, user) 
            messages.success(request, "Your password has been successfully updated!")
            return redirect('/editprofile/')
        else:
            messages.error(request, "Please correct the error below.")
    else:
        form = FormClass(user)

    return render(request, 'registration/change_password.html', {
        'form': form,
        'has_password': user.has_usable_password() # Pass this to control the template text
    })
