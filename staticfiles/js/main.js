


document.addEventListener("DOMContentLoaded", () => {

// ---- JS for base.html ----

    const products = [
        "iPhone 15 Pro",
        "iPhone 14 Case",
        "Samsung Galaxy S24",
        "MacBook Air M2",
        "Dell XPS 13",
        "Sony WH-1000XM5",
        "Nike Air Max",
        "Adidas Ultraboost"
    ];

    const searchBar = document.getElementById("search");
    const suggestionsBox = document.getElementById("suggestions");

    searchBar.addEventListener("input", function() {
        const query = this.value.toLowerCase();
        suggestionsBox.innerHTML = "";

        if (query.length === 0) {
            suggestionsBox.classList.add("hidden");
            return;
        }

        const matches = products.filter(item =>
            item.toLowerCase().includes(query)
        );

        if (matches.length > 0) {
            suggestionsBox.classList.remove("hidden");
            matches.forEach(match => {
                const div = document.createElement("div");
                div.textContent = match;
                div.onclick = () => {
                    searchBar.value = match;
                    suggestionsBox.classList.add("hidden");
                };
                suggestionsBox.appendChild(div);
            });
        } else {
            suggestionsBox.classList.add("hidden");
        }
    });


// ---- JS for index.html ----
    const vendorcont = document.getElementById("venstuff")

// ---- JS for cart.html -----

    const toggleBtn = document.getElementById("toggleDiscount");
    const discountPanel = document.querySelector(".discount");

    toggleBtn.addEventListener("click", () => {
        discountPanel.classList.toggle("show");
        toggleBtn.textContent = discountPanel.classList.contains("show") 
            ? "Hide discount code" 
            : "Have a discount code?";
    });

    const subtotalElement = document.querySelector(".subtot span");
    const shippingElement = document.querySelector(".shipes span");
    const totalElement = document.querySelector("#totnum span");

    // Function to recalculate totals
    function updateTotals() {
        const productItems = document.querySelectorAll(".product-item");
        let subtotal = 0;

        productItems.forEach(item => {
            const priceEl = item.querySelector(".price span");
            const qtyEl = item.querySelector(".quantity span");

            if (!priceEl || !qtyEl) return;

            const price = parseFloat(priceEl.textContent.replace(/,/g, "")) || 0;
            const quantity = parseInt(qtyEl.textContent) || 0;

            subtotal += price * quantity;
        });

        subtotalElement.textContent = subtotal.toLocaleString();

        const shipping = parseFloat(shippingElement.textContent.replace(/,/g, "")) || 0;
        const total = subtotal + shipping;

        totalElement.textContent = total.toLocaleString();
    }

    // Handles quantity and delete button clicks
    function attachItemListeners() {
        document.querySelectorAll(".product-item").forEach(item => {
            const plusBtn = item.querySelector(".quantity button:last-child");
            const minusBtn = item.querySelector(".quantity button:first-child");
            const quantitySpan = item.querySelector(".quantity span");
            const deleteBtn = item.querySelector(".delete-btn");

            plusBtn.onclick = () => {
                quantitySpan.textContent = parseInt(quantitySpan.textContent) + 1;
                updateTotals();
            };

            minusBtn.onclick = () => {
                let qty = parseInt(quantitySpan.textContent);
                if (qty > 1) {
                    quantitySpan.textContent = qty - 1;
                    updateTotals();
                }
            };

            if (deleteBtn) {
                deleteBtn.onclick = () => {
                    const confirmDelete = confirm("Are you sure you want to remove this product from your cart?");
                    if (confirmDelete) {
                        item.remove();
                        updateTotals();
                    }
                };
            }
        });
    }

    // Watch for product additions/removals dynamically
    const observer = new MutationObserver(() => {
        attachItemListeners();
        updateTotals();
    });
    observer.observe(document.querySelector(".checkout-container"), { childList: true, subtree: true });

    // Initialize
    attachItemListeners();
    updateTotals();


// ---- JS for editprofile.html ----
    let moonbtn = document.getElementsByClassName("")


// ---- JS for editprofile.html ----
    const grid = document.querySelector('.products-grid');
    const leftButton = document.querySelector('.left-nav');
    const rightButton = document.querySelector('.right-nav');

    const scrollAmount = 880; 

    // Logic for the Right Button (Scroll Forward)
    rightButton.addEventListener('click', () => {
        grid.scrollBy({
            left: scrollAmount,
            behavior: 'smooth'
        });
    });

    // Logic for the Left Button (Scroll Backward)
    leftButton.addEventListener('click', () => {
        grid.scrollBy({
            left: -scrollAmount,
            behavior: 'smooth'
        });

    });

})