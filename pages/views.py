from django.shortcuts import render
from MAIN.models import (
    Product, Vendor, Category, Customer, Order, OrderItem,
    Cart, CartItem, Wishlist, WishlistItem, Notification, ProductVariant,
    LUXAOrder, DraftOrder, DraftOrderItem, EligibilityStagingArea, MasterOrder, 
    KYCVerification
)
from MAIN.constants import DEFAULT_CURRENCY_CODE, DEFAULT_CURRENCY_SYMBOL


# Create your views here.
def about(request):
    featured_products = Product.objects.filter(
        is_featured=True, 
        is_available=True
    ).order_by('?')[:20]
    featured_vendors = Vendor.objects.filter(is_verified=True)[:6]
    categories = Category.objects.filter(is_active=True, parent__isnull=True)
    
    context = {
        'featured_products': featured_products,
        'featured_vendors': featured_vendors,
        'categories': categories,
        'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
    }
    return render(request, "pages/about.html",context)

def contact(request):
    return render(request, "pages/contact.html")

def privacy(request):
    return render(request, "pages/privacy.html")

def terms(request):
    return render(request, "pages/terms.html")

def help(request):
    return render(request, "pages/help.html")

def ordertrack(request):
    return render(request, "pages/ordertrack.html")

def returns(request):
    return render(request, "pages/returns.html")

def size(request):
    return render(request, "pages/size.html")

def ship(request):
    return render(request, "pages/ship.html")

def faq(request):
    return render(request, "pages/faq.html")

def vendag(request):
    return render(request, "pages/vendoragreement.html")
