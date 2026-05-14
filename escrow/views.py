from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.urls import reverse
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.conf import settings
from decimal import Decimal, InvalidOperation
import json
from django.views.decorators.csrf import csrf_exempt
import hmac
import hashlib
import uuid
from django.contrib import messages
from .models import Wallet, WalletTransaction, WalletSecurity, BankAccount
from .paystack import Paystack
from .forms import WalletPinForm, ChangePinForm
from escrow import paystack

@login_required
@require_POST
def withdraw_funds(request):
    """
    Endpoint for users to withdraw their 'Available Balance'.
    Applies withdrawal fees (₦25 for <10k, ₦50 for >=10k), but is FREE for COURIER_ADVANCE.
    """
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount')))
        wallet_type = data.get('wallet_type', 'CUSTOMER')
        idempotency_key = data.get('idempotency_key') 
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid amount or data format'}, status=400)
    
    # 1. IDEMPOTENCY CHECK (Fast Fail)
    if idempotency_key and WalletTransaction.objects.filter(idempotency_key=idempotency_key).exists():
        return JsonResponse({'error': 'Transaction already processed. Please refresh.'}, status=409)

    # --- NEW: CONDITIONAL FEE CALCULATION ---
    if wallet_type == 'COURIER_ADVANCE':
        fee = Decimal('0.00')
    else:
        fee = Decimal('15.00') if amount < Decimal('5000.00') else Decimal('30.00')
        
    total_deduction = amount + fee

    # Create the strict, globally unique reference for Paystack
    import uuid
    transfer_reference = idempotency_key if idempotency_key else f"wdr_{request.user.id}_{uuid.uuid4().hex[:10]}"

    paystack = Paystack() 

    # ==========================================
    # PHASE 1: SECURE LOCAL FUNDS (ATOMIC)
    # ==========================================
    with transaction.atomic():
        try:
            wallet = Wallet.objects.select_for_update().get(
                user=request.user, 
                wallet_type=wallet_type
            )
        except Wallet.DoesNotExist:
            return JsonResponse({'error': 'Wallet not found'}, status=404)

        if wallet.available_balance < total_deduction:
            return JsonResponse({'error': f'Insufficient funds. You need ₦{total_deduction} to cover the withdrawal and fees.'}, status=400)
        
        # Advance Wallet Sync
        if wallet.wallet_type == 'COURIER_ADVANCE':
            main_wallet = Wallet.objects.filter(user=request.user, wallet_type='COURIER').first()
            if main_wallet and main_wallet.paystack_recipient_code:
                wallet.paystack_recipient_code = main_wallet.paystack_recipient_code
                wallet.save(update_fields=['paystack_recipient_code'])

        if not wallet.paystack_recipient_code:
            return JsonResponse({'error': 'No bank account linked. Please link a payout account first.'}, status=400)

        # DEDUCT BALANCE PERMANENTLY (Principal + Fee)
        wallet.available_balance -= total_deduction
        wallet.save(update_fields=['available_balance'])

        fee_text = f" (Includes ₦{fee} transfer fee)" if fee > 0 else ""

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='WITHDRAWAL',
            amount=-total_deduction,
            running_balance=wallet.available_balance,
            reference=transfer_reference, 
            description=f"Withdrawal to Bank{fee_text}",
            idempotency_key=idempotency_key,
        )

    # ==========================================
    # PHASE 2: TALK TO THE OUTSIDE WORLD (NON-ATOMIC)
    # ==========================================
    amount_kobo = int(amount * 100)
    
    response = paystack.initiate_transfer(
        amount_kobo=amount_kobo,
        recipient_code=wallet.paystack_recipient_code,
        reason="Withdrawal from Luxa",
        reference=transfer_reference
    )

    # ==========================================
    # PHASE 3: HANDLE REALITY
    # ==========================================
    if response['api_state'] == "FAILED":
        with transaction.atomic():
            refund_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
            
            refund_wallet.available_balance += total_deduction
            refund_wallet.save(update_fields=['available_balance'])
            
            WalletTransaction.objects.create(
                wallet=refund_wallet,
                transaction_type='REFUND',
                amount=total_deduction,
                running_balance=refund_wallet.available_balance,
                reference=f"REF_{transfer_reference}",
                description=f"Auto-Refund: {response['message']}"
            )
            
            # Clawback the fee from the Admin Wallet
            if fee > Decimal('0.00'):
                admin_wallet = Wallet.objects.select_for_update().filter(wallet_type='ADMIN').first()
                if admin_wallet:
                    admin_wallet.available_balance -= fee
                    admin_wallet.save(update_fields=['available_balance'])
                    
                    WalletTransaction.objects.create(
                        wallet=admin_wallet,
                        transaction_type='DEBIT',
                        amount=-fee,
                        running_balance=admin_wallet.available_balance,
                        reference=f"REF-FEE-{transfer_reference}",
                        description="Withdrawal Fee Reversed (Failed Transfer)"
                    )
            
        return JsonResponse({'error': f"Withdrawal Failed: {response['message']}"}, status=400)

    elif response['api_state'] == "UNKNOWN":
        return JsonResponse({
            'message': 'Withdrawal is taking longer than expected. It is currently processing.',
            'balance': float(wallet.available_balance)
        }, status=202) 

    # Success
    bank_details = "Bank Account"
    try:
        from .models import BankAccount
        active_bank = BankAccount.objects.filter(paystack_recipient_code=wallet.paystack_recipient_code).first()
        if active_bank:
            bank_details = f"{active_bank.bank_name} ({active_bank.account_number})"
    except:
        pass

    return JsonResponse({
        'message': 'Withdrawal processed successfully', 
        'balance': float(wallet.available_balance),
        'destination': bank_details
    })

@login_required
@require_POST
def link_bank_account(request):
    try:
        data = json.loads(request.body)
        account_number = str(data.get('account_number', '')).strip()
        bank_code = str(data.get('bank_code', '')).strip()
        # Get the name selected by the user in the dropdown
        frontend_bank_name = data.get('bank_name', '').strip()
        
        wallet_type = data.get('wallet_type', 'CUSTOMER')

        # Debug: Check what is arriving
        print(f"DEBUG: Linking {frontend_bank_name} ({bank_code}) - {account_number}")

        wallet = Wallet.objects.get(user=request.user, wallet_type=wallet_type)
        paystack = Paystack()

        # --- 1. TEST MODE BYPASS ---
        # If user enters the standard Paystack test number, we SKIP API verification
        if account_number == "00012345670": # Added '0' to the end to disable test mode [field only accepts 10 digits]
            print(f"⚠️ TEST MODE DETECTED: Skipping verification for {account_number}")
            account_name = "TEST BANK ACCOUNT"
            # We mock a recipient code so we don't need to call the API
            recipient_code = f"RCP_TEST_{uuid.uuid4().hex[:8].upper()}"
        else:
            # --- REAL VERIFICATION ---
            account_details = paystack.verify_account_number(account_number, bank_code)
            
            if not account_details:
                print(f"❌ Verification Failed for {account_number} at {bank_code}")
                return JsonResponse({
                    'error': 'Verification failed. Please check the account number and bank.'
                }, status=400)
            
            account_name = account_details.get('account_name', 'Unknown Name')

            # Create Real Recipient
            recipient_code = paystack.create_transfer_recipient(
                name=account_name,
                account_number=account_number,
                bank_code=bank_code
            )

            if not recipient_code:
                return JsonResponse({'error': 'Paystack rejected recipient creation.'}, status=500)
        
        # Use the name user selected if Paystack didn't return one
        final_bank_name = frontend_bank_name if frontend_bank_name else "Unknown Bank"

        # 3. SAVE TO DATABASE
        with transaction.atomic():
            # Use get_or_create to handle duplicates gracefully
            bank_acc, created = BankAccount.objects.get_or_create(
                wallet=wallet,
                account_number=account_number,
                bank_code=bank_code,
                defaults={
                    'account_name': account_name,
                    'bank_name': final_bank_name,
                    'paystack_recipient_code': recipient_code,
                    'is_default': False 
                }
            )

            # ALWAYS update these fields to fix "Unknown Bank" on existing records
            bank_acc.account_name = account_name
            bank_acc.bank_name = final_bank_name 
            bank_acc.paystack_recipient_code = recipient_code
            
            # If this is the only account, make it default
            if BankAccount.objects.filter(wallet=wallet).count() == 1:
                bank_acc.is_default = True
                wallet.paystack_recipient_code = recipient_code
                wallet.save()
            
            bank_acc.save()

        return JsonResponse({
            'success': True,
            'message': 'Bank account saved successfully!', 
            'account_name': account_name
        })

    except Wallet.DoesNotExist:
        return JsonResponse({'error': 'Wallet not found.'}, status=404)
    except Exception as e:
        print(f"SERVER ERROR: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def delete_bank_account(request):
    """
    Safely deletes a bank account. Prevents deleting the default account.
    """
    import json
    data = json.loads(request.body)
    bank_id = data.get('bank_id')
    
    try:
        # Security: Ensure the bank account belongs to one of the user's wallets
        bank_acc = BankAccount.objects.get(id=bank_id, wallet__user=request.user)
        
        if not request.user.courier_profile:
            if bank_acc.is_default:
                return JsonResponse({'error': 'Cannot delete the active account. Please select another account as "In Use" first.'}, status=400)
        else:
            bank_acc.delete()
        
        bank_acc.delete()
        return JsonResponse({'success': True, 'message': 'Account removed successfully.'})
        
    except BankAccount.DoesNotExist:
        return JsonResponse({'error': 'Account not found.'}, status=404)
    
@login_required
@require_POST
def set_active_bank(request):
    """
    Sets a specific BankAccount as the default ('In Use') for the wallet.
    Updates the wallet's paystack_recipient_code to match.
    """
    import json
    data = json.loads(request.body)
    bank_id = data.get('bank_id')
    wallet_type = data.get('wallet_type', 'CUSTOMER')

    try:
        with transaction.atomic():
            # 1. Get the Wallet and the specific Bank Account
            wallet = Wallet.objects.get(user=request.user, wallet_type=wallet_type)
            target_bank = BankAccount.objects.get(id=bank_id, wallet=wallet)

            # 2. Reset all accounts for this wallet to is_default=False
            BankAccount.objects.filter(wallet=wallet).update(is_default=False)

            # 3. Set the target bank to is_default=True
            target_bank.is_default = True
            target_bank.save()

            # 4. CRITICAL: Update the Wallet's main recipient code
            # This ensures the withdraw_funds view uses THIS account next time.
            wallet.paystack_recipient_code = target_bank.paystack_recipient_code
            wallet.save()

            return JsonResponse({'success': True, 'message': f'Active account changed to {target_bank.bank_name}'})

    except (Wallet.DoesNotExist, BankAccount.DoesNotExist):
        return JsonResponse({'error': 'Bank account or wallet not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# TO HANDLE DEPOSITS
@csrf_exempt 
def paystack_webhook(request):
    """
    Listens for 'charge.success' from Paystack and funds the wallet.
    """
    # 1. VERIFY THE SIGNATURE (Security Check)
    secret_key = settings.PAYSTACK_SECRET_KEY
    paystack_signature = request.headers.get('x-paystack-signature')
    
    if not paystack_signature:
        return HttpResponse(status=400) 

    computed_signature = hmac.new(
        key=secret_key.encode('utf-8'),
        msg=request.body,
        digestmod=hashlib.sha512
    ).hexdigest()

    if computed_signature != paystack_signature:
        return HttpResponse(status=400) 

    # 2. PROCESS THE EVENT
    payload = json.loads(request.body)
    event_type = payload.get('event')
    data = payload.get('data', {})

    if event_type == 'charge.success':
        reference = data.get('reference')
        email = data.get('customer', {}).get('email')
        
        # --- SECURE FEE HANDLING LOGIC (DEPOSITS) ---
        amount_paid_kobo = data.get('amount', 0) 
        gross_amount_naira = Decimal(amount_paid_kobo) / 100
        
        # REVERSE-LOOKUP: Because Paystack charged (Deposit + Fee), we 
        # determine the required fee based on the Gross Amount brackets.
        if gross_amount_naira <= Decimal('5099.00'):
            platform_fee = Decimal('100.00')
        elif gross_amount_naira <= Decimal('10149.00'):
            platform_fee = Decimal('150.00')
        elif gross_amount_naira <= Decimal('15199.00'):
            platform_fee = Decimal('250.00')
        elif gross_amount_naira <= Decimal('20299.00'):
            platform_fee = Decimal('350.00')
        elif gross_amount_naira <= Decimal('25399.00'):
            platform_fee = Decimal('450.00')
        elif gross_amount_naira <= Decimal('30499.00'):
            platform_fee = Decimal('550.00')
        else:
            platform_fee = Decimal('650.00')

        # Calculate what actually goes into the wallet
        final_credit_naira = gross_amount_naira - platform_fee
        
        # Failsafe: If someone maliciously manipulates the JS to pay 50 Naira, 
        # the fee absorbs it all and they get credited 0.
        if final_credit_naira <= 0:
            final_credit_naira = Decimal('0.00')
        # --------------------------------------------

        # Idempotency Check
        if WalletTransaction.objects.filter(reference=reference).exists():
            return HttpResponse(status=200)

        # Credit the Wallet
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(email=email)
            with transaction.atomic():
                wallet, created = Wallet.objects.get_or_create(
                    user=user, 
                    wallet_type=Wallet.WalletType.CUSTOMER
                )
                if not created:
                    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                
                # CREDIT THE FULL AMOUNT
                wallet.available_balance += final_credit_naira
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='DEPOSIT',
                    amount=final_credit_naira,
                    running_balance=wallet.available_balance,
                    reference=reference,
                    description="Wallet Deposit" 
                )
                
            # Log it so you know you paid a fee
            print(f"💰 Wallet Funded: ₦{final_credit_naira} (Platform absorbed fee: ₦{platform_fee})")
            
        except User.DoesNotExist:
            print(f"⚠️ Unknown User: {email}")

    if event_type in ['transfer.failed', 'transfer.reversed']:
        # This happens if a bank rejects the money hours later, 
        # or if an UNKNOWN timeout eventually fails.
        reference = data.get('reference')
        amount_kobo = data.get('amount', 0)
        refund_amount = Decimal(amount_kobo) / 100
        reason = data.get('reason', 'Bank rejected transfer')

        try:
            # Find the original withdrawal transaction
            original_tx = WalletTransaction.objects.get(reference=reference, transaction_type='WITHDRAWAL')
            wallet = original_tx.wallet
            
            # Make sure we haven't already refunded this exact reference!
            refund_ref = f"REF_{reference}"
            if not WalletTransaction.objects.filter(reference=refund_ref).exists():
                
                # Safely refund the user
                with transaction.atomic():
                    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                    wallet.available_balance += refund_amount
                    wallet.save()
                    
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type='REFUND', 
                        amount=refund_amount,
                        running_balance=wallet.available_balance,
                        reference=refund_ref,
                        description=f"Auto-Refund: {reason}"
                    )
                print(f"🔄 Auto-Refunded ₦{refund_amount} for failed transfer {reference}")

        except WalletTransaction.DoesNotExist:
            print(f"⚠️ Could not find original withdrawal for reference: {reference}")

    return HttpResponse(status=200)

# View to handle wallet PIN creation and verification
@login_required
def validate_wallet_pin(request):
    """
    Intermediary page. Checks if user has a PIN.
    If No -> Ask to Create.
    If Yes -> Ask to Enter.
    """
    security, created = WalletSecurity.objects.get_or_create(user=request.user)
    
    # Logic: Is this a "Create PIN" or "Verify PIN" action?
    is_creation = (security.pin_hash == '') or created
    
    if request.method == 'POST':
        form = WalletPinForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data['pin']
            
            if is_creation:
                # SETTING NEW PIN
                security.set_pin(pin)
                # Mark session as unlocked
                request.session['wallet_unlocked'] = True
                return redirect('wallet_dashboard')
            else:
                # VERIFYING EXISTING PIN
                if security.check_pin(pin):
                    request.session['wallet_unlocked'] = True
                    # Reset failed attempts if any
                    security.failed_attempts = 0
                    security.save()
                    return redirect('wallet_dashboard')
                else:
                    security.failed_attempts += 1
                    security.save()
                    form.add_error('pin', 'Incorrect PIN.')
    else:
        form = WalletPinForm()

    context = {
        'form': form,
        'is_creation': is_creation
    }
    return render(request, 'escrow/security/wallet_pin.html', context)

# Request user to reset PIN via email link
@login_required
def request_pin_reset(request):
    """
    Step 1: User asks to reset PIN. We send an email with a signed token.
    """
    if request.method == 'POST':
        try:
            # 1. Generate Secure Token (Signed User ID)
            signer = TimestampSigner()
            token = signer.sign(request.user.id)
            
            # 2. Build Link
            reset_url = reverse('verify_pin_reset', args=[token])
            full_link = request.build_absolute_uri(reset_url)
            
            # 3. Send Email
            send_mail(
                subject="🔒 Reset Your Wallet PIN",
                message=(
                    f"Hi {request.user.first_name},\n\n"
                    f"You requested to reset your Luxa Wallet PIN.\n"
                    f"Click the link below to set a new PIN (valid for 15 minutes):\n\n"
                    f"{full_link}\n\n"
                    f"If you did not request this, please ignore this email.\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=True
            )
            return render(request, 'escrow/security/reset_email_sent.html')
            
        except Exception as e:
            return render(request, 'escrow/security/reset_email_sent.html', {'error': str(e)})

    # GET request shows the confirmation page
    return render(request, 'escrow/security/forgot_pin_confirm.html')

# Verify token and allow PIN reset
@login_required
def verify_pin_reset(request, token):
    """
    Step 2: User clicks email link. We validate token and allow new PIN entry.
    """
    signer = TimestampSigner()
    
    try:
        # 1. Unsign & Verify (Max Age: 15 minutes = 900 seconds)
        user_id = signer.unsign(token, max_age=900)
    except SignatureExpired:
        return render(request, 'escrow/security/pin_link_expired.html', {'reason': 'expired'})
    except BadSignature:
        return render(request, 'escrow/security/pin_link_expired.html', {'reason': 'invalid'})

    # 2. Security Check: Ensure the logged-in user matches the token
    # (Prevents User A from clicking User B's link to hijack)
    if str(request.user.id) != str(user_id):
        return HttpResponseForbidden("This reset link belongs to a different account.")

    # 3. Handle New PIN Submission
    if request.method == 'POST':
        form = WalletPinForm(request.POST)
        if form.is_valid():
            new_pin = form.cleaned_data['pin']
            
            # Update Security Model
            security, _ = WalletSecurity.objects.get_or_create(user=request.user)
            security.set_pin(new_pin)
            security.failed_attempts = 0 # Unlock if it was locked
            security.save()
            
            # Auto-unlock session
            request.session['wallet_unlocked'] = True
            
            # Redirect to dashboard with success message
            return redirect('wallet_dashboard')
    else:
        form = WalletPinForm()

    return render(request, 'escrow/security/reset_pin_form.html', {'form': form})

# Change pin while logged in
@login_required
def change_wallet_pin(request):
    # 1. MIDDLEWARE CHECK: Ensure session is unlocked
    if not request.session.get('wallet_unlocked', False):
        return redirect('validate_wallet_pin')

    security = request.user.wallet_security

    if request.method == 'POST':
        form = ChangePinForm(request.POST)
        if form.is_valid():
            old_pin = form.cleaned_data['old_pin']
            new_pin = form.cleaned_data['new_pin']

            # 2. Verify Old PIN
            if security.check_pin(old_pin):
                # 3. Set New PIN
                security.set_pin(new_pin)
                messages.success(request, "Security PIN updated successfully.")
                return redirect('wallet_dashboard')
            else:
                form.add_error('old_pin', "Incorrect current PIN.")
    else:
        form = ChangePinForm()

    return render(request, 'escrow/security/change_pin.html', {'form': form})

@login_required
def wallet_dashboard(request):
    # --- 1. PIN SECURITY CHECK ---
    if not request.session.get('wallet_unlocked', False):
        return redirect('validate_wallet_pin')

    # --- 2. DETERMINE WALLET TYPE ---
    view_param = request.GET.get('view')
    
    # Default
    wallet_type = Wallet.WalletType.CUSTOMER

    # Check Vendor
    if view_param == 'vendor' and hasattr(request.user, 'vendor_profile'):
        wallet_type = Wallet.WalletType.VENDOR
    
    # Check Courier (New Logic)
    elif view_param == 'courier' and hasattr(request.user, 'courier_profile'):
        wallet_type = Wallet.WalletType.COURIER

    # --- 3. FETCH WALLET ---
    wallet, _ = Wallet.objects.get_or_create(
        user=request.user, 
        wallet_type=wallet_type,
        defaults={'currency': 'NGN'}
    )
    
    transactions = wallet.transactions.all().order_by('-timestamp')[:50]

    # --- 4. COURIER SPECIFIC: Calculate Lifetime Earnings ---
    courier_lifetime_earnings = 0
    if wallet_type == Wallet.WalletType.COURIER:
        # We sum up all credit transactions related to deliveries
        earning_agg = wallet.transactions.filter(
            transaction_type='CREDIT',
            description__startswith='Delivery Earning'
        ).aggregate(Sum('amount'))
        
        courier_lifetime_earnings = earning_agg['amount__sum'] or 0

    context = {
        'wallet': wallet,
        'transactions': transactions,
        'wallet_type': wallet_type,
        'courier_lifetime_earnings': courier_lifetime_earnings, # Pass to template
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
    }
    return render(request, 'escrow/wallet_dashboard.html', context)

@login_required
def escrow_management_dashboard(request):
    """
    Admin dashboard showing full escrow transaction flow.
    UPDATED: 
    - Delivery Fees are now calculated from MasterOrder (Global).
    - Luxa Cuts are calculated from Order (Per-Vendor).
    """
    # Check privileges
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Access Denied")
    
    # IMPORT MASTER ORDER
    from MAIN.models import Order, MasterOrder 
    
    # 1. FETCH DATA
    sub_orders = Order.objects.select_related('customer', 'vendor', 'master_order').order_by('-created_at')
    master_orders = MasterOrder.objects.filter(delivery_fee__gt=0).order_by('-created_at')

    # -------------------------------------------------------
    # PANEL 1: ORDER TRANSACTIONS (The Sub-Orders / Vendor Payouts)
    # -------------------------------------------------------
    # This shows the "Service Fee" revenue stream.
    order_transactions = []
    for order in sub_orders:
        order_transactions.append({
            'order_number': order.order_number,
            'order_id': order.id,
            'customer': order.customer.full_name,
            'vendor': order.vendor.business_name,
            'created_at': order.created_at,
            'status': order.get_status_display(),
            'payment_status': order.get_payment_status_display(),
            'subtotal': order.subtotal,
            
            # NOTE: Delivery fee is 0 here (it's on the Master). 
            # We display 0 to avoid confusion, or you could fetch order.master_order.delivery_fee 
            # but that would duplicate it visually if a master has 3 sub-orders.
            'delivery_fee': Decimal('0.00'), 
            
            'luxa_cut_percentage': order.luxa_cut_percentage if order.luxa_cut_percentage else Decimal('0.00'),
            'luxa_cut_amount': order.luxa_cut_amount if order.luxa_cut_amount else Decimal('0.00'),
            'customer_total': order.total, 
            'vendor_payout': order.vendor_payout if order.vendor_payout and order.vendor_payout > 0 else order.subtotal,
        })
    
    # -------------------------------------------------------
    # PANEL 2: DELIVERY FEES SUMMARY (Source: MasterOrder)
    # -------------------------------------------------------
    # Total balance from global delivery fees
    total_delivery_fees = MasterOrder.objects.aggregate(
        total=Sum('delivery_fee')
    )['total'] or Decimal('0.00')
    
    # Breakdown now lists Master Orders (The Receipts)
    delivery_fee_breakdown = master_orders.values(
        'public_order_id', # changed from order_number
        'id', 
        'delivery_fee', 
        'created_at', 
        'customer__first_name', 
        'customer__last_name'
    ).order_by('-created_at')
    
    # -------------------------------------------------------
    # PANEL 3: LUXA CUT SUMMARY (Source: Sub-Order)
    # -------------------------------------------------------
    # This remains unchanged because Service Fees are still per-vendor
    total_luxa_cut = Order.objects.aggregate(
        total=Sum('luxa_cut_amount')
    )['total'] or Decimal('0.00')
    
    luxa_cut_breakdown = sub_orders.filter(luxa_cut_amount__gt=0).values(
        'order_number', 'id', 'luxa_cut_amount', 'luxa_cut_percentage', 
        'subtotal', 'created_at', 'customer__first_name', 
        'customer__last_name', 'vendor__business_name'
    ).order_by('-created_at')
    
    context = {
        'order_transactions': order_transactions,
        'total_delivery_fees': total_delivery_fees,
        'delivery_fee_breakdown': delivery_fee_breakdown,
        'total_luxa_cut': total_luxa_cut,
        'luxa_cut_breakdown': luxa_cut_breakdown,
        'total_orders': sub_orders.count(),
        'total_platform_revenue': total_delivery_fees + total_luxa_cut,
    }
    
    return render(request, 'escrow/admin_dashboard.html', context)
    