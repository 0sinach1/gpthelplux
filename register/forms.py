from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from allauth.socialaccount.forms import SignupForm
from django import forms
from MAIN.models import Vendor, Customer
from datetime import date

class registerForm(UserCreationForm):
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.EmailField()
    date_of_birth = forms.DateField(
        widget = forms.DateInput(attrs={'type': 'date'}),
        label="Date of Birth",
        required=True
    )
    gender = forms.ChoiceField(
        choices=Customer.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Gender",
        required=True
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "password1", "password2"]
        help_texts = {
            'first_name': None,
            'last_name': None,
            'username': None,
            'password1': None,
            'password2': None,
        }
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        today = date.today()

        if dob is None:
            raise forms.ValidationError("Please enter your date of birth.")

        # Minimum age requirement
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 15:
            raise forms.ValidationError("You must be at least 15 years old to register.")

        return dob
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ""
        # Set bootstrap classes for styling
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['first_name'].widget.attrs['class'] = 'form-control'
        self.fields['last_name'].widget.attrs['class'] = 'form-control'
        self.fields['email'].widget.attrs['class'] = 'form-control'
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'
        self.fields['date_of_birth'].widget.attrs['class'] = 'form-control'
        self.fields['gender'].widget.attrs['class'] = 'form-control'
        
class vendorform(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'business_name',
            'contact_person',
            'official_email',
            'official_phone',
            'business_type',
            'instagramlink',
            'selling_category',
            'business_address',
            'warrantyinfo',
            'city',
            'state',
            'postal_code',
            'country',
            'business_license',
            'tax_id',
            'legal_document',
            'image',
        ]
        widgets = {
            'business_address': forms.Textarea(attrs={'rows': 3}),
            'warrantyinfo': forms.Textarea(attrs={'rows': 5}),
            'business_type': forms.Select(attrs={'class': 'form-control'}),
            'selling_category': forms.Select(attrs={'class': 'form-control'}),
            'currency_code': forms.Select(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        """Save vendor instance
        
        Note: currency_symbol is a computed property derived from currency_code,
        so no manual handling is needed here. It's automatically calculated when accessed.
        """
        vendor = super().save(commit=commit)
        return vendor

    def clean_business_name(self):
        businessname = self.cleaned_data.get('business_name')
        if businessname is not None:
            # Strip whitespace to handle edge cases
            businessname_stripped = businessname.strip()
            # Check for empty or whitespace-only strings
            if len(businessname_stripped) == 0:
                raise forms.ValidationError("Business name cannot be empty.")
            # Require at least 2 words for full business name (must match NIN and Bank records)
            words = businessname_stripped.split()
            if len(words) < 2:
                raise forms.ValidationError("Please enter your full business name as it appears on your ID or official records (at least 2 words required).")
            return businessname_stripped
        return businessname

class CustomSocialSignupForm(SignupForm):
    # This form is injected into the Google Signup flow
    birth_date = forms.DateField(
        label="Date of Birth",
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="You must be at least 15 years old to register."
    )

    # 1. Add the Gender Field exactly like your standard registerForm
    gender = forms.ChoiceField(
        choices=Customer.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Gender",
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'email' in self.fields:
            del self.fields['email']

    def clean_birth_date(self):
        dob = self.cleaned_data['birth_date']
        today = date.today()
        # Calculate age
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
        if age < 15:
            raise forms.ValidationError("You must be at least 15 years old to use Luxa.ng.")
        
        return dob

    def save(self, request):
        user = super().save(request)
        
        # 2. Check if a Customer profile exists, or create one
        customer, created = Customer.objects.get_or_create(user_account=user, defaults={'email': user.email})
        
        # 3. Save the birth date to the CUSTOMER profile
        customer.date_of_birth = self.cleaned_data['birth_date']
        customer.gender = self.cleaned_data['gender']
        customer.save()

# FORM FOR PASSWORD RESET WITH EMAIL VALIDATION
class EmailCheckingPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data.get('email')
        User = get_user_model()
        
        # Check if a user with this email exists and is active
        if not User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError("We couldn't find an account with that email address.")
            
        return email

