from django import forms

# Input pin form
class WalletPinForm(forms.Form):
    pin = forms.CharField(
        max_length=4, 
        min_length=4, 
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Input 4-digit PIN',
            'style': 'text-align: center; font-size: 20px; letter-spacing: 10px;',
            'inputmode': 'numeric',
            'pattern': '[0-9]*'
        }),
        label="Enter 4-Digit PIN"
    )

    def clean_pin(self):
        pin = self.cleaned_data.get('pin')
        if not pin.isdigit():
            raise forms.ValidationError("PIN must contain only numbers.")
        return pin
    
# Change PIN Form
class ChangePinForm(forms.Form):
    old_pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'pin-input-field', 
            'maxlength': '4', 
            'placeholder': 'Old PIN', 
            'inputmode': 'numeric',
            'style': 'text-align: center; font-size: 20px; letter-spacing: 10px;'
        }),
        label="Current PIN", max_length=4, required=True
    )
    
    new_pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'pin-input-field', 
            'maxlength': '4', 
            'placeholder': 'New PIN', 
            'inputmode': 'numeric',
            'style': 'text-align: center; font-size: 20px; letter-spacing: 10px;'
        }),
        label="New PIN", max_length=4, required=True
    )

    # NEW: Confirmation Field
    confirm_new_pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'pin-input-field', 
            'maxlength': '4', 
            'placeholder': 'Confirm New PIN', 
            'inputmode': 'numeric',
            'style': 'text-align: center; font-size: 20px; letter-spacing: 10px;'
        }),
        label="Confirm New PIN", max_length=4, required=True
    )

    def clean(self):
        cleaned_data = super().clean()
        old = cleaned_data.get('old_pin')
        new = cleaned_data.get('new_pin')
        confirm = cleaned_data.get('confirm_new_pin')

        # 1. Check if Old matches New (Prevention)
        if old and new and old == new:
            raise forms.ValidationError("New PIN cannot be the same as the old one.")
        
        # 2. Check Digits
        if new and (not new.isdigit() or len(new) != 4):
            raise forms.ValidationError("New PIN must be 4 digits.")

        # 3. Check Confirmation (Safety)
        if new and confirm and new != confirm:
            raise forms.ValidationError("The two PIN fields do not match.")
            
        return cleaned_data