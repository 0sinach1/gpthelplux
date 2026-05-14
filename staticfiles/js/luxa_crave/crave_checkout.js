

// NEW: We store the grouped cart globally so we can send the compressed version to the backend
let finalGroupedCart = [];
let pendingProfileUpdate = false; 
let isVipRouteActive = false;
let verifiedVipUsername = null;

// --- NEW: SMART BUTTON LOADING STATE MANAGERS ---
let btnSafeCache = '';
let btnFastCache = '';
let btnOrderCache = '';

document.addEventListener('DOMContentLoaded', () => {
    // Cache the original complex HTML of the buttons when the page loads
    const bs = document.querySelector('.btn-complete-safe');
    const bf = document.querySelector('.btn-complete-fast');
    const bo = document.querySelector('.btn-complete-order');
    if(bs) btnSafeCache = bs.innerHTML;
    if(bf) btnFastCache = bf.innerHTML;
    if(bo) btnOrderCache = bo.innerHTML;
});

function setCheckoutButtonsLoading() {
    const bs = document.querySelector('.btn-complete-safe');
    const bf = document.querySelector('.btn-complete-fast');
    const bo = document.querySelector('.btn-complete-order');
    const loader = '<i class="bi bi-hourglass-split fa-spin"></i> Processing...';
    
    if(bs) { bs.disabled = true; bs.innerHTML = loader; }
    if(bf) { bf.disabled = true; bf.innerHTML = loader; }
    if(bo) { bo.disabled = true; bo.innerHTML = loader; }
}

function restoreCheckoutButtons() {
    const bs = document.querySelector('.btn-complete-safe');
    const bf = document.querySelector('.btn-complete-fast');
    const bo = document.querySelector('.btn-complete-order');
    
    if(bs && btnSafeCache) { bs.disabled = false; bs.innerHTML = btnSafeCache; }
    if(bf && btnFastCache) { bf.disabled = false; bf.innerHTML = btnFastCache; }
    if(bo && btnOrderCache) { bo.disabled = false; bo.innerHTML = btnOrderCache; }
}
// ------------------------------------------------


document.addEventListener('DOMContentLoaded', () => {
    let cartData = [];
    
    try {
        // Grab the raw data that was rendered by the HTML script tag
        cartData = JSON.parse(window.cartDataRaw);
    } catch(e) {
        console.error("Could not parse cart data", e);
    }

    // Failsafe: If they try to access checkout with an empty bag
    if (!cartData || cartData.length === 0) {
        alert("Your Crave Bag is empty!");
        // Note: You might need to hardcode this URL or pass it via window as well
        // if your JS file doesn't recognize the Django url tag. 
        window.location.href = "/dashboard/"; 
        return;
    }

    // --- NEW: THE PACK GROUPING ALGORITHM ---
    const packSignatures = {};

    cartData.forEach((pack) => {
        // Sort items by ID so [Rice, Beans] is treated exactly the same as [Beans, Rice]
        const sortedItems = [...pack.items].sort((a, b) => a.id - b.id);
        const itemsHash = sortedItems.map(i => `${i.id}_${i.qty}`).join('|');
        const packConfig = pack.selectedPackConfigId || 'loose';
        
        // Signature creates a unique string for this exact configuration
        const signature = `${packConfig}::${itemsHash}`;
        const currentMult = pack.multiplier || 1;

        if (packSignatures[signature]) {
            // Exact match found! Combine the multipliers and costs.
            packSignatures[signature].multiplier += currentMult;
            packSignatures[signature].finalTotal += pack.finalTotal; 
            
            // THE FIX: Combine the influence (Courion) values too!
            // We fallback to currentMult just in case it's somehow missing
            packSignatures[signature].influence_value += (pack.influence_value || currentMult); 
        } else {
            // New configuration found. Clone it so we don't alter the original reference.
            const clonedPack = JSON.parse(JSON.stringify(pack));
            clonedPack.multiplier = currentMult;
            // Safely ensure influence value exists on the clone
            clonedPack.influence_value = pack.influence_value || currentMult; 
            packSignatures[signature] = clonedPack;
            finalGroupedCart.push(clonedPack);
        }
    });

    const SPECIAL_RESTRICTIONS = {
        'large_bread': { extra_fee: 250 },
        'medium_bread': { extra_fee: 200 },
        'small_bread': { extra_fee: 125 },
        'bread_egg': { extra_fee: 0 },
    };

    // --- UI RENDERING ---
    const itemsListEl = document.getElementById('checkout-items-list');
    let subtotal = 0;
    let totalPhysicalPacks = 0;
    let totalSurchargeFee = 0;   
    let standardPackCount = 0;    
    let hasBreadEggInCart = false; // --- NEW: Track if bread_egg exists for the UI Icon ---
    let surchargeMap = {}; 
    itemsListEl.innerHTML = ''; // Clear container

    finalGroupedCart.forEach((pack, index) => {
        subtotal += pack.finalTotal;

        let hasNormalItem = false;
        let packSpecificSurcharge = 0; 
        let breadEggQty = 0; // --- NEW: Track bread_egg items inside this pack ---        
        const packMultiplier = pack.multiplier || 1; 

        pack.items.forEach(item => {
            const isStrange = String(item.is_strange) === 'true';
            if (!isStrange) hasNormalItem = true; 

            // --- NEW: Tally Bread Eggs & Trigger Global Icon Flag ---
            if (item.strange_value === 'bread_egg') {
                breadEggQty += parseInt(item.qty) || 1;
                hasBreadEggInCart = true;
            }

            // Calculate Surcharge & Track Details
            const restriction = SPECIAL_RESTRICTIONS[item.strange_value];
            if (restriction) {
                const fee = restriction.extra_fee;
                
                // Add to the specific pack check (ignoring multiplier for the logic check)
                packSpecificSurcharge += (item.qty * fee); 
                
                // Keep the global math accurate
                const qty = item.qty * packMultiplier;
                const itemSubtotal = qty * fee;
                totalSurchargeFee += itemSubtotal;

                // Group by Name + Section (Category)
                const section = item.sectionName;
                const key = `${item.name} (${section})`;

                if (!surchargeMap[key]) {
                    surchargeMap[key] = { qty: 0, fee: fee, total: 0 };
                }
                surchargeMap[key].qty += qty;
                surchargeMap[key].total += itemSubtotal;
            }
        });

        // --- THE FIX: DYNAMIC PACK COUNTING FOR BREAD EGG ---
        if (hasNormalItem || packSpecificSurcharge < 1) {
            // Determine effective packs for this bundle based on bread_egg quantity
            const baseCount = breadEggQty > 0 ? breadEggQty : 1;
            standardPackCount += (baseCount * packMultiplier);
        }

        totalPhysicalPacks += pack.multiplier;

        let iconHtml = (pack.requiresPackFlag && pack.packContainerImage && pack.packContainerImage !== 'placeholder') 
            ? `<img src="${pack.packContainerImage}" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;" alt="Pack">` 
            : `<i class="bi bi-box-seam"></i>`;
        
        let itemsPreview = pack.items.map(i => `${i.qty}x ${i.name}`).join(', ');
        if (itemsPreview.length > 35) {
            itemsPreview = itemsPreview.substring(0, 32) + '...';
        }

        // Beautiful multiplier badge for grouped items
        const multiplierBadge = pack.multiplier > 1 
            ? `<span style="background: #eff6ff; color: #3b82f6; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 800; margin-left: 8px; border: 1px solid #bfdbfe; display: inline-block;">x${pack.multiplier}</span>` 
            : '';

        const displayName = pack.packContainerName && pack.packContainerName !== "No Pack" 
            ? pack.packContainerName 
            : "Custom Pack";

        itemsListEl.innerHTML += `
            <div class="summary-item">
                <div class="si-image">
                    ${iconHtml}
                </div>
                <div class="si-details">
                    <h4 style="display: flex; align-items: center; gap: 4px; margin: 0 0 4px 0;">
                        ${displayName} ${multiplierBadge}
                    </h4>
                    <span style="font-size:0.75rem; color:#a8a096;">${itemsPreview}</span>
                </div>
                <div class="si-price">₦${pack.finalTotal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            </div>
        `;
    });

    // --- BUILD THE SURCHARGE SUMMARY HTML ---
    let surchargeBreakdownHtml = "";
    for (const [label, data] of Object.entries(surchargeMap)) {
        surchargeBreakdownHtml += `
            <div style="display: flex; flex-direction: column; gap: 2px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 700; color: #742a2a;">
                    <span>${label}</span>
                    <span>₦${data.total.toLocaleString()}</span>
                </div>
                <div style="font-size: 0.7rem; color: #a04545; font-style: italic;">
                    Math: ${data.qty} units × ₦${data.fee} fee
                </div>
            </div>
        `;
    }

    // 3. Updated Delivery Logic (Using standardPackCount)
    let baseDeliveryFee = 0;
    let calcText = "";
    
    if (standardPackCount > 0) {
        let count = Math.min(standardPackCount, 10);
        let ratePerPack = (count === 10) ? 300 : 400 - ((count - 1) * 10);
        baseDeliveryFee = count * ratePerPack;
        calcText = `${count} x ₦${ratePerPack}`;
    }

    // --- NEW: RUSH HOUR WAIT FEE LOGIC ---
    let waitFee = 0;
    if (window.CURRENT_OUTLET_NAME && window.CURRENT_OUTLET_NAME.toLowerCase().includes('backyard')) {
        const now = new Date();
        const hour = now.getHours();
        const mins = now.getMinutes();
        
        if ((hour === 17) || (hour === 18)) {
            waitFee = 300;
        }
    }
    
    // Combine base delivery and wait fee so the Promo Discount correctly applies to both!
    const combinedDeliveryForPromo = baseDeliveryFee + waitFee;

    // --- THE PROMO DISCOUNT UI ---
    let promoHtml = "";
    if (window.promoPercentage > 0 && totalPhysicalPacks > 0 && totalPhysicalPacks <= window.availablePromoCourions) {
        promoHtml = `
            <div style="background: #fdf2f8; border: 1px dashed #db2777; padding: 15px; border-radius: 8px; margin-top: 15px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #be185d; font-size: 0.9rem;"><i class="bi bi-stars"></i> VIP Loyalty Discount</strong>
                    <div style="font-size: 0.75rem; color: #9d174d; margin-top: 2px;">Apply ${window.promoPercentage}% off delivery? (${window.availablePromoCourions} Courions left today)</div>
                </div>
                <label class="vip-switch">
                    <input type="checkbox" id="loyalty-promo-toggle" onchange="togglePromoDiscount(${combinedDeliveryForPromo}, ${totalSurchargeFee}, ${subtotal})">
                    <span class="vip-slider"></span>
                </label>
            </div>
        `;
    }

    // Inject Promo UI right below the Surcharge section
    const surchargeContainer = document.getElementById('checkout-surcharge-section');
    if (promoHtml && !document.getElementById('loyalty-promo-toggle')) {
        surchargeContainer.insertAdjacentHTML('afterend', promoHtml);
    }

    // --- GRAND TOTAL UPDATE ---
    const finalTotal = subtotal + combinedDeliveryForPromo + totalSurchargeFee;

    // 4. Update the DOM values
    document.getElementById('checkout-subtotal').innerText = `₦${subtotal.toLocaleString()}`;

    // --- NEW: RENDER THE WAIT FEE DOM & CUSTOM TOOLTIP ---
    const waitFeeRow = document.getElementById('checkout-wait-fee-row');
    const waitFeePrice = document.getElementById('checkout-wait-fee-price');
    
    if (waitFeeRow && waitFeePrice) {
        if (waitFee > 0 && standardPackCount > 0) {
            waitFeeRow.style.display = 'flex';
            // Inject the price and the Custom Tooltip HTML
            waitFeePrice.innerHTML = `+₦${waitFee} 
                <div class="crave-tooltip-wrapper">
                    <i class="bi bi-info-circle-fill" style="color: #94a3b8; font-size: 0.85rem;"></i>
                    <span class="crave-tooltip-text">100% of this fee goes directly to your courier to compensate for their time waiting in the extreme rush hour queue at BackYard. Luxa takes 0%.</span>
                </div>`;
        } else {
            waitFeeRow.style.display = 'none';
        }
    }

    // --- NEW: THE ICON INJECTION LOGIC ---
    const infoIconHtml = hasBreadEggInCart ? ` <i class="bi bi-info-circle-fill" title="Due to courier bag constraints, each special item like sharwarma or bread and egg acts as a separate pack for delivery calculation." style="cursor: help; color: #94a3b8; font-size: 0.85rem; margin-left: 3px;"></i>` : '';
    document.getElementById('checkout-delivery-calc').innerHTML = standardPackCount > 0 ? `(${calcText})${infoIconHtml}` : '';
    document.getElementById('checkout-delivery').innerText = `₦${baseDeliveryFee.toLocaleString()}`;

    // UPDATE SURCHARGE SECTION (Restored and Protected)
    const surchargeSection = document.getElementById('checkout-surcharge-section');
    const breakdownContainer = document.getElementById('checkout-surcharge-breakdown-list');
    
    if (totalSurchargeFee > 0) {
        if (surchargeSection) surchargeSection.style.display = 'flex';
        if (breakdownContainer) breakdownContainer.innerHTML = surchargeBreakdownHtml;
        document.getElementById('checkout-surcharge').innerText = `₦${totalSurchargeFee.toLocaleString()}`;
    } else {
        if (surchargeSection) surchargeSection.style.display = 'none';
    }

    document.getElementById('checkout-total').innerText = `₦${finalTotal.toLocaleString()}`;    

    // --- NEW: PROXY MODAL TRIGGER LOGIC ---
    // We only want to show this if they haven't seen it recently AND they don't already have proxy turned on
    const proxyActive = document.getElementById('proxy-checkout-toggle') && document.getElementById('proxy-checkout-toggle').checked;
    const proxyModalSeen = localStorage.getItem('luxa_proxy_intro_seen');

    if (!proxyModalSeen && !proxyActive) {
        // Slight delay (600ms) so it pops up smoothly after the page fade-in animation finishes
        setTimeout(() => {
            document.getElementById('modal-proxy-intro').classList.add('active');
        }, 600);
    }

});


// --- DYNAMIC CASCADING DROPDOWN LOGIC ---
function filterBuildings(zoneSelectId, buildingSelectId) {
    const zoneElement = document.getElementById(zoneSelectId);
    const buildingElement = document.getElementById(buildingSelectId);

    if (!zoneElement || !buildingElement) return;

    const zoneValue = zoneElement.value;
    const buildingOptions = buildingElement.querySelectorAll('option');

    let isCurrentSelectionValid = false;

    buildingOptions.forEach(option => {
        // Always show the default placeholder
        if (option.value === "") {
            option.style.display = '';
            return;
        }

        // Check if the building belongs to the selected zone
        const buildingZoneId = option.getAttribute('data-zone-id');
        
        if (buildingZoneId === zoneValue || zoneValue === "") {
            option.style.display = ''; // Show it
            if (option.selected) isCurrentSelectionValid = true;
        } else {
            option.style.display = 'none'; // Hide it
        }
    });

    // If they changed the zone, and the previously selected building is hidden, reset it
    if (!isCurrentSelectionValid) {
        buildingElement.value = "";
    }
}

// Run this function immediately when the checkout page loads so the initial UI is correct!
document.addEventListener('DOMContentLoaded', () => {
    filterBuildings('checkout-location', 'checkout-building');
});

// --- CHECKOUT PROXY TOGGLE LOGIC ---
function toggleCheckoutProxy() {
    const toggleInput = document.getElementById('proxy-checkout-toggle');
    const isChecked = toggleInput.checked;
    const proxyInfo = document.getElementById('checkout-proxy-info');
    const customerForm = document.getElementById('customer-location-wrapper');
    
    // Form elements to manage 'required' state
    const locSelect = document.getElementById('checkout-location');
    const bldgSelect = document.getElementById('checkout-building');
    const roomInput = document.getElementById('checkout-room');

    // 1. FRONTEND UI UPDATE
    if (isChecked) {
        proxyInfo.style.display = 'block';
        customerForm.classList.add('disabled-form');
        locSelect.removeAttribute('required');
        bldgSelect.removeAttribute('required');
        roomInput.removeAttribute('required');
    } else {
        proxyInfo.style.display = 'none';
        customerForm.classList.remove('disabled-form');
        locSelect.setAttribute('required', 'true');
        bldgSelect.setAttribute('required', 'true');
        roomInput.setAttribute('required', 'true');
    }

    // 2. BACKEND SYNC (Saves the choice permanently)
    // Disables the toggle temporarily to prevent spam-clicking while saving
    toggleInput.disabled = true; 

    fetch("/api/toggle-proxy-status/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({ proxy_enabled: isChecked })
    })
    .then(response => response.json())
    .then(data => {
        toggleInput.disabled = false; // Re-enable switch
        if (data.status !== 'success') {
            console.error("Backend sync failed:", data.message);
            alert("Warning: Could not save your proxy preference to the server.");
        }
    })
    .catch(err => {
        toggleInput.disabled = false;
        console.error("Network Error:", err);
    });
}

// --- KYC AND PIN VERIFICATION FLOW ---

// We grab the KYC status from the view context (Defaults to NONE if no KYC exists)
const kycStatus = window.kycStatus || 'NONE'; 

let targetGender = window.targetGender; // Fallback

// 1. Modal Toggles
window.openProfileEdit = function() {
    closeModals();
    document.getElementById('modal-profile-edit').classList.add('active');
}

window.triggerProfileUpdateWarning = function() {
    const fname = document.getElementById('modal_fname').value;
    const lname = document.getElementById('modal_lname').value;
    const phone = document.getElementById('modal_phone').value;
    const gender = document.getElementById('modal_gender').value; // NEW
    const socialplat = document.getElementById('modal_social_platform').value; // NEW
    const socialhandle = document.getElementById('modal_social_handle').value; // NEW

    if(!fname || !lname || !phone || !gender) { // NEW
        alert("Please fill in the necessary fields, including your gender.");
        return;
    }
    closeModals();
    document.getElementById('modal-update-warning').classList.add('active');
}

window.closeModals = function() {
    document.querySelectorAll('.kyc-modal-overlay').forEach(el => el.classList.remove('active'));
}

window.previewProfileImage = function(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = document.getElementById('preview_img');
            const placeholder = document.getElementById('preview_placeholder');
            img.src = e.target.result;
            img.style.display = 'block';
            if(placeholder) placeholder.style.display = 'none';
        }
        reader.readAsDataURL(input.files[0]);
    }
}


// FUNCTION BLOCK FOR VIP COURIER ASSIGNMENT
function toggleVipCourier() {
    const toggle = document.getElementById('vip-courier-toggle');
    isVipRouteActive = toggle.checked;
    if (!isVipRouteActive) {
        verifiedVipUsername = null; // Clear it if they turn it off
    }
}

function cancelVipCourier() {
    document.getElementById('vip-courier-toggle').checked = false;
    isVipRouteActive = false;
    verifiedVipUsername = null;
    closeModals();
    
    // Reset the main checkout button
    const btn = document.querySelector('.btn-complete-order');
    btn.disabled = false;
    btn.innerHTML = 'Complete Order <i class="bi bi-arrow-right"></i>';
}

async function verifyVipCourier() {
    const inputEl = document.getElementById('vip_courier_username');
    const errorEl = document.getElementById('vip-error-msg');
    const btn = document.getElementById('btn-verify-vip');
    const username = inputEl.value.trim();

    if (!username) {
        errorEl.innerText = "Please enter a username.";
        errorEl.style.display = "block";
        return;
    }

    // 1. Calculate the total Courion volume of the cart
    let totalCartVolume = 0;
    finalGroupedCart.forEach(pack => {
        totalCartVolume += (pack.influence_value || pack.multiplier || 1);
    });

    // 2. Determine target gender (Proxy vs Customer)
    const useProxy = document.getElementById('proxy-checkout-toggle') && document.getElementById('proxy-checkout-toggle').checked;
    let finalGender = window.targetGender; // Default to customer
    
    if (useProxy) {
        // Grab proxy gender from the rendered DOM if proxy is active
        const proxyGenderBadge = document.querySelector('#checkout-proxy-info span[style*="text-transform: uppercase"]');
        if (proxyGenderBadge) {
            finalGender = proxyGenderBadge.innerText.trim().toLowerCase();
        }
    }

    // 3. UI Loading State
    errorEl.style.display = "none";
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Verifying...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/validate-preferred-courier/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({
                username: username,
                cart_volume: totalCartVolume,
                target_gender: finalGender
            })
        });

        const data = await response.json();

        if (data.valid) {
            // Success! Save the username and move to the PIN modal
            verifiedVipUsername = username;
            closeModals();
            openPinModal();
        } else {
            // Failed: Show the specific error from the backend (+3 margin error, offline, etc.)
            errorEl.innerText = data.error || "Invalid Courier.";
            errorEl.style.display = "block";
        }
    } catch (error) {
        errorEl.innerText = "Network error. Could not verify courier.";
        errorEl.style.display = "block";
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}


function openPinModal() {
    const pinInput = document.getElementById('checkout_pin_input');
    
    if (pinInput) {
        pinInput.value = ''; // Only clear if it exists
    }
    
    document.getElementById('modal-pin-verify').classList.add('active');
    
    if (pinInput) {
        setTimeout(() => pinInput.focus(), 100); // Only focus if it exists
    }
}

// =================================================================
// THE ENGINE: FORM INTERCEPTORS, POLLING, AND REBUILD UI
// =================================================================

// 1. GLOBAL STATE FOR ENGINE
window.selectedCheckoutMode = 'fast'; 
let currentSoldOutIds = [];

// 2. NEW ENTRY POINT (From the Dual Buttons) - WITH PRE-CHECKOUT WALLET VALIDATION
window.initiateCheckout = async function(isSafeMode) {
    // Show loading state immediately on click
    setCheckoutButtonsLoading();

    try {
        const totalText = document.getElementById('checkout-total').innerText;
        const requiredAmount = parseFloat(totalText.replace(/[^\d.-]/g, ''));

        const response = await fetch('/api/check-wallet-balance/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({ required_amount: requiredAmount })
        });

        const data = await response.json();

        if (!data.has_balance) {
            const alertContainer = document.getElementById('crave-checkout-alerts');
            const reqAmtStr = requiredAmount.toLocaleString(undefined, {minimumFractionDigits: 2});
            
            alertContainer.innerHTML = `
                <div style="background: #fef2f2; border: 1px solid #fecaca; padding: 15px 20px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; gap: 15px; color: #991b1b; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <i class="bi bi-exclamation-octagon-fill" style="font-size: 1.5rem; color: #dc2626;"></i>
                        <span style="font-weight: 600; font-size: 0.95rem;">Insufficient Wallet Balance. You need ₦${reqAmtStr} to complete this order.</span>
                    </div>
                    <a href="${data.wallet_url || '#'}" target="_blank" style="background: #991b1b; color: white; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-size: 0.85rem; font-weight: 700; display: flex; align-items: center; gap: 6px;">Fund Wallet <i class="bi bi-box-arrow-up-right"></i></a>
                </div>`;
            
            alertContainer.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
            
            restoreCheckoutButtons(); // Restore on fail
            return; 
        }

    } catch (error) {
        console.error("Pre-checkout validation failed:", error);
        alert("Network error while verifying wallet balance.");
        restoreCheckoutButtons(); // Restore on fail
        return;
    }

    // IF THEY HAVE THE MONEY: Revert buttons back to normal before opening the KYC/PIN Modals
    restoreCheckoutButtons();

    window.selectedCheckoutMode = isSafeMode ? 'safe' : 'fast';
    
    if (!isSafeMode) {
        document.getElementById('modal-fast-warning').classList.add('active');
    } else {
        const event = new Event('submit', { cancelable: true });
        document.getElementById('checkout-form').dispatchEvent(event);
    }
}

// 2A. MODAL ACTION: Proceed with Fast Mode anyway
window.confirmFastMode = function() {
    closeModals();
    const event = new Event('submit', { cancelable: true });
    document.getElementById('checkout-form').dispatchEvent(event);
}

// 2B. MODAL ACTION: Change mind to Safe Mode
window.switchToSafeMode = function() {
    closeModals();
    window.selectedCheckoutMode = 'safe'; 
    const event = new Event('submit', { cancelable: true });
    document.getElementById('checkout-form').dispatchEvent(event);
}

// 3. FORM SUBMISSION INTERCEPTOR (Handles KYC & VIP before PIN)
const checkoutForm = document.getElementById('checkout-form');
checkoutForm.addEventListener('submit', function(e) {
    e.preventDefault(); 
    pendingProfileUpdate = false; 
    
    if (kycStatus === 'APPROVED') {
        if (isVipRouteActive) {
            document.getElementById('vip_courier_username').value = '';
            document.getElementById('vip-error-msg').style.display = 'none';
            document.getElementById('modal-vip-courier').classList.add('active');
        } else {
            openPinModal(); 
        }
    } else if (kycStatus === 'PENDING') {
        document.getElementById('modal-kyc-pending').classList.add('active');
    } else {
        document.getElementById('modal-kyc-warning').classList.add('active');
    }
});

window.submitFinalOrder = function() {
    closeModals();
    pendingProfileUpdate = true; 
    if (isVipRouteActive) {
        document.getElementById('vip_courier_username').value = '';
        document.getElementById('vip-error-msg').style.display = 'none';
        document.getElementById('modal-vip-courier').classList.add('active');
    } else {
        openPinModal();
    }
}

// 4. PIN EXECUTION & TERMINAL ROUTING
window.submitOrderWithPin = function() {
    const pinValue = document.getElementById('checkout_pin_input').value;
    if(pinValue.length !== 4) { alert("Please enter a valid 4-digit PIN."); return; }
    
    closeModals();
    window.tempPinValue = pinValue; 
    
    if (window.selectedCheckoutMode === 'fast') {
        // YOLO Mode: Skip terminal, just fire the fetch
        processCraveOrderSubmission(pendingProfileUpdate, pinValue, false);
    } else {
        // Safe Mode: Start the visual engine!
        startTerminalSequence();
    }
}

// 5. THE TERMINAL UI SEQUENCE
window.terminalCancelTimer = null; // Global timer tracker

function startTerminalSequence() {
    const terminal = document.getElementById('terminal-overlay');
    const logs = document.getElementById('terminal-logs');
    const cancelBtn = document.getElementById('terminal-cancel-btn-container');
    
    terminal.classList.add('active');
    logs.innerHTML = ''; 
    if(cancelBtn) cancelBtn.style.display = 'none';

    // NEW: Start the 1-minute 40-second timer to show the escape hatch
    clearTimeout(window.terminalCancelTimer);
    window.terminalCancelTimer = setTimeout(() => {
        if(cancelBtn) cancelBtn.style.display = 'block';
    }, 100000); 

    appendLog("[SYSTEM] Initializing Cart Verification...");
    
    setTimeout(() => {
        appendLog("[ENGINE] Scanning Outlet timestamps...");
        processCraveOrderSubmission(pendingProfileUpdate, window.tempPinValue, true);
    }, 1000);
}

// --- NEW: ESCAPE HATCH MODAL CONTROLS ---
window.showTerminalTimeoutOptions = function() {
    document.getElementById('modal-terminal-options').classList.add('active');
}

window.hideTerminalOptionsAndWait = function() {
    document.getElementById('modal-terminal-options').classList.remove('active');
}

function appendLog(text, isError = false) {
    const logs = document.getElementById('terminal-logs');
    const div = document.createElement('div');
    
    // Default styling (Blue Arrow)
    let iconClass = "bi-arrow-right-circle-fill";
    let iconColor = "#3b82f6"; 
    let textStyle = "color: #334155;";

    // Smart context detection based on your existing string payloads
    if (isError || text.includes("[ALERT]")) {
        iconClass = "bi-x-circle-fill";
        iconColor = "#ef4444";
        textStyle = "color: #dc2626;";
    } else if (text.includes("[SUCCESS]")) {
        iconClass = "bi-check-circle-fill";
        iconColor = "#22c55e";
    } else if (text.includes("[WAITING]") || text.includes("Pinging")) {
        // Spinning hourglass when waiting for the kitchen!
        iconClass = "bi-hourglass-split";
        iconColor = "#f59e0b";
        iconClass += " fa-spin"; // Add spin if using font-awesome, or it stays static with bootstrap
    }

    // Strip the technical brackets (e.g. "[SYSTEM] Scanning..." becomes "Scanning...")
    let cleanText = text.replace(/\[.*?\]\s*/, '');

    div.className = 'engine-log-line';
    div.innerHTML = `<i class="bi ${iconClass}" style="color: ${iconColor};"></i> <span style="${textStyle}">${cleanText}</span>`;
    
    logs.appendChild(div);
    logs.scrollTop = logs.scrollHeight;
}

// 6. MODIFIED FETCH TO HANDLE PINGS AND 4-STATE ENGINE
function processCraveOrderSubmission(includeProfileUpdate, pinValue, isSafeMode = false) {
   
    setCheckoutButtonsLoading();

    const formData = new FormData(checkoutForm);
    formData.append('delivery_pin', pinValue);
    if (isVipRouteActive && verifiedVipUsername) formData.append('preferred_courier_username', verifiedVipUsername);
    formData.append('cart_data', JSON.stringify(finalGroupedCart)); 

    if (includeProfileUpdate) {
        formData.append('update_profile', 'true');
        formData.append('kyc_first_name', document.getElementById('modal_fname').value);
        formData.append('kyc_last_name', document.getElementById('modal_lname').value);
        formData.append('kyc_phone', document.getElementById('modal_phone').value);
        formData.append('kyc_gender', document.getElementById('modal_gender').value);
        formData.append('kyc_social_platform', document.getElementById('modal_social_platform').value);
        formData.append('kyc_social_handle', document.getElementById('modal_social_handle').value);
        
        const fileInput = document.getElementById('modal_profile_pic');
        if (fileInput.files[0]) formData.append('kyc_profile_picture', fileInput.files[0]);
    }

    // THE CRITICAL FLAG FOR THE ENGINE
    formData.append('safe_mode', isSafeMode ? 'true' : 'false');

    const promoToggle = document.getElementById('loyalty-promo-toggle');
    const isPromoApplied = promoToggle ? promoToggle.checked : false;
    formData.append('apply_loyalty_promo', isPromoApplied ? 'true' : 'false');

    fetch('/api/create-campus-order/', { 
        method: 'POST', body: formData 
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ping_initiated') {
            // STATE 2 or 4: Kitchen needs to verify
            appendLog("[WAITING] Low confidence on items. Pinging Kitchen Staff...", false);
            pollPingStatus(data.ping_id);
            
        } else if (data.status === 'instant_rebuild') {
            // STATE 3: The Hard Block (Skip pinging, go straight to fix)
            appendLog("[ALERT] " + data.message, true);
            currentSoldOutIds = data.sold_out_ids.map(String);

            window.currentAlternatives = data.alternatives || {};
            populatePackAlternatives();
            
            setTimeout(() => {
                document.getElementById('terminal-overlay').classList.remove('active');
                document.getElementById('rebuild-interceptor-message').innerText = data.message;
                renderMiniRebuildUI();
                document.getElementById('modal-mini-rebuild').classList.add('active');
            }, 1500);

        } else if (data.success) {
            // STATE 1: Everything is good!
            if (isSafeMode) appendLog("[SUCCESS] Verification passed. Locking escrow...");
            localStorage.removeItem('crave_terminal_state'); 
            sessionStorage.removeItem('crave_terminal_state');
            setTimeout(() => { window.location.href = data.redirect_url; }, isSafeMode ? 800 : 0);
            
        } else {
            // ERROR ROUTE (e.g., Wallet empty)
            document.getElementById('terminal-overlay').classList.remove('active');
            const alertContainer = document.getElementById('crave-checkout-alerts');
            let message = ''; let actionBtn = '';

            if (data.error_code === 'insufficient_funds') {
                const reqAmount = parseFloat(data.required_amount).toLocaleString(undefined, {minimumFractionDigits: 2});
                message = `Insufficient Wallet Balance. You need ₦${reqAmount} to complete this order.`;
                actionBtn = `<a href="${data.wallet_url}" target="_blank" style="background: #991b1b; color: white; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-size: 0.85rem; font-weight: 700; display: flex; align-items: center; gap: 6px;">Fund Wallet <i class="bi bi-box-arrow-up-right"></i></a>`;
            } else {
                message = data.error || "Failed to place order.";
            }

            alertContainer.innerHTML = `
                <div style="background: #fef2f2; border: 1px solid #fecaca; padding: 15px 20px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; gap: 15px; color: #991b1b; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <i class="bi bi-exclamation-octagon-fill" style="font-size: 1.5rem; color: #dc2626;"></i>
                        <span style="font-weight: 600; font-size: 0.95rem;">${message}</span>
                    </div>
                    ${actionBtn}
                </div>`;
            alertContainer.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
            
            const btn = document.querySelector('.btn-complete-order');
            if(btn) {
                btn.disabled = false;
                btn.innerHTML = 'Complete Order <i class="bi bi-arrow-right"></i>';
            }
        }
    }).catch(err => {
        console.error(err); alert("Network Error");
        document.getElementById('terminal-overlay').classList.remove('active');
    });
}

// 7. THE POLLER (Waits for kitchen staff)
window.currentAlternatives = {}; // Global store for the mini-builder

// --- NEW: EXTRACT ALTERNATIVES INDEPENDENTLY ---
function populatePackAlternatives() {
    finalGroupedCart.forEach(pack => {
        pack.pendingAlts = pack.pendingAlts || {};
        pack.items.forEach(item => {
            if (currentSoldOutIds.includes(String(item.id)) && window.currentAlternatives[String(item.id)]) {
                pack.pendingAlts[String(item.id)] = {
                    originalName: item.name,
                    alts: window.currentAlternatives[String(item.id)]
                };
            }
        });
    });
}

function checkRebuildStatus() {
    const stillHasBroken = finalGroupedCart.some(p => p.items.some(i => currentSoldOutIds.includes(String(i.id))));
    const msgEl = document.getElementById('rebuild-interceptor-message');
    if (!stillHasBroken && msgEl) {
        msgEl.innerText = "Bag fixed! You can now proceed to checkout.";
        msgEl.style.color = '#16a34a';
    }
}

function pollPingStatus(pingId) {
    const startTime = Date.now();
    const TIMEOUT_DURATION = 2 * 60 * 1000; // 2 minutes in milliseconds (120,000ms)

    const pollInterval = setInterval(() => {
        // 1. Check if 3 minutes have passed BEFORE pinging the server
        if (Date.now() - startTime > TIMEOUT_DURATION) {
            clearInterval(pollInterval); // Stop asking the server
            clearTimeout(window.terminalCancelTimer);
            document.getElementById('terminal-overlay').classList.remove('active'); // Hide the engine
            document.getElementById('modal-ping-timeout').classList.add('active');  // Show the timeout popup
            return;
        }

        // 2. Otherwise, check the server normally
        fetch(`/api/check-ping/${pingId}/`)
        .then(res => res.json())
        .then(data => {
            if (data.status === 'resolved') {
                clearInterval(pollInterval);
                clearTimeout(window.terminalCancelTimer);
                
                if (data.needs_rebuild) {
                    appendLog("[ALERT] Missing items detected! Routing to manual override...", true);
                    currentSoldOutIds = data.sold_out_ids.map(String);
                    window.currentAlternatives = data.alternatives || {};
                    
                    populatePackAlternatives(); // Hydrate the independent trays
                    
                    setTimeout(() => {
                        document.getElementById('terminal-overlay').classList.remove('active');
                        document.getElementById('rebuild-interceptor-message').innerText = data.message;
                        renderMiniRebuildUI();
                        document.getElementById('modal-mini-rebuild').classList.add('active');
                    }, 1500);
                } else {
                    appendLog("[SUCCESS] Kitchen confirms all items available. Resuming...");
                    processCraveOrderSubmission(pendingProfileUpdate, window.tempPinValue, true);
                }
            }
        });
    }, 2000); 
}

// 7B. HANDLE TIMEOUT ACTIONS
window.proceedAfterTimeout = function() {
    document.getElementById('modal-ping-timeout').classList.remove('active');
    document.getElementById('modal-terminal-options').classList.remove('active'); // Close new modal
    
    const terminal = document.getElementById('terminal-overlay');
    terminal.classList.add('active');
    
    // Hide the cancel button again since they chose to force it
    const cancelBtn = document.getElementById('terminal-cancel-btn-container');
    if(cancelBtn) cancelBtn.style.display = 'none';

    appendLog("[SYSTEM] Bypassing verification. Pushing order directly...");
    
    setTimeout(() => {
        processCraveOrderSubmission(pendingProfileUpdate, window.tempPinValue, false);
    }, 1000);
}

window.cancelTimeout = function() {
    document.getElementById('modal-ping-timeout').classList.remove('active');
    document.getElementById('modal-terminal-options').classList.remove('active'); // Close new modal
    document.getElementById('terminal-overlay').classList.remove('active'); // Close terminal
    
    restoreCheckoutButtons(); // Safely revert buttons to their standard HTML
}

// NOTE: Ensure your processCraveOrderSubmission 'instant_rebuild' block ALSO calls populatePackAlternatives() right after setting window.currentAlternatives!

// 8. THE DECOUPLED MINI REBUILD TRAY RENDERER
function renderMiniRebuildUI() {
    const container = document.getElementById('mini-pack-builder-container');
    container.innerHTML = '';

    let grandTotal = 0;

    finalGroupedCart.forEach((pack, pIndex) => {
        let itemsSubtotal = pack.items.reduce((sum, item) => sum + (parseFloat(item.price) * item.qty), 0);
        let appliesPackCharge = pack.items.some(item => item.has_charge === true);
        let extraFee = appliesPackCharge ? 50 : 0;
        pack.finalTotal = (itemsSubtotal + (pack.requiresPackFlag ? pack.packContainerCost : 0) + extraFee) * pack.multiplier;
        
        grandTotal += pack.finalTotal;

        let html = `
        <div class="rebuild-pack-card">
            <div class="rebuild-pack-header">
                <span>Bundle ${pack.displayId} ${pack.multiplier > 1 ? `<span style="color:#3b82f6; background:#eff6ff; padding:2px 6px; border-radius:6px;">x${pack.multiplier}</span>` : ''}</span>
                <span style="color: #9539cb;">₦${pack.finalTotal.toLocaleString()}</span>
            </div>`;
        
        // A. Render current active items
        pack.items.forEach((item, iIndex) => {
            const isSoldOut = currentSoldOutIds.includes(String(item.id));
            const statusClass = isSoldOut ? 'sold-out' : '';
            const alertIcon = isSoldOut ? '<i class="bi bi-x-circle-fill" style="color: #ef4444; margin-right: 5px;"></i>' : '';

            html += `
            <div class="rebuild-item-pill ${statusClass}">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <img src="${item.image !== 'placeholder' ? item.image : '/static/images/placeholder.png'}" style="width: 30px; height: 30px; border-radius: 6px; object-fit: cover;">
                    <div>
                        <span class="pill-name" style="font-size: 0.85rem; font-weight: 700;">${alertIcon}${item.name}</span>
                        <div style="font-size: 0.7rem; color: #64748b;">Qty: ${item.qty} | ₦${parseFloat(item.price).toLocaleString()}</div>
                    </div>
                </div>
                <div style="display: flex; gap: 8px;">
                    ${!isSoldOut && !item.is_a_soup ? `
                        <button onclick="adjustRebuildQty(${pIndex}, ${iIndex}, 1)" style="background: #f1f5f9; border:none; border-radius:4px; padding:4px 8px; cursor:pointer; font-weight:bold;">+</button>
                        <button onclick="adjustRebuildQty(${pIndex}, ${iIndex}, -1)" style="background: #f1f5f9; border:none; border-radius:4px; padding:4px 8px; cursor:pointer; font-weight:bold;">-</button>
                    ` : ''}
                    ${isSoldOut ? `
                        <button onclick="removeBrokenItem(${pIndex}, ${iIndex})" style="background: #fee2e2; color: #ef4444; border: 1px solid #fca5a5; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 700;">
                            <i class="bi bi-trash"></i> Remove
                        </button>
                    ` : ''}
                </div>
            </div>`;
        });

        // B. THE MAGIC: Render Independent Alternative Trays
        if (pack.pendingAlts) {
            Object.keys(pack.pendingAlts).forEach(oldId => {
                const altGroup = pack.pendingAlts[oldId];
                if (!altGroup || !altGroup.alts || altGroup.alts.length === 0) return;
                
                html += `
                <div class="alts-wrapper">
                    <div class="alts-title"><i class="bi bi-stars"></i> Replacements for ${altGroup.originalName}</div>
                    <div class="alts-scroll-container">`;
                
                altGroup.alts.forEach(alt => {
                    const safeAltJson = JSON.stringify(alt).replace(/'/g, "&#39;");
                    html += `
                        <div class="alt-mini-card">
                            <img src="${alt.image}" class="alt-mini-img">
                            <div class="alt-mini-name">${alt.name}</div>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span class="alt-mini-price">₦${alt.price.toLocaleString()}</span>
                                <button class="btn-alt-add" onclick='addAlternativeToPack(${pIndex}, ${safeAltJson}, "${oldId}")'>+ Add</button>
                            </div>
                        </div>`;
                });
                
                html += `</div></div>`;
            });
        }

        html += `</div>`;
        container.innerHTML += html;
    });

    const titleHeader = document.querySelector('.kyc-title');
    if (titleHeader) {
        titleHeader.innerHTML = `
            <div class="rebuild-header-flex">
                <span>Review Your Bag</span>
                <span class="rebuild-bag-total">Total: ₦${grandTotal.toLocaleString()}</span>
            </div>`;
    }
}

window.adjustRebuildQty = function(packIndex, itemIndex, delta) {
    const item = finalGroupedCart[packIndex].items[itemIndex];
    if (item.is_a_soup) return; 
    
    if (delta > 0 && item.qty >= 30) return alert("Maximum quantity reached.");
    
    item.qty += delta;
    if (item.qty < 1) finalGroupedCart[packIndex].items.splice(itemIndex, 1);
    renderMiniRebuildUI();
}

// 9. UPGRADED: REMOVE ITEM (Keeps alternatives intact!)
window.removeBrokenItem = function(packIndex, itemIndex) {
    finalGroupedCart[packIndex].items.splice(itemIndex, 1);
    
    // Only delete the pack entirely if it has no items AND no pending alternatives left
    const hasPendingAlts = Object.keys(finalGroupedCart[packIndex].pendingAlts || {}).length > 0;
    if (finalGroupedCart[packIndex].items.length === 0 && !hasPendingAlts) {
        finalGroupedCart.splice(packIndex, 1);
    }
    
    renderMiniRebuildUI();
    checkRebuildStatus();
}

// 9B. UPGRADED: ADD ALTERNATIVE & AUTO-RESOLVE
window.addAlternativeToPack = function(packIndex, altData, originalItemId) {
    const pack = finalGroupedCart[packIndex];
    
    let existingItem = pack.items.find(i => String(i.id) === String(altData.id));
    if (existingItem) {
        existingItem.qty += 1;
    } else {
        pack.items.push({
            id: altData.id, name: altData.name, price: altData.price, image: altData.image, qty: 1,
            needsPack: altData.needsPack, fillingValue: altData.fillingValue, sectionId: altData.sectionId,
            sectionName: altData.sectionName, notOrderedAlone: altData.notOrderedAlone, is_a_soup: altData.is_a_soup,
            need_soup: altData.need_soup, is_strange: altData.is_strange, strange_value: altData.strange_value,
            has_charge: altData.has_charge
        });
    }

    if (originalItemId) {
        // Auto-remove the broken item so the user doesn't have to manually click the trash can
        const brokenIndex = pack.items.findIndex(i => String(i.id) === String(originalItemId));
        if (brokenIndex !== -1) pack.items.splice(brokenIndex, 1);
        
        // Remove the alternatives tray entirely!
        if (pack.pendingAlts && pack.pendingAlts[originalItemId]) {
            delete pack.pendingAlts[originalItemId];
        }
    }
    
    renderMiniRebuildUI();
    checkRebuildStatus();
}

// 10. SUBMIT THE FIXED CART
window.submitRebuiltCart = function() {
    const stillHasBroken = finalGroupedCart.some(p => p.items.some(i => currentSoldOutIds.includes(String(i.id))));
    if (stillHasBroken) {
        alert("Please remove or replace the highlighted sold-out items before continuing.");
        return;
    }
    
    // Clean up empty packs (if they clicked Remove but never added a replacement)
    finalGroupedCart = finalGroupedCart.filter(p => p.items.length > 0);
    
    if (finalGroupedCart.length === 0) {
        alert("Your bag is empty! Please return to the menu.");
        window.location.href = 'javascript:history.back()';
        return;
    }

    document.getElementById('modal-mini-rebuild').classList.remove('active');
    startTerminalSequence();
}
// =================================================================

// --- NEW: DYNAMIC PROMO RECALCULATOR (Transparent Version) ---
window.togglePromoDiscount = function(baseDelivery, surcharges, subtotal) {
    const isChecked = document.getElementById('loyalty-promo-toggle').checked;
    const discountFactor = window.promoPercentage / 100; // e.g., 0.20 for 20%
    
    // Calculate total delivery costs
    const totalDeliveryCost = baseDelivery + surcharges;
    const discountAmount = isChecked ? (totalDeliveryCost * discountFactor) : 0;
    
    // Grab the UI elements
    const deliveryEl = document.getElementById('checkout-delivery');
    const surchargeEl = document.getElementById('checkout-surcharge');
    
    if (isChecked) {
        // Strike out the old price and show the discounted price in pink
        const newBase = baseDelivery * (1 - discountFactor);
        deliveryEl.innerHTML = `<del style="color: #94a3b8; font-size: 0.8rem; margin-right: 6px;">₦${baseDelivery.toLocaleString()}</del> <span style="color: #db2777; font-weight: 800;">₦${newBase.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>`;
        
        if (surchargeEl && surcharges > 0) {
            const newSurcharge = surcharges * (1 - discountFactor);
            surchargeEl.innerHTML = `<del style="color: #94a3b8; font-size: 0.8rem; margin-right: 6px;">₦${surcharges.toLocaleString()}</del> <span style="color: #db2777; font-weight: 800;">₦${newSurcharge.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>`;
        }
    } else {
        // Revert to normal
        deliveryEl.innerText = `₦${baseDelivery.toLocaleString()}`;
        if (surchargeEl && surcharges > 0) {
            surchargeEl.innerText = `₦${surcharges.toLocaleString()}`;
        }
    }

    // Update Grand Total
    const newTotal = subtotal + totalDeliveryCost - discountAmount;
    document.getElementById('checkout-total').innerText = `₦${newTotal.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
}

// --- NEW: CLOSE PROXY MODAL & SAVE PREFERENCE ---
window.closeProxyModal = function() {
    document.getElementById('modal-proxy-intro').classList.remove('active');
    // Set item in localStorage so it doesn't pop up again for this device
    localStorage.setItem('luxa_proxy_intro_seen', 'true');
}
