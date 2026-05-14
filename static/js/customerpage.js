// JS FOR CUSTOMERPAGE.HTML

document.addEventListener("DOMContentLoaded", () => {
    const items = document.querySelectorAll('.menu li[data-target]');
    let activeItem = document.querySelector('.menu .active');
    let activePanel = document.querySelector('.detpanel.active');

    items.forEach(item => {

        item.addEventListener('click', () => {
            if (item === activeItem) return;

            // Switch active item
            activeItem?.classList.remove('active');
            item.classList.add('active');
            activeItem = item; // Update reference

             // Switch panel
            activePanel?.classList.remove('active', 'fade-in');
            const targetPanel = document.getElementById(item.dataset.target);
            targetPanel.classList.add('active');

            // Trigger animation (reflow trick)
            void targetPanel.offsetWidth;
            targetPanel.classList.add('fade-in');
            
            activePanel = targetPanel;
        });
    });

    const tabs = document.querySelectorAll('#type span');
    const uncompleted = document.querySelector('#orders .uncompleted');
    const completed = document.querySelector('#orders .completed');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active-type'));
            tab.classList.add('active-type');

            if (tab.textContent === 'Ongoing/Delivered') {
                uncompleted.style.display = 'flex';
                completed.style.display = 'none';
            } else {
                uncompleted.style.display = 'none';
                completed.style.display = 'flex';
            }
        });
    });


    // --- Order Panel Filtering Logic ---
    const mainTabs = document.querySelectorAll('.op-tab');
    const subTabs = document.querySelectorAll('.op-sub-tab');
    const subTabsContainer = document.getElementById('pending-sub-tabs');
    const orderCards = document.querySelectorAll('.op-card');
    const emptyState = document.getElementById('op-empty-state');

    let currentMain = 'pending';
    let currentSub = 'all';

    function runOrderFilter() {
        let visibleCount = 0;
        
        orderCards.forEach(card => {
            const cardMain = card.getAttribute('data-main');
            const cardSub = card.getAttribute('data-sub');
            let showCard = false;

            if (currentMain === 'all') {
                showCard = true; // Show everything on "All Orders"
            } else if (currentMain === cardMain) {
                if (currentMain === 'pending') {
                    // If Pending is active, respect the sub-tab filter
                    if (currentSub === 'all' || currentSub === cardSub) {
                        showCard = true;
                    }
                } else {
                    // For Delivered/Cancelled, just show matching main category
                    showCard = true; 
                }
            }

            card.style.display = showCard ? 'block' : 'none';
            if (showCard) visibleCount++;
        });

        // Toggle Empty State Message
        emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    // Main Tab Click Event
    mainTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update Active Class
            mainTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Set state variables
            currentMain = tab.getAttribute('data-filter-main');
            
            // Show/Hide subtabs container
            if (currentMain === 'pending') {
                subTabsContainer.style.display = 'block';
            } else {
                subTabsContainer.style.display = 'none';
            }
            
            runOrderFilter();
        });
    });

    // Sub Tab Click Event
    subTabs.forEach(subTab => {
        subTab.addEventListener('click', () => {
            // Update Active Class
            subTabs.forEach(t => t.classList.remove('active'));
            subTab.classList.add('active');
            
            // Set state variable
            currentSub = subTab.getAttribute('data-filter-sub');
            
            runOrderFilter();
        });
    });

    // Run once on load to ensure proper initial state
    runOrderFilter();

    // --- Wishlist Add to Cart Logic ---
    
    // 1. Single Item Add to Cart
    document.querySelectorAll('.add-to-cart-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const productId = this.getAttribute('data-product-id');
            const originalText = this.innerHTML;
            
            // UI feedback
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Adding...';
            this.disabled = true;

            fetch(`/cart/add/${productId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success || data.message) {
                    this.innerHTML = '<i class="fas fa-check"></i> Added';
                    this.style.background = '#dcfce7';
                    this.style.color = '#16a34a';
                } else {
                    alert(data.error || 'Failed to add item to cart');
                    this.innerHTML = originalText;
                    this.disabled = false;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred');
                this.innerHTML = originalText;
                this.disabled = false;
            });
        });
    });

    // 2. Add All to Cart
    const addAllBtn = document.getElementById('add-all-to-cart-btn');
    if (addAllBtn) {
        addAllBtn.addEventListener('click', async function() {
            // Grab all product IDs on the page
            const buttons = document.querySelectorAll('.add-to-cart-btn');
            if (buttons.length === 0) return;

            const originalText = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Adding All...';
            this.disabled = true;

            let successCount = 0;

            // Process sequentially to not overload the server
            for (let btn of buttons) {
                const productId = btn.getAttribute('data-product-id');
                try {
                    const response = await fetch(`/cart/add/${productId}/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken'),
                            'Content-Type': 'application/json'
                        }
                    });
                    if (response.ok) {
                        successCount++;
                        // Visual update on the individual button
                        btn.innerHTML = '<i class="fas fa-check"></i> Added';
                        btn.style.background = '#dcfce7';
                        btn.style.color = '#16a34a';
                        btn.disabled = true;
                    }
                } catch (error) {
                    console.error('Failed to add product:', productId, error);
                }
            }

            this.innerHTML = `<i class="fas fa-check"></i> Added ${successCount} Items`;
            
            // Reset button text after 3 seconds
            setTimeout(() => {
                this.innerHTML = originalText;
                this.disabled = false;
            }, 3000);
        });
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

})
