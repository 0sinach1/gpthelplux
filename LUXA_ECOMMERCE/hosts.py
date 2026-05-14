from django_hosts import patterns, host

host_patterns = patterns('',
    # 1. The Default Site (luxa.ng)
    # Routes to your main LUXA_ECOMMERCE/urls.py
    host(r'www', 'LUXA_ECOMMERCE.urls', name='www'),
    host(r'', 'LUXA_ECOMMERCE.urls', name='default'),

    # 2. The Crave Subdomain (crave.luxa.ng)
    # Routes traffic DIRECTLY to your luxa_crave app's urls.py
    host(r'crave', 'luxa_crave.urls', name='crave'),
)
