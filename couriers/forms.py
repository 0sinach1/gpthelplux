from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms
from .models import Courier
from datetime import date
from luxa_crave.models import University_Profile

class courierRegForm(UserCreationForm):
    date_of_birth = forms.DateField(
        widget = forms.DateInput(attrs={'type': 'date'}),
        label="Date of Birth",
        required=True
    )
    gender = forms.ChoiceField(
        choices=Courier.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Gender",
        required=True
    )
    university_profile = forms.ModelChoiceField(
        queryset=University_Profile.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select your University", # Adds a nice placeholder at the top
        label="Choose your Working University",
        required=True
    )
    photo = forms.ImageField(
        required=True,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        label="Profile Photo"
    )
    # --- NEW FIELDS ---
    social_media_platform = forms.ChoiceField(
        choices=[('', 'Select Platform...')] + Courier.SOCIALS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Social Media Platform",
        required=True
    )
    social_media_handle = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@yourhandle or Phone Number'}),
        label="Social Media Handle",
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
    

    # ---NITTY-GRITTY INJECTION ---

# Form to upgrade to luxa student courier
class CourierUpgradeForm(forms.ModelForm):
    """Form for existing customers to upgrade to a Courier account."""
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Date of Birth",
        required=True
    )
    gender = forms.ChoiceField(
        choices=Courier.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Gender",
        required=True
    )
    university_profile = forms.ModelChoiceField(
        queryset=University_Profile.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select your University",
        label="Choose your Working University",
        required=True
    )
    photo = forms.ImageField(
        required=True,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        label="Profile Photo"
    )
    # --- NEW FIELDS ---
    social_media_platform = forms.ChoiceField(
        choices=[('', 'Select Platform...')] + Courier.SOCIALS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Social Media Platform",
        required=True
    )
    social_media_handle = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@yourhandle or Phone Number'}),
        label="Social Media Handle",
        required=True
    )

    class Meta:
        model = Courier
        fields = ['date_of_birth', 'gender', 'photo', 'social_media_platform', 'social_media_handle']

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        today = date.today()

        if dob is None:
            raise forms.ValidationError("Please enter your date of birth.")

        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 15:
            raise forms.ValidationError("You must be at least 15 years old to register.")

        return dob

class DailyAccessKeyForm(forms.Form):
    """
    The 'Ignition' form. 
    Couriers use this every morning to enter the 5 AM office key.
    """
    daily_key = forms.CharField(
        max_length=12, 
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter Office Key',
            'class': 'form-control',
            'style': 'text-transform:uppercase'
        }),
        label="Daily Activation Key"
    )
    