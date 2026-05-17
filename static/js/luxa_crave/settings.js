// NAVIGATION: Section Switcher
function showSection(sectionId, element) {
    // 1. Hide ALL panels
    document.querySelectorAll('.settings-panel').forEach(panel => {
        panel.style.display = 'none';
    });

    // 2. Show the targeted panel
    document.getElementById(sectionId).style.display = 'block';

    // 3. Reset all navigation links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.style.background = 'transparent';
        link.style.color = '#475569';
        link.style.fontWeight = '500';
    });

    // 4. Highlight the active link
    element.style.background = '#eff6ff';
    element.style.color = '#3b82f6';
    element.style.fontWeight = '600';
}

// THEME SAVER: Updates UI and DB
function saveTheme(themeValue) {
    // 1. Update UI Classes
    document.body.className = 'theme-' + themeValue;
    const wrapper = document.getElementById('settings-wrapper');
    if (wrapper) wrapper.className = 'theme-' + themeValue;

    // 2. Visual Feedback on Cards
    document.querySelectorAll('.theme-card').forEach(card => {
        card.classList.remove('active');
        if (card.getAttribute('onclick').includes(themeValue)) {
            card.classList.add('active');
        }
    });

    // 3. Database Save
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    fetch('/api/update-settings/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({
            'field': 'selected_theme',
            'value': themeValue,
            'profile_id': '{{ settings_hub.profile.id }}'
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log("Theme synchronization successful:", themeValue);
    });
}

// --- PREVIEW IMAGE BEFORE UPLOADING ---
function previewProxyImage(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('proxy-image-preview');
            const icon = document.getElementById('proxy-cam-icon');
            
            preview.style.backgroundImage = `url('${e.target.result}')`;
            preview.style.borderStyle = 'solid';
            preview.style.borderColor = 'transparent';
            preview.style.boxShadow = '0 4px 10px rgba(0,0,0,0.1)';
            if (icon) icon.style.display = 'none'; // Hide the camera icon
        }
        reader.readAsDataURL(file);
    }
}

// --- REWRITTEN PROXY SAVER (Using FormData) ---
function saveProxySettings() {
    const btn = document.getElementById('btn-save-proxy');
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
    btn.disabled = true;

    // Using FormData instead of JSON so we can send the image file securely
    const formData = new FormData();
    formData.append('proxy_name', document.getElementById('proxy-name').value);
    formData.append('proxy_location_id', document.getElementById('proxy-location').value);
    formData.append('proxy_building_id', document.getElementById('proxy-building').value);
    formData.append('proxy_address', document.getElementById('proxy-room').value);
    // NEW: Grab the gender value and send it to Django
    formData.append('proxy_gender', document.getElementById('proxy-gender').value);
    formData.append('proxy_seed_phrase_hash', document.getElementById('proxy-seed-phrase').value);

    // Append the image file if they uploaded one
    const imageInput = document.getElementById('proxy-image-input');
    if (imageInput.files.length > 0) {
        formData.append('proxy_photo', imageInput.files[0]);
    }

    fetch('/api/update-proxy/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Saved Successfully!';
            btn.style.background = '#22c55e';
        } else {
            // If the backend fails, this will now tell you exactly why!
            alert("Backend Error: " + data.message);
            btn.innerHTML = '<i class="bi bi-x-circle"></i> Error Saving';
            btn.style.background = '#ef4444';
        }
        setTimeout(() => { btn.innerHTML = originalText; btn.style.background = 'var(--accent, #3b82f6)'; btn.disabled = false; }, 2500);
    })
    .catch(err => {
        console.error(err);
        btn.innerHTML = '<i class="bi bi-wifi-off"></i> Network Error';
        btn.style.background = '#ef4444';
        setTimeout(() => { btn.innerHTML = originalText; btn.style.background = 'var(--accent, #3b82f6)'; btn.disabled = false; }, 2500);
    });
}

// NEW: Handles the Toggle Switch
function toggleProxyState() {
    const isEnabled = document.getElementById('proxy-toggle').checked;
    const formContainer = document.getElementById('proxy-form-container');
    const disabledMsg = document.getElementById('proxy-disabled-msg');
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    // 1. Instant Visual Update
    if (isEnabled) {
        formContainer.classList.remove('disabled-form');
        disabledMsg.style.display = 'none';
    } else {
        formContainer.classList.add('disabled-form');
        disabledMsg.style.display = 'block';
    }

    // 2. Save the state to the backend
    fetch('/api/toggle-proxy-status/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({ 'proxy_enabled': isEnabled })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status !== 'success') {
            console.error("Failed to update status");
        }
    })
    .catch(err => console.error("Network error:", err));
}

// --- TOGGLE ADDRESS VIEWS ---
function toggleAddressEdit(showForm) {
    const displayPanel = document.getElementById('customer-address-display');
    const formPanel = document.getElementById('customer-address-form');
    
    if (showForm) {
        displayPanel.style.display = 'none';
        formPanel.style.display = 'block';
    } else {
        formPanel.style.display = 'none';
        displayPanel.style.display = 'block';
        displayPanel.style.animation = 'fadeIn 0.3s ease'; // Trigger subtle fade
    }
}

// --- CUSTOMER ADDRESS SAVER ---
function saveCustomerAddress() {
    const locationSelect = document.getElementById('customer-location');
    const buildingSelect = document.getElementById('customer-building');
    const roomInput = document.getElementById('customer-room');
    
    const locationId = locationSelect.value;
    const buildingId = buildingSelect.value;
    const room = roomInput.value;
    
    // Basic validation
    if(!locationId || !buildingId || !room) {
        return alert("Please select your Hostel, Wing, and enter a Room Number.");
    }
    
    const btn = document.getElementById('btn-save-address');
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
    btn.disabled = true;

    fetch('/api/update-customer-address/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({
            'location_id': locationId,
            'building_id': buildingId,
            'room_number': room
        })
    })
    .then(response => response.json())
    .then(data => {
        if(data.status === 'success') {
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Saved Successfully!';
            btn.style.background = '#22c55e';
            
            // 1. Get the actual text names from the dropdowns so we can update the UI
            const locName = locationSelect.options[locationSelect.selectedIndex].text;
            const bldgName = buildingSelect.options[buildingSelect.selectedIndex].text;
            
            // 2. Dynamically update the Display Panel text
            document.getElementById('display-loc-name').innerText = locName;
            document.getElementById('display-bldg-room').innerText = `${bldgName} — Room ${room}`;
            
            // 3. Make sure the 'Cancel' button becomes visible for future edits
            document.getElementById('btn-cancel-address').style.display = 'block';

            // 4. Slide back to the display panel after a brief pause
            setTimeout(() => { 
                toggleAddressEdit(false);
                btn.innerHTML = originalText; 
                btn.style.background = 'var(--accent, #3b82f6)'; 
                btn.disabled = false; 
            }, 1000);

        } else {
            btn.innerHTML = '<i class="bi bi-x-circle"></i> Error Saving';
            btn.style.background = '#ef4444';
            setTimeout(() => { btn.innerHTML = originalText; btn.style.background = 'var(--accent, #3b82f6)'; btn.disabled = false; }, 2500);
        }
    })
    .catch(err => {
        console.error(err);
        btn.innerHTML = '<i class="bi bi-x-circle"></i> Error Saving';
        btn.style.background = '#ef4444';
        setTimeout(() => { btn.innerHTML = originalText; btn.style.background = 'var(--accent, #3b82f6)'; btn.disabled = false; }, 2500);
    });
}

// --- DYNAMIC CASCADING DROPDOWN LOGIC ---
function filterBuildings(zoneSelectId, buildingSelectId) {
    // Fallbacks just in case it gets called without arguments
    const zId = zoneSelectId || 'proxy-location';
    const bId = buildingSelectId || 'proxy-building';

    const zoneElement = document.getElementById(zId);
    const buildingElement = document.getElementById(bId);

    if (!zoneElement || !buildingElement) return;

    const zoneValue = zoneElement.value;
    const buildingOptions = buildingElement.querySelectorAll('option');

    let isCurrentSelectionValid = false;

    buildingOptions.forEach(option => {
        // Always show the default "Select a Building..." placeholder
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

// Run this function immediately when the page loads for BOTH dropdowns
document.addEventListener('DOMContentLoaded', () => {
    filterBuildings('proxy-location', 'proxy-building');
    filterBuildings('customer-location', 'customer-building');
    if (window.location.hash === '#proxy-section') {
        const proxyLink = document.querySelector('a[onclick*="proxy-section"]');
        if (proxyLink) showSection('proxy-section', proxyLink);
    }
});


// PRESET LOGIC
// --- DELETE PRESET FROM SETTINGS ---
function deleteSettingsPreset(presetId, btnElement) {
    if (!confirm("Are you sure you want to permanently delete this preset?")) return;

    const originalHtml = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="bi bi-hourglass"></i> Deleting...';
    btnElement.disabled = true;

    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch(`/api/delete-preset/${presetId}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const card = document.getElementById(`settings-preset-${presetId}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    card.remove();
                    // If grid is empty, refresh to show the empty state
                    if (document.querySelectorAll('.preset-settings-card').length === 0) {
                        window.location.reload(); 
                    }
                }, 300);
            }
        } else {
            alert("Error deleting preset.");
            btnElement.innerHTML = originalHtml;
            btnElement.disabled = false;
        }
    })
    .catch(err => {
        console.error(err);
        btnElement.innerHTML = originalHtml;
        btnElement.disabled = false;
    });
}

// --- VIEW PRESET DETAILS LOGIC ---
function viewPresetDetails(presetId) {
    const modal = document.getElementById('presetDetailsModal');
    const contentDiv = document.getElementById('presetDetailsContent');
    
    // Open modal & show loading animation
    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
    contentDiv.innerHTML = '<div style="text-align:center; padding: 40px; color: #94a3b8;"><i class="bi bi-arrow-repeat" style="font-size: 2rem; display: inline-block; animation: spin 1s linear infinite;"></i><p>Loading details...</p></div>';

    // Add keyframes for the spinner dynamically if it doesn't exist
    if (!document.getElementById('spinKeyframes')) {
        const style = document.createElement('style');
        style.id = 'spinKeyframes';
        style.innerHTML = `@keyframes spin { 100% { transform: rotate(360deg); } }`;
        document.head.appendChild(style);
    }

    // Fetch current live data from the API
    fetch(`/api/get-preset/${presetId}/`)
        .then(res => res.json())
        .then(data => {
            if(data.status === 'success') {
                const pd = data.pack_data;
                let itemsHtml = '';
                let itemsTotal = 0;
                let needsPackFlag = false;

                // Loop through the items
                pd.items.forEach(item => {
                    const itemSubtotal = item.price * item.qty;
                    itemsTotal += itemSubtotal;
                    if (item.needsPack) needsPackFlag = true;

                    itemsHtml += `
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f1f5f9;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 45px; height: 45px; border-radius: 10px; background: #f8fafc; overflow: hidden; display: flex; align-items: center; justify-content: center; border: 1px solid #e2e8f0;">
                                    ${item.image !== 'placeholder' ? `<img src="${item.image}" style="width: 100%; height: 100%; object-fit: cover;">` : `<i class="bi bi-cup-hot" style="color: #94a3b8; font-size: 1.2rem;"></i>`}
                                </div>
                                <div>
                                    <div style="font-weight: 700; color: #1e293b; font-size: 0.95rem;">${item.name}</div>
                                    <div style="font-size: 0.8rem; color: #64748b;">${item.qty}x ₦${item.price.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
                                </div>
                            </div>
                            <div style="font-weight: 800; color: #1e293b; font-size: 0.95rem;">
                                ₦${itemSubtotal.toLocaleString(undefined, {minimumFractionDigits: 2})}
                            </div>
                        </div>
                    `;
                });

                // Determine pack cost
                const packCost = needsPackFlag ? pd.packContainerCost : 0;
                const finalTotal = itemsTotal + packCost;

                // Render Final HTML
                contentDiv.innerHTML = `
                    <div style="margin-bottom: 20px;">
                        <h3 style="margin: 0 0 5px 0; color: #1e293b; font-size: 1.1rem;">${pd.preset_name}</h3>
                        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 10px; border-radius: 8px; font-size: 0.85rem; color: #166534; display: flex; justify-content: space-between;">
                            <span><i class="bi bi-box-seam"></i> <b>${pd.packContainerName}</b></span>
                            <span>+₦${packCost.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                        </div>
                    </div>
                    
                    <div style="max-height: 250px; overflow-y: auto; padding-right: 10px; margin-bottom: 20px;">
                        ${itemsHtml}
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 15px; border-top: 2px dashed #e2e8f0;">
                        <span style="font-weight: 700; color: #64748b; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px;">Current Total</span>
                        <span style="font-size: 1.3rem; font-weight: 800; color: var(--accent, #3b82f6);">₦${finalTotal.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                    </div>
                `;
            } else {
                contentDiv.innerHTML = `<div style="text-align:center; color:#ef4444; padding: 20px;"><i class="bi bi-exclamation-triangle" style="font-size: 2rem;"></i><br>Error loading details.</div>`;
            }
        })
        .catch(err => {
            console.error(err);
            contentDiv.innerHTML = `<div style="text-align:center; color:#ef4444; padding: 20px;"><i class="bi bi-wifi-off" style="font-size: 2rem;"></i><br>Network Error</div>`;
        });
}

function closePresetDetailsModal() {
    const modal = document.getElementById('presetDetailsModal');
    modal.classList.remove('show');
    setTimeout(() => modal.style.display = 'none', 300);
}

let activeOrderPolling;
let currentlyViewingOrderId = null; // Tracks if a modal is currently open

// --- VIEW ORDER DETAILS LOGIC ---
function viewOrderDetails(orderId, isSilentUpdate = false) {
    currentlyViewingOrderId = orderId;
    const modal = document.getElementById('orderDetailsModal');
    const contentDiv = document.getElementById('orderDetailsContent');
    
    // Only show the loading spinner if this is a manual click, not a background poll
    if (!isSilentUpdate) {
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('show'), 10);
        contentDiv.innerHTML = '<div style="text-align:center; padding: 40px; color: #94a3b8;"><i class="bi bi-arrow-repeat" style="font-size: 2rem; display: inline-block; animation: spin 1s linear infinite;"></i><p>Fetching receipt...</p></div>';
    }

    fetch(`/api/get-order/${orderId}/`)
        .then(res => res.json())
        .then(data => {
            if(data.status === 'success') {
                const od = data.order_data;
                let packsHtml = '';

                // Loop through the specific packs in this order
                od.packs.forEach((pack, index) => {
                    let itemsHtml = '';
                    pack.items.forEach(item => {
                        itemsHtml += `
                            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #475569; margin-bottom: 5px;">
                                <span>${item.qty}x ${item.name}</span>
                                <span>₦${item.subtotal.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                            </div>
                        `;
                    });

                    // --- CONDITIONAL PACK HEADER ---
                    let packHeaderHtml = '';
                    const isPhysicalPack = pack.pack_name && 
                                           pack.pack_name !== 'Loose Items' && 
                                           pack.pack_name !== 'Custom Pack' && 
                                           pack.pack_name !== 'No Pack' &&
                                           pack.pack_name !== 'None';
                    
                    if (isPhysicalPack) {
                        const packCostDisplay = pack.pack_cost ? ` - ₦${pack.pack_cost.toLocaleString(undefined, {minimumFractionDigits: 2})}` : '';
                        packHeaderHtml = `<strong style="color: #1e293b; font-size: 0.95rem;">Bundle ${index + 1} <span style="color: #64748b; font-size: 0.8rem; font-weight: 500;">(${pack.pack_name}${packCostDisplay})</span></strong>`;
                    } else {
                        packHeaderHtml = `<strong style="color: #1e293b; font-size: 0.95rem;">Bundle ${index + 1} <span style="color: #ef4444; font-size: 0.75rem; font-weight: 600; background: #fef2f2; padding: 2px 6px; border-radius: 6px; margin-left: 5px; border: 1px solid #fecaca;">No Physical Pack</span></strong>`;
                    }

                    packsHtml += `
                        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 15px; margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed #cbd5e1; padding-bottom: 10px; margin-bottom: 10px;">
                                ${packHeaderHtml}
                                <span style="font-weight: 800; color: #3b82f6;">x${pack.multiplier}</span>
                            </div>
                            ${itemsHtml}
                            <div style="text-align: right; margin-top: 10px; font-size: 0.9rem; font-weight: 800; color: #1e293b;">
                                Total: ₦${pack.pack_total.toLocaleString(undefined, {minimumFractionDigits: 2})}
                            </div>
                        </div>
                    `;
                });

                // --- NEW: STATUS PROGRESSION UI LOGIC ---
                let statusHtml = '';
                const isCancelled = od.raw_status === 'cancelled' || od.raw_status === 'refunded';
                
                if (isCancelled) {
                    // If cancelled, just show the single badge. No progression needed.
                    statusHtml = `<div class="order-status badge-${od.raw_status}" style="display: inline-block; margin-bottom: 15px; font-size: 0.85rem;">${od.status} 😔</div>`;
                } else {
                    // Define the strict lifecycle of a campus order
                    const statusFlow = [
                        { raw: 'pending', display: 'Pending' },
                        { raw: 'processing', display: 'Processing' },
                        { raw: 'assigned', display: 'Assigned' },
                        { raw: 'in_transit', display: 'In Transit' },
                        { raw: 'delivered', display: 'Delivered' }
                    ];

                    const currentIndex = statusFlow.findIndex(s => s.raw === od.raw_status);

                    if (currentIndex === -1) {
                        // Fallback if somehow a weird status slips through
                        statusHtml = `<div class="order-status badge-${od.raw_status}" style="display: inline-block; margin-bottom: 15px; font-size: 0.85rem;">${od.status}</div>`;
                    } else {
                        const prevStatus = currentIndex > 0 ? statusFlow[currentIndex - 1] : null;
                        const nextStatus = currentIndex < statusFlow.length - 1 ? statusFlow[currentIndex + 1] : null;
                        
                        // --- UPDATED: Using CSS classes for mobile responsiveness ---
                        const dottedArrowHtml = `
                        <div class="tracker-arrow">
                            <span style="letter-spacing: 2px; font-size: 0.8rem; font-weight: 800;">•••</span>
                            <i class="bi bi-chevron-right" style="font-size: 0.7rem; font-weight: 800;"></i>
                        </div>`;

                        let uiParts = [];

                        // 1. Previous Status
                        if (prevStatus) {
                            uiParts.push(`<span class="tracker-text">${prevStatus.display}</span>`);
                            uiParts.push(dottedArrowHtml);
                        }

                        // 2. Current Status
                        uiParts.push(`<div class="order-status badge-${od.raw_status}" style="margin: 0; font-size: 0.85rem; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">${od.status}</div>`);

                        // 3. Next Status
                        if (nextStatus) {
                            uiParts.push(dottedArrowHtml);
                            uiParts.push(`<span class="tracker-text">${nextStatus.display}</span>`);
                        }

                        // Wrapper
                        statusHtml = `
                            <div class="order-status-tracker">
                                ${uiParts.join('')}
                            </div>
                        `;
                    }
                }

                // Render Final Receipt HTML
                contentDiv.innerHTML = `
                    <div style="text-align: center; margin-bottom: 25px;">
                        ${statusHtml}
                        <h2 style="margin: 0; color: #1e293b; font-size: 1.7rem; font-weight: 800;">₦${od.total_cost.toLocaleString(undefined, {minimumFractionDigits: 2})}</h2>
                        <span style="color: #64748b; font-size: 0.85rem;">Order ID: ${od.order_number}</span><br>
                        <span style="color: #64748b; font-size: 0.85rem;">Date: ${od.date}</span>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <strong style="font-size: 0.85rem; color: #94a3b8; text-transform: uppercase;">Delivery Location</strong>
                        <div style="background: white; border: 1px solid #e2e8f0; padding: 12px; border-radius: 8px; margin-top: 5px; font-size: 0.95rem; color: #1e293b; font-weight: 600;">
                            <i class="bi bi-geo-alt-fill" style="color: #3b82f6; margin-right: 8px;"></i> ${od.address}
                        </div>
                    </div>
                    
                    <div style="max-height: 280px; overflow-y: auto; padding-right: 5px; margin-bottom: 20px;">
                        <strong style="font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; display: block; margin-bottom: 10px;">Order Summary</strong>
                        ${packsHtml}
                        
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px; color: #d97706; font-weight: 600; font-size: 0.9rem;">
                            <span>Delivery Fee</span>
                            <span>+₦${od.delivery_fee.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                        </div>
                    </div>
                `;
            } else {
                contentDiv.innerHTML = `
                    <div style="text-align:center; color:#ef4444; padding: 20px;">
                        <i class="bi bi-exclamation-triangle" style="font-size: 2rem; margin-bottom: 10px;"></i>
                        <br><strong style="font-size: 1.1rem;">Error loading receipt</strong>
                        <p style="font-size: 0.85rem; color: #64748b; margin-top: 10px; background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0;">
                            ${data.message || "Unknown server error"}
                        </p>
                    </div>`;
                console.error("Backend Receipt Error:", data.message);
            }            
        })
        .catch(err => {
            console.error(err);
            contentDiv.innerHTML = `<div style="text-align:center; color:#ef4444; padding: 20px;"><i class="bi bi-wifi-off" style="font-size: 2rem;"></i><br>Network Error</div>`;
        });
}

function closeOrderDetailsModal() {
    currentlyViewingOrderId = null;
    const modal = document.getElementById('orderDetailsModal');
    modal.classList.remove('show');
    setTimeout(() => modal.style.display = 'none', 300);
}

// --- SILENT BACKGROUND POLLING - For getting order updates---
function startOrderStatusPolling() {
    // Poll every 15 seconds (15000 milliseconds)
    activeOrderPolling = setInterval(() => {
        // Only poll if they are actually looking at the Orders section to save bandwidth
        const ordersPanel = document.getElementById('orders-section');
        if (ordersPanel && ordersPanel.style.display === 'none') return;

        fetch('/api/get-active-orders-status/') // Ensure this matches your urls.py
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                const orders = data.orders;
                
                for (const [orderId, statusData] of Object.entries(orders)) {
                    // 1. Update the list badge
                    const badge = document.getElementById(`status-badge-${orderId}`);
                    if (badge) {
                        // Swap the CSS class for colors, and update the text
                        badge.className = `order-status badge-${statusData.raw}`;
                        badge.innerText = statusData.display;
                    }

                    // 2. MAGIC: If they are actively staring at this specific order's modal, refresh the tracker silently!
                    if (currentlyViewingOrderId === orderId) {
                        // Pass 'true' to trigger the silent update (no loading spinner flash)
                        viewOrderDetails(orderId, true); 
                    }
                }
            }
        })
        .catch(err => console.error('Silent polling error:', err));
    }, 15000);
}

// Start the engine when the page loads
document.addEventListener('DOMContentLoaded', () => {
    startOrderStatusPolling();
});

// --- SMART SIDEBAR LOGIC ---
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.querySelector('.settings-nav-sidebar');
    
    if (sidebar) {
        // 1. Expand on click anywhere inside sidebar
        sidebar.addEventListener('click', (e) => {
            if (!sidebar.classList.contains('expanded')) {
                sidebar.classList.add('expanded');
            } else if (e.target === sidebar || e.target.classList.contains('nav-header')) {
                // Smart Collapse: If it is already expanded and they click the blank "dead space" 
                // or header inside the sidebar, it smoothly collapses again.
                sidebar.classList.remove('expanded');
            }
        });

        // 2. Auto-Close when clicking outside the sidebar
        document.addEventListener('click', (e) => {
            if (!sidebar.contains(e.target)) {
                sidebar.classList.remove('expanded');
            }
        });
        
        // 3. Auto-Close on Mobile after selecting a menu item
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 1024 && sidebar.classList.contains('expanded')) {
                    // Small delay lets the user see the click ripple before it snaps shut
                    setTimeout(() => sidebar.classList.remove('expanded'), 400);
                }
            });
        });
    }
});

// --- URL HASH LISTENER (Auto-open tabs based on URL) ---
document.addEventListener('DOMContentLoaded', () => {
    // Check if there's a hash in the URL (e.g., "#orders-section")
    const hash = window.location.hash; 
    
    if (hash) {
        // Remove the '#' to just get "orders-section"
        const sectionId = hash.substring(1); 
        
        // Find the sidebar link that corresponds to this section
        const targetLink = document.querySelector(`a[onclick*="${sectionId}"]`);
        
        if (targetLink) {
            // Virtually "click" the button so it triggers your existing showSection logic!
            targetLink.click(); 
        } else {
            // Fallback: Just show the panel if the button isn't found
            document.querySelectorAll('.settings-panel').forEach(p => p.style.display = 'none');
            const targetPanel = document.getElementById(sectionId);
            if (targetPanel) targetPanel.style.display = 'block';
        }
    }
});
