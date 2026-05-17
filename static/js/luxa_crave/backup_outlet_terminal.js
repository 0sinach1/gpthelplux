// --- STATE MANAGEMENT ---
// Using 'var' and the check from the working version to prevent re-declaration errors
if (typeof selectedPackConfigId === 'undefined') {
    var selectedPackConfigId = null; 
}

let currentPackItems = []; 
let packCounter = 1; 
let uniquePackIdCounter = 1; 
let packContainerCost = 0; 
let packContainerName = "No Pack Selected";
let requiresPackFlag = false;
let editingPackOriginal = null; 
let packMaxCapacity = Infinity; 
let packMaxOverflow = Infinity; 
let globalCartPacks = [];

// --- GLOBAL SAFETY LIMITS ---
const GLOBAL_MAX_ITEM_QTY = 30;    
const MAX_MULTIPLIER_PER_PACK = 10; 
const MAX_TOTAL_PACKS_IN_BAG = 20;  

// --- PERSISTENCE LOGIC ---
const STORAGE_KEY = 'crave_terminal_state';
const EXPIRY_TIME = 2 * 60 * 60 * 1000; 

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

function saveToLocalStorage() {
    const data = {
        timestamp: Date.now(),
        globalCartPacks,
        currentPackItems,
        selectedPackConfigId,
        packCounter,
        uniquePackIdCounter,
        requiresPackFlag,
        packMaxCapacity,
        packMaxOverflow,
        packContainerName,
        packContainerCost
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function loadFromLocalStorage() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;

    const data = JSON.parse(saved);
    if (Date.now() - data.timestamp > EXPIRY_TIME) {
        localStorage.removeItem(STORAGE_KEY);
        return;
    }

    globalCartPacks = data.globalCartPacks || [];
    selectedPackConfigId = data.selectedPackConfigId || null;
    currentPackItems = data.currentPackItems || [];
    packCounter = data.packCounter || 1;
    uniquePackIdCounter = data.uniquePackIdCounter || 1;
    requiresPackFlag = data.requiresPackFlag || false;
    packMaxCapacity = data.packMaxCapacity || Infinity;
    packMaxOverflow = data.packMaxOverflow || Infinity;
    packContainerName = data.packContainerName || "No Pack Selected";
    packContainerCost = data.packContainerCost || 0;

    if (currentPackItems.length > 0) {
        panel.classList.remove('hidden');
        if (requiresPackFlag) packSizeSelector.classList.remove('hidden');
        renderPackTray();
        updatePackTotal();
    }
    renderCart();
}

window.addEventListener('DOMContentLoaded', loadFromLocalStorage);

const panel = document.getElementById('pack-builder-panel');
const tray = document.getElementById('pack-items-tray');
const packSizeSelector = document.getElementById('pack-size-selector');
const totalPriceEl = document.getElementById('pack-total-price');
const packNameEl = document.getElementById('current-pack-name');
const cartContainer = document.getElementById('cart-items-container');
const dropZone = document.getElementById('pack-drop-zone');

// --- SMOOTH SCROLLING ---
document.querySelectorAll('.nav-pill').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        document.querySelectorAll('.nav-pill').forEach(p => p.classList.remove('active'));
        this.classList.add('active');
        const targetId = this.getAttribute('href');
        const targetSection = document.querySelector(targetId);
        if (targetSection) {
            const offset = 140; 
            const top = targetSection.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({ top: top, behavior: 'smooth' });
        }
    });
});

// --- DRAG AND DROP & HOLD LOGIC ---
document.querySelectorAll('.product-card').forEach(card => {
    let pressTimer;
    const startHold = () => {
        pressTimer = setTimeout(() => {
            panel.classList.remove('hidden');
            dropZone.classList.add('active');
        }, 1000);
    };
    const cancelHold = () => clearTimeout(pressTimer);

    card.addEventListener('mousedown', startHold);
    card.addEventListener('touchstart', startHold);
    card.addEventListener('mouseup', cancelHold);
    card.addEventListener('mouseleave', cancelHold);
    card.addEventListener('touchend', cancelHold);

    card.addEventListener('dragstart', (e) => {
        cancelHold();
        panel.classList.remove('hidden');
        dropZone.classList.add('active');
        card.classList.add('dragging');
        
        const btn = card.querySelector('.btn-add');
        const itemData = {
            id: card.getAttribute('data-item-id') || btn.getAttribute('data-item-id'),
            name: card.getAttribute('data-name') || btn.getAttribute('data-name'),
            price: parseFloat(String(card.getAttribute('data-price') || btn.getAttribute('data-price')).replace(/,/g, '')),
            image: card.getAttribute('data-image') || btn.getAttribute('data-image'),
            needsPack: (card.getAttribute('data-requires-pack') || btn.getAttribute('data-requires-pack')) === 'true',
            fillingValue: parseFloat(card.getAttribute('data-filling-value')) || 0, 
            sectionId: card.getAttribute('data-section-id') || btn.getAttribute('data-section-id'),
            notOrderedAlone: (card.getAttribute('data-not-ordered-alone') || btn.getAttribute('data-not-ordered-alone')) === 'true',
        };
        e.dataTransfer.setData('text/plain', JSON.stringify(itemData));
    });

    card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        dropZone.classList.remove('active', 'drag-over');
        if (currentPackItems.length === 0) panel.classList.add('hidden');
    });
});

panel.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
panel.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
panel.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('active', 'drag-over');
    try {
        const data = JSON.parse(e.dataTransfer.getData('text/plain'));
        processItemAddition(data);
    } catch (err) { console.error("Drop parsing failed:", err); }
});

function changePackMultiplier(delta) {
    const input = document.getElementById('global-pack-multiplier');
    let val = parseInt(input.value) || 1;
    if (delta > 0 && val >= MAX_MULTIPLIER_PER_PACK) {
        showToast(`You can only order a maximum of ${MAX_MULTIPLIER_PER_PACK} of the same pack.`);
        return;
    }
    val += delta;
    if (val < 1) val = 1;
    input.value = val;
    updatePackTotal();
    saveToLocalStorage();
}

function changeItemQty(index, delta) {
    const item = currentPackItems[index];
    if (item.qty + delta >= 1) {
        if (delta > 0) {
            if (item.qty >= GLOBAL_MAX_ITEM_QTY) {
                showToast(`Maximum ${GLOBAL_MAX_ITEM_QTY} units of ${item.name} allowed per pack.`);
                return;
            }
            const currentBoxFill = currentPackItems.reduce((sum, i) => i.needsPack ? sum + (i.fillingValue * i.qty) : sum, 0);
            const currentTotalPayload = currentPackItems.reduce((sum, i) => sum + (i.fillingValue * i.qty), 0);
            if (item.needsPack && (currentBoxFill + item.fillingValue) > packMaxCapacity) {
                showToast("The box is full!");
                return;
            }
            if ((currentTotalPayload + item.fillingValue) > packMaxOverflow) {
                showToast("Weight limit reached!");
                return;
            }
        }
        item.qty += delta;
        renderPackTray();
        updatePackTotal();
        saveToLocalStorage();
    }
}

function processItemAddition(data) {
    if (!data.id) return;
    const currentTotalInBag = globalCartPacks.reduce((sum, p) => sum + (p.multiplier || 1), 0);
    if (currentTotalInBag >= MAX_TOTAL_PACKS_IN_BAG) {
        showToast("Courier bag limit reached! Please checkout this order before buying more.");
        return;
    }
    if (currentPackItems.length > 0 && data.sectionId !== currentPackItems[0].sectionId) {
        showToast("Items from different sections cannot be placed in the same pack.");
        return; 
    }
    let existingItem = currentPackItems.find(i => i.id == data.id);
    if (existingItem && existingItem.qty >= GLOBAL_MAX_ITEM_QTY) {
        showToast(`Limit reached: Maximum ${GLOBAL_MAX_ITEM_QTY} units of this item per pack.`);
        return;
    }
    const fillingValue = parseFloat(data.fillingValue) || 0;
    const currentBoxFill = currentPackItems.reduce((sum, i) => i.needsPack ? sum + (i.fillingValue * i.qty) : sum, 0);
    const currentTotalPayload = currentPackItems.reduce((sum, i) => sum + (i.fillingValue * i.qty), 0);
    if (data.needsPack && (currentBoxFill + fillingValue) > packMaxCapacity) {
        showToast("The box is full! Try a larger pack.");
        return;
    }
    if ((currentTotalPayload + fillingValue) > packMaxOverflow) {
        showToast("This pack has reached its absolute weight limit.");
        return;
    }

    if (existingItem) {
        existingItem.qty += 1;
    } else {
        currentPackItems.push({ 
            id: data.id, name: data.name, price: data.price, image: data.image, qty: 1,
            needsPack: data.needsPack, fillingValue: fillingValue, sectionId: data.sectionId, notOrderedAlone: data.notOrderedAlone 
        });
    }

    panel.classList.remove('hidden');
    packNameEl.innerText = `Pack ${packCounter}`;
    if (data.needsPack && !requiresPackFlag) {
        requiresPackFlag = true;
        packSizeSelector.classList.remove('hidden');
        const firstPackPill = packSizeSelector.querySelector('.size-pill');
        if (firstPackPill) firstPackPill.click();
    }
    renderPackTray();
    updatePackTotal();
    saveToLocalStorage();
}

function showToast(message) {
    const existingToast = document.getElementById('crave-toast');
    if (existingToast) existingToast.remove();
    const toast = document.createElement('div');
    toast.id = 'crave-toast';
    toast.innerHTML = `<i class="bi bi-exclamation-triangle-fill" style="margin-right: 8px;"></i> ${message}`;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 4500);
}

function addToPackFromClick(btn) {
    const card = btn.closest('.product-card');
    const data = {
        id: card.getAttribute('data-item-id') || btn.getAttribute('data-item-id'),
        name: card.getAttribute('data-name') || btn.getAttribute('data-name'),
        price: parseFloat(String(card.getAttribute('data-price') || btn.getAttribute('data-price')).replace(/,/g, '')),
        image: card.getAttribute('data-image') || btn.getAttribute('data-image'),
        needsPack: (card.getAttribute('data-requires-pack') || btn.getAttribute('data-requires-pack')) === 'true',
        fillingValue: parseFloat(card.getAttribute('data-filling-value')) || 0, 
        sectionId: card.getAttribute('data-section-id') || btn.getAttribute('data-section-id'),
        notOrderedAlone: (card.getAttribute('data-not-ordered-alone') || btn.getAttribute('data-not-ordered-alone')) === 'true'
    };
    processItemAddition(data);

    // Keep the "Original" button animation
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check2"></i>';
    btn.style.background = '#2d1a11';
    btn.style.color = 'white';
    setTimeout(() => {
        btn.innerHTML = originalHtml;
        btn.style.background = '#f4fbf7';
        btn.style.color = '#16a34a';
    }, 800);
}

function renderPackTray() {
    if (currentPackItems.length === 0) {
        tray.innerHTML = '<div class="empty-tray-msg">Select items to add to this pack...</div>';
        return;
    }
    tray.innerHTML = ''; 
    currentPackItems.forEach((item, index) => {
        const imgHtml = item.image !== 'placeholder' 
            ? `<img src="${item.image}" alt="${item.name}">` 
            : `<div class="pill-img-ph"><i class="bi bi-cup-hot"></i></div>`;

        tray.innerHTML += `
            <div class="item-pill fade-in">
                <div style="position: relative;">${imgHtml}</div>
                <div class="item-pill-info">
                    <span class="pill-name">${item.name}</span>
                    <div class="item-qty-stepper">
                        <button onclick="changeItemQty(${index}, -1)">-</button>
                        <span>${item.qty}</span>
                        <button onclick="changeItemQty(${index}, 1)">+</button>
                    </div>
                </div>
                <button class="btn-remove-pill" onclick="deleteItemCompletely(${index})" title="Remove All">
                    <i class="bi bi-trash"></i>
                </button>
            </div>`;
    });
}

function selectPackSize(element, price, name, maxCap, maxOver, configId) {
    selectedPackConfigId = configId; 
    const newMaxCap = parseFloat(maxCap) || 0;
    const newMaxOver = parseFloat(maxOver) || 0;
    const currentBoxFill = currentPackItems.reduce((sum, i) => i.needsPack ? sum + (i.fillingValue * i.qty) : sum, 0);
    const currentTotalPayload = currentPackItems.reduce((sum, i) => sum + (i.fillingValue * i.qty), 0);

    if (currentBoxFill > newMaxCap || currentTotalPayload > newMaxOver) {
        showToast(`Items already in tray cannot fit in a ${name}.`);
        return; 
    }
    document.querySelectorAll('.size-pill').forEach(el => el.classList.remove('active'));
    element.classList.add('active');
    packContainerCost = price;
    packContainerName = name;
    packMaxCapacity = newMaxCap; 
    packMaxOverflow = newMaxOver; 
    updatePackTotal();
    saveToLocalStorage();
}

function deleteItemCompletely(index) {
    currentPackItems.splice(index, 1);
    renderPackTray();
    updatePackTotal();
    saveToLocalStorage();
    if (currentPackItems.length === 0) closePackBuilder();
}

function updatePackTotal() {
    const stillNeedsPack = currentPackItems.some(item => item.needsPack === true);
    if (!stillNeedsPack) {
        requiresPackFlag = false;
        packSizeSelector.classList.add('hidden');
        packContainerCost = 0;
        packMaxCapacity = Infinity;
        packMaxOverflow = Infinity;
    } else {
        requiresPackFlag = true;
        packSizeSelector.classList.remove('hidden');
    }
    const itemsSubtotal = currentPackItems.reduce((sum, item) => sum + (item.price * item.qty), 0);
    const multiplier = parseInt(document.getElementById('global-pack-multiplier').value) || 1;
    const finalTotal = (itemsSubtotal + (requiresPackFlag ? packContainerCost : 0)) * multiplier;
    totalPriceEl.innerText = `₦${finalTotal.toLocaleString()}`;
}

function closePackBuilder() {
    if (editingPackOriginal) {
        globalCartPacks.push(editingPackOriginal);
        globalCartPacks.sort((a, b) => a.displayId - b.displayId); 
        editingPackOriginal = null;
    }
    panel.classList.add('hidden');
    currentPackItems = [];
    requiresPackFlag = false;
    packContainerCost = 0;
    packMaxCapacity = Infinity;
    packMaxOverflow = Infinity;
    document.getElementById('global-pack-multiplier').value = 1; 
    packSizeSelector.classList.add('hidden');
    renderPackTray();
    renderCart();
    saveToLocalStorage();
}

// --- CORE SAVE TO BAG LOGIC (FIXED LOGIC + ORIGINAL UI) ---
async function savePackToBag() {
    if (currentPackItems.length === 0) return;

    // WORKING LOGIC: Main dish check
    const hasMainItem = currentPackItems.some(item => item.notOrderedAlone === false);
    if (!hasMainItem) {
        showToast("Please add a main dish first!");
        return;
    }

    // WORKING LOGIC: Use the bridge URL
    const validateUrl = document.getElementById('validate-url').value;
    const packData = {
        items: currentPackItems,
        pack_size_id: selectedPackConfigId
    };

    try {
        const response = await fetch(validateUrl, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(packData)
        });

        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const result = await response.json();
            if (result.valid) {
                commitPackToBag();
            } else {
                showToast(result.reason); // WORKING LOGIC: Direct reason
            }
        } else {
            showToast("Server Error: Invalid Response");
        }
    } catch (error) {
        console.error("Validation Error:", error);
        showToast("Connection error. Could not verify order.");
    }
}

function commitPackToBag() {
    const newPackMultiplier = parseInt(document.getElementById('global-pack-multiplier').value) || 1;
    const itemsSubtotal = currentPackItems.reduce((sum, item) => sum + (item.price * item.qty), 0);
    const finalTotal = (itemsSubtotal + (requiresPackFlag ? packContainerCost : 0)) * newPackMultiplier;

    globalCartPacks.push({
        id: editingPackOriginal ? editingPackOriginal.id : uniquePackIdCounter++, 
        displayId: editingPackOriginal ? editingPackOriginal.displayId : packCounter++,    
        multiplier: newPackMultiplier,
        items: JSON.parse(JSON.stringify(currentPackItems)), 
        requiresPackFlag,
        selectedPackConfigId,
        packContainerCost,
        packContainerName,
        finalTotal: finalTotal,
        maxCapacity: packMaxCapacity,
        maxOverflow: packMaxOverflow
    });

    editingPackOriginal = null; 
    closePackBuilder(); 
    saveToLocalStorage();
}

// --- ORIGINAL STYLING: Detailed Cart View ---
function renderCart() {
    if (globalCartPacks.length === 0) {
        cartContainer.innerHTML = `
            <div class="empty-cart-state">
                <div class="empty-icon"><i class="bi bi-bag-x"></i></div>
                <p>Your bag is empty.<br>Add some items to get started!</p>
            </div>`;
        document.getElementById('checkout-btn').classList.add('disabled');
        updateCartTotals();
        return;
    }

    cartContainer.innerHTML = ''; 
    globalCartPacks.forEach(pack => {
        let itemsListHtml = pack.items.map(i => `<li><b>${i.qty}x</b> ${i.name}</li>`).join('');

        cartContainer.innerHTML += `
            <div class="cart-pack-item fade-in" id="cart-pack-${pack.id}">
                ${pack.multiplier > 1 ? `<div class="pack-qty-badge">${pack.multiplier}</div>` : ''}
                <div class="cart-pack-header">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div class="pack-icon"><i class="bi bi-box-seam"></i></div>
                        <div>
                            <div class="pack-title">Pack ${pack.displayId} ${pack.multiplier > 1 ? `<span class="multiplier-tag">x${pack.multiplier}</span>` : ''}</div>
                            <div class="pack-subtitle">${pack.requiresPackFlag ? pack.packContainerName : 'No Pack'}</div>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div class="pack-price">₦${pack.finalTotal.toLocaleString()}</div>
                        <div class="pack-actions-mini">
                            <button onclick="editPack(${pack.id})" title="Edit Pack"><i class="bi bi-pencil-square"></i></button>
                            <button onclick="removePack(${pack.id})" title="Remove Pack" class="btn-trash"><i class="bi bi-trash"></i></button>
                        </div>
                    </div>
                </div>
                <ul class="cart-pack-contents">
                    ${itemsListHtml}
                </ul>
            </div>`;
    });

    document.getElementById('checkout-btn').classList.remove('disabled');
    updateCartTotals();
}

function removePack(packId) {
    if(!confirm("Remove this pack from your bag?")) return;
    globalCartPacks = globalCartPacks.filter(p => p.id !== packId);
    renderCart();
    saveToLocalStorage();
}

function editPack(packId) {
    const packIndex = globalCartPacks.findIndex(p => p.id === packId);
    if (packIndex === -1) return;

    editingPackOriginal = JSON.parse(JSON.stringify(globalCartPacks[packIndex]));
    globalCartPacks.splice(packIndex, 1);

    const p = editingPackOriginal;
    currentPackItems = p.items;
    requiresPackFlag = p.requiresPackFlag;
    selectedPackConfigId = p.selectedPackConfigId;
    packContainerCost = p.packContainerCost;
    packContainerName = p.packContainerName;
    packMaxCapacity = p.maxCapacity || Infinity;
    packMaxOverflow = p.maxOverflow || Infinity;
    
    document.getElementById('global-pack-multiplier').value = p.multiplier || 1;
    panel.classList.remove('hidden');
    packNameEl.innerText = `Pack ${p.displayId}`;

    if (requiresPackFlag) {
        packSizeSelector.classList.remove('hidden');
        document.querySelectorAll('.size-pill').forEach(el => {
            el.classList.remove('active');
            if (el.querySelector('.pack-name') && el.querySelector('.pack-name').innerText === packContainerName) {
                el.classList.add('active');
            }
        });
    }

    renderPackTray();
    updatePackTotal();
    renderCart(); 
    saveToLocalStorage();
}

// --- ORIGINAL STYLING: Complex delivery calculations ---
function updateCartTotals() {
    let subtotal = 0;
    let totalPhysicalPacks = 0; 
    globalCartPacks.forEach(p => {
        subtotal += p.finalTotal;
        totalPhysicalPacks += (p.multiplier || 1); 
    });
    
    let deliveryFee = 0;
    let calcText = "";
    if (totalPhysicalPacks === 1) {
        deliveryFee = 250;
        calcText = "1 x ₦250";
    } else if (totalPhysicalPacks === 2) {
        deliveryFee = totalPhysicalPacks * 200;
        calcText = "2 x ₦200";
    } else if (totalPhysicalPacks >= 3) {
        deliveryFee = totalPhysicalPacks * 100;
        calcText = `${totalPhysicalPacks} x ₦100`;
    }

    const finalTotal = subtotal + deliveryFee;
    document.getElementById('cart-subtotal').innerText = `₦${subtotal.toLocaleString()}`;
    document.getElementById('cart-delivery-calc').innerText = totalPhysicalPacks > 0 ? `(${calcText})` : '';
    document.getElementById('cart-delivery-price').innerText = `₦${deliveryFee.toLocaleString()}`;
    document.getElementById('cart-total').innerText = `₦${finalTotal.toLocaleString()}`;
    document.querySelector('.item-count').innerText = `${totalPhysicalPacks} pack${totalPhysicalPacks !== 1 ? 's' : ''}`;
}