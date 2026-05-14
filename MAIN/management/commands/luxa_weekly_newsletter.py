from django.core.management.base import BaseCommand
from django.core.mail import get_connection, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from MAIN.models import Customer
import time

class Command(BaseCommand):
    help = 'Sends personalized weekly newsletter to all registered customers'

    def handle(self, *args, **kwargs):
        self.stdout.write("Gathering customers...")
        
        # 1. Fetch customers and pre-fetch the KYC profile to avoid database "N+1" overhead
        customers = Customer.objects.filter(
            user_account__is_active=True
        ).select_related('user_account', 'kyc_profile')
        
        if not customers.exists():
            self.stdout.write(self.style.WARNING("No customers found."))
            return

        subject = "Weekly Luxa Updates! 💎"
        
        # 2. Open a single persistent connection
        connection = get_connection()
        connection.open()

        messages = []
        count = 0

        for customer in customers:
            email = customer.user_account.email
            if not email:
                continue

            # --- NEW: INDIVIDUAL KYC LOGIC ---
            # Replicates the logic from your views
            try:
                # Assuming the relationship name is 'kyc_profile'
                kyc_status = customer.kyc_profile.status 
            except AttributeError:
                kyc_status = 'NONE'

            # --- NEW: RENDER PER CUSTOMER ---
            # This ensures the {% if kyc_status %} check works for each person
            html_content = render_to_string('MAIN/emails/weekly_newsletter.html', {
                'preview_text': 'Check out what is new this week!',
                'customer_name': customer.user_account.first_name or "Valued Member",
                'kyc_status': kyc_status  # The template now sees this!
            })
            text_content = strip_tags(html_content)

            msg = EmailMultiAlternatives(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                connection=connection
            )
            msg.attach_alternative(html_content, "text/html")
            messages.append(msg)
            count += 1
            
            # Batch sending (50 at a time)
            if len(messages) >= 50:
                connection.send_messages(messages)
                messages = []
                self.stdout.write(f"Sent batch of 50...")
                time.sleep(1) 

        # Send remaining messages
        if messages:
            connection.send_messages(messages)
            
        connection.close()
        self.stdout.write(self.style.SUCCESS(f"Successfully sent newsletter to {count} customers."))
