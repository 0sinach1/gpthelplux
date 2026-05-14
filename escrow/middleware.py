class WalletSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Define paths that KEEP the wallet unlocked
        secure_paths = [
            '/escrow/',       
            '/wallet/',        
            '/api/withdraw/',  
        ]

        # 2. Define paths to IGNORE (Don't lock, but don't count as "secure" either)
        ignored_paths = [
            '/static/', 
            '/media/', 
            '/api/',
            '/favicon.ico',
            '/.well-known/',
            '/notification/',
            '/__debug__/', # If you use Django Debug Toolbar
        ]

        # 3. Check status
        is_unlocked = request.session.get('wallet_unlocked', False)
        
        # Check if current path matches any list
        on_secure_page = any(request.path.startswith(p) for p in secure_paths)
        is_ignored_request = any(request.path.startswith(p) for p in ignored_paths)

        # LOGIC:
        # If unlocked...
        # AND NOT on a secure page...
        # AND the request is NOT just a background image/css file...
        # -> THEN Lock it.
        if is_unlocked and not on_secure_page and not is_ignored_request:
            request.session['wallet_unlocked'] = False
            # print(f"🔒 Wallet locked. User went to: {request.path}")

        response = self.get_response(request)
        return response