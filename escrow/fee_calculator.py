"""
Luxa Platform Fee Calculator

This module handles calculation of:
1. Delivery fees - ₦250 per vendor in an order
2. Luxa cut (platform service fee) - Tiered percentage based on order amount

Fee Tiers:
- ₦1,000 - ₦5,000: 10%
- ₦5,001 - ₦50,000: 8%
- ₦50,001 - ₦200,000: 5%
- ₦200,001+: 4%
"""

from decimal import Decimal, ROUND_HALF_UP

# Base delivery fee per vendor
BASE_DELIVERY_FEE = Decimal('250.00')

# Luxa cut tiers - sorted from highest to lowest threshold
# Format: (minimum_amount, percentage_as_decimal)
LUXA_CUT_TIERS = [
    (Decimal('200000.01'), Decimal('0.04')),  # ₦200,000.01+ = 4%
    (Decimal('50000.01'), Decimal('0.05')),   # ₦50,000.01 - ₦200,000 = 5%
    (Decimal('5000.01'), Decimal('0.08')),    # ₦5,000.01 - ₦50,000 = 8%
    (Decimal('1000.00'), Decimal('0.10')),    # ₦1,000 - ₦5,000 = 10%
]

# Default percentage for amounts below ₦1,000
DEFAULT_PERCENTAGE = Decimal('0.10')


def calculate_luxa_cut_percentage(amount):
    """
    Returns the Luxa cut percentage based on the amount tier.
    
    Args:
        amount: Decimal amount to calculate percentage for
        
    Returns:
        Decimal: The percentage as a decimal (e.g., 0.10 for 10%)
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    for threshold, percentage in LUXA_CUT_TIERS:
        if amount >= threshold:
            return percentage
    
    return DEFAULT_PERCENTAGE


def calculate_delivery_fee(vendor_count):
    return BASE_DELIVERY_FEE


def calculate_vendor_payout(subtotal):
    """
    Calculate the vendor's payout after Luxa cut deduction.
    
    Args:
        subtotal: Decimal amount of the order subtotal (product total for this vendor)
        
    Returns:
        tuple: (vendor_payout, luxa_cut_amount, luxa_cut_percentage_display)
            - vendor_payout: Amount vendor receives after deductions
            - luxa_cut_amount: Amount deducted as platform fee
            - luxa_cut_percentage_display: Percentage as whole number (e.g., 10 for 10%)
    """
    if not isinstance(subtotal, Decimal):
        subtotal = Decimal(str(subtotal))
    
    # Get the percentage for this amount tier
    percentage = calculate_luxa_cut_percentage(subtotal)
    
    # Calculate the Luxa cut amount
    luxa_cut_amount = (subtotal * percentage).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # Calculate vendor payout
    vendor_payout = subtotal - luxa_cut_amount
    
    # Convert percentage to display format (e.g., 0.10 -> 10)
    luxa_cut_percentage_display = (percentage * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return vendor_payout, luxa_cut_amount, luxa_cut_percentage_display


def calculate_order_fees(subtotal, include_delivery=False):
    """
    Calculate fees for a sub-order.
    CHANGED: include_delivery defaults to False because vendors don't see fees anymore.
    """
    if not isinstance(subtotal, Decimal):
        subtotal = Decimal(str(subtotal))
    
    vendor_payout, luxa_cut_amount, luxa_cut_pct = calculate_vendor_payout(subtotal)
    
    # If this is a Sub-Order, delivery_fee is usually 0.
    delivery_fee = BASE_DELIVERY_FEE if include_delivery else Decimal('0.00')
    
    return {
        'subtotal': subtotal,
        'delivery_fee': delivery_fee,
        'luxa_cut_percentage': luxa_cut_pct,
        'luxa_cut_amount': luxa_cut_amount,
        'vendor_payout': vendor_payout,
        'customer_total': subtotal + delivery_fee,
    }


def get_fee_tier_info(amount):
    
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    percentage = calculate_luxa_cut_percentage(amount)
    pct_display = int(percentage * 100)
    
    # Determine tier name and next threshold
    if amount >= Decimal('200000.01'):
        tier_name = "Premium (₦200k+)"
        next_threshold = None
    elif amount >= Decimal('50000.01'):
        tier_name = "Gold (₦50k - ₦200k)"
        next_threshold = Decimal('200000.01')
    elif amount >= Decimal('5000.01'):
        tier_name = "Silver (₦5k - ₦50k)"
        next_threshold = Decimal('50000.01')
    else:
        tier_name = "Standard (up to ₦5k)"
        next_threshold = Decimal('5000.01')
    
    return {
        'percentage': pct_display,
        'tier_name': tier_name,
        'next_tier_threshold': next_threshold,
    }
