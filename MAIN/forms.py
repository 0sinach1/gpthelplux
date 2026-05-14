from django import forms
from .models import Customer, Category, Product, ProductImage, KYCVerification
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError

User = get_user_model()

class CustomerProfileForm(forms.ModelForm):
    """Form for editing customer profile information.
    
    When commit=False, if a user object is present and modified, it will be
    attached to the returned customer instance as customer._unsaved_user.
    The caller must save customer._unsaved_user explicitly if needed.
    """
    
    # User model fields that we want to edit
    username = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    
    class Meta:
        model = Customer
        fields = [
            'profile_picture',
            'first_name',
            'last_name',
            'gender', 
            'social_media_platform', 
            'social_media_handle',
            'phone_number',
            'date_of_birth',
            'address_line1',
            'address_line2',
            'city',
            'state',
            'postal_code',
            'country',
        ]
        labels = {
            'phone_number': 'Preferrably Your WhatsApp Number',  
            }
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address_line1': forms.Textarea(attrs={'rows': 2}),
            'address_line2': forms.Textarea(attrs={'rows': 2}),
            'gender': forms.Select()
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Pre-populate with user data if editing
        if self.user:
            if not self.initial.get('username'):
                self.initial['username'] = self.user.username
            if not self.initial.get('email'):
                self.initial['email'] = self.user.email
    
    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        email = cleaned_data.get('email')
        current_user = self.user or getattr(self.instance, 'user_account', None)
        errors = {}
        
        # Use case-sensitive lookups to match DB constraints
        if username:
            username_qs = User.objects.filter(username=username)
            if current_user:
                username_qs = username_qs.exclude(pk=current_user.pk)
            if username_qs.exists():
                errors['username'] = ['This username is already in use.']
        
        if email:
            email_qs = User.objects.filter(email=email)
            if current_user:
                email_qs = email_qs.exclude(pk=current_user.pk)
            if email_qs.exists():
                errors['email'] = ['This email address is already in use.']
        
        # Validate User instance if we're going to update it
        # (Customer instance validation happens in save() after form data is applied)
        user_obj = self.user or getattr(self.instance, 'user_account', None)
        if user_obj and (username or email):
            # Temporarily update user fields to validate them
            original_username = user_obj.username
            original_email = user_obj.email
            try:
                if username is not None:
                    user_obj.username = username
                if email is not None:
                    user_obj.email = email
                user_obj.full_clean()
            except ValidationError as e:
                # Merge User model validation errors into form errors
                if hasattr(e, 'error_dict') and e.error_dict:
                    for field, error_list in e.error_dict.items():
                        if field not in errors:
                            errors[field] = []
                        if isinstance(error_list, list):
                            errors[field].extend([str(err) for err in error_list])
                        else:
                            errors[field].append(str(error_list))
                elif hasattr(e, 'messages') and e.messages:
                    if '__all__' not in errors:
                        errors['__all__'] = []
                    errors['__all__'].extend([str(msg) for msg in e.messages])
            finally:
                # Restore original values
                user_obj.username = original_username
                user_obj.email = original_email
        
        if errors:
            raise ValidationError(errors)
        
        return cleaned_data
    
    def save(self, commit=True):
        customer = super().save(commit=False)
        username = self.cleaned_data.get('username')
        email = self.cleaned_data.get('email')
        user_obj = self.user or getattr(customer, 'user_account', None)
        
        if username is not None:
            customer.username = username
        if email is not None:
            customer.email = email
        
        # Perform model-level validation on Customer instance with form data applied
        # This catches model ValidationErrors before saving to the database
        try:
            customer.full_clean()
        except ValidationError as e:
            # Convert model ValidationError to form errors
            errors = {}
            if hasattr(e, 'error_dict') and e.error_dict:
                for field, error_list in e.error_dict.items():
                    errors[field] = []
                    if isinstance(error_list, list):
                        errors[field].extend([str(err) for err in error_list])
                    else:
                        errors[field].append(str(error_list))
            elif hasattr(e, 'messages') and e.messages:
                errors['__all__'] = [str(msg) for msg in e.messages]
            else:
                errors['__all__'] = [str(e)]
            raise ValidationError(errors)
        
        # Track if user was modified for commit=False handling
        user_modified = False
        if user_obj:
            if username is not None and user_obj.username != username:
                user_obj.username = username
                user_modified = True
            if email is not None and user_obj.email != email:
                user_obj.email = email
                user_modified = True
        
        if commit:
            try:
                with transaction.atomic():
                    if user_obj:
                        user_obj.save()
                        if not customer.user_account_id:
                            customer.user_account = user_obj
                    customer.save()
                    # Persist any many-to-many data within the same transaction
                    self.save_m2m()
            except IntegrityError as e:
                # Handle race conditions: convert IntegrityError to ValidationError
                # Check which field caused the constraint violation
                error_str = str(e).lower()
                errors = {}
                
                # Try to identify which field caused the violation from error message
                username_violated = 'username' in error_str
                email_violated = 'email' in error_str
                
                # If error message doesn't specify, check database to determine conflict
                if not username_violated and not email_violated:
                    # Check which field actually conflicts in the database
                    if username:
                        username_violated = User.objects.filter(
                            username=username
                        ).exclude(pk=user_obj.pk if user_obj else None).exists()
                    if email:
                        email_violated = User.objects.filter(
                            email=email
                        ).exclude(pk=user_obj.pk if user_obj else None).exists()
                
                # Set appropriate error messages (ValidationError expects lists)
                if username_violated:
                    errors['username'] = ['This username is already in use.']
                if email_violated:
                    errors['email'] = ['This email address is already in use.']
                
                # If we still can't determine, provide generic error as non-field error
                if not errors:
                    errors['__all__'] = ['A user with this username or email already exists.']
                
                # Always raise ValidationError with consistent dict format
                raise ValidationError(errors)
        else:
            # When commit=False, attach modified user to customer for caller to save
            if user_obj and user_modified:
                customer._unsaved_user = user_obj
            if user_obj and not customer.user_account_id:
                customer.user_account = user_obj
            # Caller must handle saving customer._unsaved_user and calling save_m2m() if needed
        
        return customer

class ProductListingForm(forms.ModelForm):
    """Form for vendors to create or edit product listings"""

    # ✅ Smooth vendor variant input
    vendor_variants = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Enter variants like:\nColor: Red, Blue, Black\nSize: Small, Medium, Large"
        }),
        help_text="Each variant should be on a new line (Variant: values separated by commas)."
    )

    class Meta:
        model = Product
        exclude = [
            'vendor', 'slug', 'created_at',
            'model_3d_file', 'updated_at',
            'is_featured', 'is_active',
            'is_approved'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'meta_description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)  # pass vendor from view
        super().__init__(*args, **kwargs)

        # ✅ If editing an existing product, prefill vendor_variants nicely
        if self.instance and self.instance.vendor_variants:
            formatted = []
            for key, values in self.instance.vendor_variants.items():
                formatted.append(f"{key}: {', '.join(values)}")

            self.fields["vendor_variants"].initial = "\n".join(formatted)

    def clean_vendor_variants(self):
        """
        Convert vendor input into JSON format.
        Example input:
            Color: Red, Blue
            Size: Small, Medium
        Output:
            {"Color": ["Red", "Blue"], "Size": ["Small", "Medium"]}
        """
        raw_data = self.cleaned_data.get("vendor_variants")

        if not raw_data:
            return {}

        variants = {}
        lines = raw_data.split("\n")

        for line in lines:
            if ":" not in line:
                continue

            key, values = line.split(":", 1)
            key = key.strip()

            values_list = [
                v.strip()
                for v in values.split(",")
                if v.strip()
            ]

            if key and values_list:
                variants[key] = values_list

        return variants

    def save(self, commit=True):
        product = super().save(commit=False)

        # attach the logged-in vendor
        if self.vendor:
            product.vendor = self.vendor

        if commit:
            product.save()

        return product

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return price


class ProductImageForm(forms.ModelForm):
    """Form for uploading additional product images"""
    
    class Meta:
        model = ProductImage
        fields = [
            'orthographicfront', 
            'orthographicleft', 
            'orthographicright', 
            'orthographicback', 
            'orthographictop', 
            'orthographicbottom', 
            'perspectivefront', 
            'perspectiveback',
            'video360',
        ]

        labels = {
            'orthographicfront': 'Front (Orthographic) View',
            'orthographicleft': 'Left (Orthographic) View',
            'orthographicright': 'Right (Orthographic) View',
            'orthographicback': 'Back (Orthographic) View',
            'orthographictop': 'Top (Orthographic) View',
            'orthographicbottom': 'Bottom (Orthographic) View',
            'perspectivefront': 'Front (Perspective) View',
            'perspectiveback': 'Back (Perspective) View',
            'video360': '360° Product Video',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        required_fields = [
            'orthographicfront', 'orthographicleft', 'orthographicright', 
            'orthographicback', 'orthographictop', 'orthographicbottom',
            'perspectivefront', 'perspectiveback', 'video360'
        ]

        for field in required_fields:
            self.fields[field].required = True

    def clean_video(self):
        video = self.cleaned_data.get('video360')
        if not video:
            raise forms.ValidationError("Please upload a 360° product video.")
        return video

# KYC Verification Form
class KYCSubmissionForm(forms.ModelForm):
    class Meta:
        model = KYCVerification
        fields = ['full_name_on_id', 'id_type', 'id_number', 'social_media_platform', 'social_media_handle', 'document_front', 'document_back', 'selfie']
        labels = {
            'full_name_on_id': 'Full Name as on ID',
            'social_media_platform': 'Select a social media platform',
            'id_type': 'Type of Identification Document',
            'id_number': 'Identification Number as it appears on the document',  
            }
        widgets = {
            'full_name_on_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name exactly as shown on ID'}),
            'social_media_platform': forms.Select(attrs={'class': 'form-control'}),
            'social_media_handle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@<socialmedia handle>'}),
            'id_type': forms.Select(attrs={'class': 'form-control'}),
            'id_number': forms.TextInput(attrs={'class': 'form-control'}),
            # Add custom file input styling if needed
        }


