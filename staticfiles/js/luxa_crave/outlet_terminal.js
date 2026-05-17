// IMPORTANT NOTE!
// SPECIAL RESTRICTIONS IS A DICTIONARY CONTAINER THAT HANDLES THE DIFFERENT TYPES OF STRANGE ITEMS


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
let packContainerImage = "placeholder";
let requiresPackFlag = false;
let editingPackOriginal = null; 
let packMaxCapacity = Infinity; 
let packMaxOverflow = Infinity; 
let globalCartPacks = [];
const terminalMain = document.querySelector('.terminal-main'); // The scrolling container

// --- GLOBAL SAFETY LIMITS ---
const GLOBAL_MAX_ITEM_QTY = 30;    
const MAX_MULTIPLIER_PER_PACK = 10; 
const MAX_TOTAL_PACKS_IN_BAG = 10;
const LOOSE_ITEM_PACK_LIMIT = 10;  

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

// --- DYNAMIC SCROLL CLEARANCE HELPER ---
function toggleBuilderPadding(isOpen) {
    const terminalMain = document.querySelector('.terminal-main');
    if (!terminalMain) return;
    
    const isMobile = window.innerWidth <= 1024;
    
    if (isOpen) {
        // Just set the padding so the bottom items aren't hidden behind the builder
        terminalMain.style.paddingBottom = isMobile ? '280px' : '350px'; 
    } else {
        // Reset the padding when the builder closes
        terminalMain.style.paddingBottom = isMobile ? '120px' : '50px'; 
    }
}

// --- 1. SINGLE SECTION NAVIGATION LOGIC ---
const sectionsList = document.querySelectorAll('.product-section');
const navPillsList = document.querySelectorAll('.nav-pill');
const btnPrev = document.getElementById('btn-prev-section');
const btnNext = document.getElementById('btn-next-section');
let currentSectionIndex = 0;

function showSection(index) {
    if (index < 0 || index >= sectionsList.length) return;
    
    // 1. Hide all sections and remove active from pills
    sectionsList.forEach(sec => sec.classList.remove('active'));
    navPillsList.forEach(pill => pill.classList.remove('active'));
    
    // 2. Show target section and highlight pill
    sectionsList[index].classList.add('active');
    navPillsList[index].classList.add('active');
    
    // 3. Scroll to the top of the internal container so the new page starts fresh
    if (terminalMain) terminalMain.scrollTo({ top: 0, behavior: 'smooth' });
    
    // 4. Ensure nav pill is visible on smaller screens
    navPillsList[index].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });

    // 5. Update Arrow Buttons
    if (btnPrev && btnNext) {
        btnPrev.disabled = index === 0;
        btnNext.disabled = index === sectionsList.length - 1;
    }
    
    currentSectionIndex = index;
}

// Initialize the arrows on page load
if (sectionsList.length > 0) {
    showSection(0);
}

// Attach click listeners to the top navigation pills
navPillsList.forEach((anchor, index) => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        showSection(index);
    });
});

// Make floating arrow navigation globally accessible
window.navigateSection = function(direction) {
    showSection(currentSectionIndex + direction);
};

// --- DRAG AND DROP & HOLD LOGIC (With Mobile Polyfill) ---
document.querySelectorAll('.product-card').forEach(card => {
    let pressTimer;
    let touchClone = null;
    let isTouchDragging = false;
    let touchStartX = 0;
    let touchStartY = 0;

    const startHold = (e) => {
        pressTimer = setTimeout(() => {
            panel.classList.remove('hidden');
            dropZone.classList.add('active');
            toggleBuilderPadding(true); 

            // If on mobile (touch event), start our custom drag polyfill
            if (e && e.type === 'touchstart') {
                isTouchDragging = true;
                
                // Create a floating visual clone of the card
                touchClone = card.cloneNode(true);
                touchClone.classList.add('drag-clone');
                touchClone.style.position = 'fixed';
                touchClone.style.zIndex = '9999';
                touchClone.style.opacity = '0.9'; 
                touchClone.style.pointerEvents = 'none'; // Lets elementFromPoint look *through* the clone
                touchClone.style.width = card.offsetWidth + 'px';
                touchClone.style.left = (touchStartX - card.offsetWidth / 2) + 'px';
                touchClone.style.top = (touchStartY - card.offsetHeight / 2) + 'px';
                touchClone.style.boxShadow = '0 15px 35px rgba(0,0,0,0.2)'; // Makes it "pop" out
                touchClone.style.transform = 'scale(1.05)';
                document.body.appendChild(touchClone);
                
                // Optional: tiny haptic feedback if the phone supports it
                if (navigator.vibrate) navigator.vibrate(50);
            }
        }, 350); // 350ms hold to activate (feels snappy!)
    };

    const cancelHold = () => {
        clearTimeout(pressTimer);
    };

    // --- NATIVE DESKTOP LISTENERS ---
    card.addEventListener('mousedown', (e) => startHold(e));
    
    card.addEventListener('click', function(e) {
        if (card.tagName.toLowerCase() === 'a' && card.getAttribute('href') === '#') e.preventDefault();
    });

    card.addEventListener('dragstart', (e) => {
        cancelHold();
        panel.classList.remove('hidden');
        dropZone.classList.add('active');
        card.classList.add('dragging');
        toggleBuilderPadding(true);
        
        const btn = card.querySelector('.btn-add');
        const itemData = {
            id: card.getAttribute('data-item-id') || btn.getAttribute('data-item-id'),
            name: card.getAttribute('data-name') || btn.getAttribute('data-name'),
            price: parseFloat(String(card.getAttribute('data-price') || btn.getAttribute('data-price')).replace(/,/g, '')),
            image: card.getAttribute('data-image') || btn.getAttribute('data-image'),
            needsPack: (card.getAttribute('data-requires-pack') || btn.getAttribute('data-requires-pack')) === 'true',
            fillingValue: parseFloat(card.getAttribute('data-filling-value')) || 0, 
            sectionId: card.getAttribute('data-section-id') || btn.getAttribute('data-section-id'),
            sectionName: card.getAttribute('data-section-name') || btn.getAttribute('data-section-name'),
            notOrderedAlone: (card.getAttribute('data-not-ordered-alone') || btn.getAttribute('data-not-ordered-alone')) === 'true',
            is_a_soup: (card.getAttribute('data-is-soup') || btn.getAttribute('data-is-soup')) === 'true',
            need_soup: (card.getAttribute('data-need-soup') || btn.getAttribute('data-need-soup')) === 'true',
            is_strange: card.getAttribute('data-is-strange') || btn.getAttribute('data-is-strange'),
            strange_value: card.getAttribute('data-strange-value') || btn.getAttribute('data-strange-value'),
            has_charge: (card.getAttribute('data-has-charge') || btn.getAttribute('data-has-charge')) === 'true'
        };
        e.dataTransfer.setData('text/plain', JSON.stringify(itemData));
    });

    card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        dropZone.classList.remove('active', 'drag-over');
        if (currentPackItems.length === 0) panel.classList.add('hidden');
    });

    // --- CUSTOM MOBILE TOUCH LISTENERS ---
    card.addEventListener('touchstart', (e) => {
        const touch = e.touches[0];
        touchStartX = touch.clientX;
        touchStartY = touch.clientY;
        startHold(e);
    }, {passive: true});
    
    card.addEventListener('touchmove', function(e) {
        if (isTouchDragging && touchClone) {
            e.preventDefault(); // ONLY locks the screen from scrolling if actively dragging
            const touch = e.touches[0];
            touchClone.style.left = (touch.clientX - touchClone.offsetWidth / 2) + 'px';
            touchClone.style.top = (touch.clientY - touchClone.offsetHeight / 2) + 'px';
            
            // Highlight the dropzone if hovering over it
            const elUnder = document.elementFromPoint(touch.clientX, touch.clientY);
            if (elUnder && (elUnder.id === 'pack-drop-zone' || elUnder.closest('#pack-drop-zone'))) {
                dropZone.classList.add('drag-over');
            } else {
                dropZone.classList.remove('drag-over');
            }
        } else {
            // THE FIX: Slop Threshold! Tiny finger wobbles (< 15px) won't cancel the hold!
            const touch = e.touches[0];
            const moveX = Math.abs(touch.clientX - touchStartX);
            const moveY = Math.abs(touch.clientY - touchStartY);
            if (moveX > 15 || moveY > 15) {
                cancelHold(); 
            }
        }
    }, {passive: false});

    card.addEventListener('touchend', function(e) {
        cancelHold();
        
        // If they were actively touch-dragging
        if (isTouchDragging && touchClone) {
            const touch = e.changedTouches[0];
            const elUnder = document.elementFromPoint(touch.clientX, touch.clientY);
            
            // Drop successful!
            if (elUnder && (elUnder.id === 'pack-drop-zone' || elUnder.closest('#pack-drop-zone'))) {
                const btn = card.querySelector('.btn-add');
                const data = {
                    id: card.getAttribute('data-item-id') || btn.getAttribute('data-item-id'),
                    name: card.getAttribute('data-name') || btn.getAttribute('data-name'),
                    price: parseFloat(String(card.getAttribute('data-price') || btn.getAttribute('data-price')).replace(/,/g, '')),
                    image: card.getAttribute('data-image') || btn.getAttribute('data-image'),
                    needsPack: (card.getAttribute('data-requires-pack') || btn.getAttribute('data-requires-pack')) === 'true',
                    fillingValue: parseFloat(card.getAttribute('data-filling-value')) || 0, 
                    sectionId: card.getAttribute('data-section-id') || btn.getAttribute('data-section-id'),
                    sectionName: card.getAttribute('data-section-name') || btn.getAttribute('data-section-name'),
                    notOrderedAlone: (card.getAttribute('data-not-ordered-alone') || btn.getAttribute('data-not-ordered-alone')) === 'true',
                    is_a_soup: (card.getAttribute('data-is-soup') || btn.getAttribute('data-is-soup')) === 'true',
                    need_soup: (card.getAttribute('data-need-soup') || btn.getAttribute('data-need-soup')) === 'true',
                    is_strange: card.getAttribute('data-is-strange') || btn.getAttribute('data-is-strange'),
                    strange_value: card.getAttribute('data-strange-value') || btn.getAttribute('data-strange-value'),
                    has_charge: (card.getAttribute('data-has-charge') || btn.getAttribute('data-has-charge')) === 'true'
                };
                processItemAddition(data);
            }
            
            // Clean up the clone
            touchClone.remove();
            touchClone = null;
            isTouchDragging = false;
            dropZone.classList.remove('active', 'drag-over');
            
            if (currentPackItems.length === 0) panel.classList.add('hidden');
        }
    });

    card.addEventListener('touchcancel', function() {
        cancelHold();
        if (touchClone) {
            touchClone.remove();
            touchClone = null;
        }
        isTouchDragging = false;
        dropZone.classList.remove('active', 'drag-over');
    });
    
    card.addEventListener('mouseup', cancelHold);
    card.addEventListener('mouseleave', cancelHold);
});

panel.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
panel.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
panel.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('active', 'drag-over');
    try {
        const data = JSON.parse(e.dataTransfer.getData('text/plain'));

        // Limit soup to one per pack. Disallows extra soup addition by dragging
        if (data.is_a_soup && currentPackItems.some(i => i.is_a_soup)) {
            showToast("Only one soup allowed per pack.");
            return;
        }

        // Function for disallowing items that don't require pack after limit is reached goes here

        processItemAddition(data);
    } catch (err) { console.error("Drop parsing failed:", err); }
});

function changePackMultiplier(delta) {
    const input = document.getElementById('global-pack-multiplier');
    let val = parseInt(input.value) || 1;
    
    // Calculate how many packs are already in the bag
    const currentTotalInBag = globalCartPacks.reduce((sum, p) => sum + (p.multiplier || 1), 0);

   if (delta > 0) {
        // Check 1: Individual Pack Multiplier Limit (10)
        if (val >= MAX_MULTIPLIER_PER_PACK) {
            showToast(`You can only order a maximum of ${MAX_MULTIPLIER_PER_PACK} of the same pack.`);
            return;
        }
        
        // Check 2: Global Bag Limit Loophole (20)
        // We check if (Packs already in bag) + (Proposed new quantity) > 20
        if (currentTotalInBag + (val + 1) > MAX_TOTAL_PACKS_IN_BAG) {
            showToast(`Courier bag limit reached! You can only add ${MAX_TOTAL_PACKS_IN_BAG - currentTotalInBag} more packs.`);
            return;
        }
    }

    val += delta;
    if (val < 1) val = 1;
    input.value = val;
    updatePackTotal();
    saveToLocalStorage();
}

function changeItemQty(index, delta) {
    const item = currentPackItems[index];
    if (!item) return;

    // 1. Safety Block: Soups cannot have their quantity changed
    if (item.is_a_soup) return;

    // 2. INCREMENT CHECKS (Only run if user clicks '+')
    if (delta > 0) {

        // --- NEW: BREAD EGG LIMITER ---
        // if (item.strange_value === 'bread_egg' && item.qty >= 1) {
        //     showToast("You can only add 1 type of this item per bundle.");
        //     return;
        // }

        // Individual Item Limit
        if (item.qty >= GLOBAL_MAX_ITEM_QTY) {
            showToast(`Maximum ${GLOBAL_MAX_ITEM_QTY} units of ${item.name} allowed per pack.`);
            return;
        }

        // --- LOOSE PACK LIMIT (The 10-item rule) ---
        const isLooseOnlyPack = currentPackItems.every(i => String(i.needsPack) === 'false' || i.needsPack === false);
        if (isLooseOnlyPack) {
            const currentTotal = currentPackItems.reduce((sum, i) => sum + i.qty, 0);
            if (currentTotal + 1 > LOOSE_ITEM_PACK_LIMIT) {
                showToast(`Limit reached: ${LOOSE_ITEM_PACK_LIMIT} units max for loose items.`);
                return;
            }
        }

        // --- PHYSICAL CAPACITY CHECKS ---
        const currentBoxFill = currentPackItems.reduce((sum, i) => i.needsPack ? sum + (i.fillingValue * i.qty) : sum, 0);
        const currentTotalPayload = currentPackItems.reduce((sum, i) => sum + (i.fillingValue * i.qty), 0);

        if (item.needsPack && (currentBoxFill + item.fillingValue) > packMaxCapacity) {
            showToast("The lid won't close because pack is full. Try a larger pack.");
            return;
        }

        if ((currentTotalPayload + item.fillingValue) > packMaxOverflow) {
            showToast("Overflow limit reached!");
            return;
        }
    }

    // 3. EXECUTION (Handles both + and -)
    const newQty = item.qty + delta;

    if (newQty >= 1) {
        item.qty = newQty;
    } else {
        // Remove item if qty hits 0
        currentPackItems.splice(index, 1);
    }

    // 4. UPDATE UI & STORAGE
    renderPackTray();
    updatePackTotal();
    saveToLocalStorage();
}

function processItemAddition(data) {
    if (!data.id) return;

    // Check if tray will be "loose-only"
    const isLooseItem = String(data.needsPack) === 'false' || data.needsPack === false;
    const currentTrayIsLooseOnly = currentPackItems.length === 0 || 
                                   currentPackItems.every(i => String(i.needsPack) === 'false' || i.needsPack === false);

    if (currentTrayIsLooseOnly && isLooseItem) {
        const totalQty = currentPackItems.reduce((sum, i) => sum + i.qty, 0);
        if (totalQty + 1 > LOOSE_ITEM_PACK_LIMIT) {
            showToast(`Loose-item packs are limited to ${LOOSE_ITEM_PACK_LIMIT} units.`);
            return;
        }
    
    }


    // --- SINGLE SOUP LIMITER ---
    if (data.is_a_soup) {
        const existingSoup = currentPackItems.find(i => i.is_a_soup === true);
        if (existingSoup) {
            showToast("You can only add one type of soup to a pack.");
            return;
        }
    }

    // --- NEW: BREAD EGG LIMITER ---
    // if (data.strange_value === 'bread_egg') {
    //     // Count how many bread_eggs are already in the tray
    //     const breadEggQty = currentPackItems.reduce((sum, i) => i.strange_value === 'bread_egg' ? sum + i.qty : sum, 0);
    //     if (breadEggQty >= 1) {
    //         showToast("You can only add 1 of this type of item per bundle.");
    //         return;
    //     }
    // }

    // Function for limiting products that don't need pack goes here

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
            id: data.id, 
            name: data.name, 
            price: data.price, 
            image: data.image, 
            qty: 1,
            needsPack: (String(data.needsPack) === 'true' || data.needsPack === true),
            fillingValue: fillingValue, 
            sectionId: data.sectionId,
            sectionName: data.sectionName || "General", 
            notOrderedAlone: data.notOrderedAlone,
            is_a_soup: data.is_a_soup,
            need_soup: data.need_soup,
            is_strange: data.is_strange,
            strange_value: data.strange_value,
            has_charge: data.has_charge 
        });
    }

    panel.classList.remove('hidden');
    toggleBuilderPadding(true);
    packNameEl.innerText = `Bundle ${packCounter}`;
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
        sectionName: card.getAttribute('data-section-name') || btn.getAttribute('data-section-name'),
        sectionId: card.getAttribute('data-section-id') || btn.getAttribute('data-section-id'),
        notOrderedAlone: (card.getAttribute('data-not-ordered-alone') || btn.getAttribute('data-not-ordered-alone')) === 'true',
        is_a_soup: (card.getAttribute('data-is-soup') || btn.getAttribute('data-is-soup')) === 'true',
        need_soup: (card.getAttribute('data-need-soup') || btn.getAttribute('data-need-soup')) === 'true',
        is_strange: card.getAttribute('data-is-strange') || btn.getAttribute('data-is-strange'),
        strange_value: card.getAttribute('data-strange-value') || btn.getAttribute('data-strange-value'),
        has_charge: (card.getAttribute('data-has-charge') || btn.getAttribute('data-has-charge')) === 'true'
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

// Function to render pack tray
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

        // NEW: Conditional stepper logic
        const qtyControls = item.is_a_soup 
            ? `<span style="font-size: 15px; font-weight:600; color:var(--crave-primary); padding: 0 10px;">Soup</span>`
            : `<div class="item-qty-stepper">
                <button onclick="changeItemQty(${index}, -1)">-</button>
                <span>${item.qty}</span>
                <button onclick="changeItemQty(${index}, 1)">+</button>
               </div>`;

        tray.innerHTML += `
            <div class="item-pill fade-in">
                <div style="position: relative;">${imgHtml}</div>
                <div class="item-pill-info">
                    <span class="pill-name">${item.name}</span>
                    ${qtyControls}
                </div>
                <button class="btn-remove-pill" onclick="deleteItemCompletely(${index})" title="Remove All">
                    <i class="bi bi-trash"></i>
                </button>
            </div>`;
    });
}

// Remove items from pack (Globally accessible)
function removeItemFromPack(index) {
    if (currentPackItems[index].qty > 1) {
        currentPackItems[index].qty -= 1;
    } else {
        currentPackItems.splice(index, 1);
    }
    renderPackTray();
    updatePackTotal();
    
    if (currentPackItems.length === 0) {
        closePackBuilder();
    }
}

function selectPackSize(element, price, name, maxCap, maxOver, configId, imageUrl) {
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
    packContainerImage = imageUrl || 'placeholder';
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

// Update pack total price display
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

    // --- NEW: Add 50 if any item in the tray has the charge flag ---
    const appliesPackCharge = currentPackItems.some(item => item.has_charge === true);
    const extraFee = appliesPackCharge ? 50 : 0;

    const finalTotal = (itemsSubtotal + (requiresPackFlag ? packContainerCost : 0) + extraFee) * multiplier;
    totalPriceEl.innerText = `₦${finalTotal.toLocaleString()}`;
}

// Close the pack builder and reset all related states
function closePackBuilder() {
    if (editingPackOriginal) {
        globalCartPacks.push(editingPackOriginal);
        globalCartPacks.sort((a, b) => a.displayId - b.displayId); 
        editingPackOriginal = null;
    }
    panel.classList.add('hidden');
    toggleBuilderPadding(false); // closes the padding when panel closes
    dropZone.classList.remove('active');
    
    currentPackItems = [];
    requiresPackFlag = false;
    packContainerCost = 0;
    packContainerImage = 'placeholder';
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

    const validateUrl = document.getElementById('validate-url').value;
    const newPackMultiplier = parseInt(document.getElementById('global-pack-multiplier').value) || 1;

    let result;
    try {
        // --- STAGE 1: TALK TO SERVER ---
        const response = await fetch(validateUrl, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                items: currentPackItems,
                pack_size_id: selectedPackConfigId,
                multiplier: newPackMultiplier,
                current_cart: globalCartPacks
            })
        });
        result = await response.json();
    } catch (networkError) {
        console.error("SERVER FETCH FAILED:", networkError);
        showToast("Connection error. Server unreachable.");
        return;
    }

    // --- STAGE 2: HANDLE SERVER VALIDATION ---
    if (!result.valid) {
        showToast(result.reason);
        return;
    }

   // --- STAGE 3: LOCAL SAVE ---
    try {
        commitPackToBag(result.influence_value);
        
        // This is the Safe Call. It checks if the function exists first.
        if (typeof renderCartSidebar === 'function') {
            renderCartSidebar();
        } else if (typeof renderCart === 'function') {
            renderCart();
        }
        
        // This ensures the prices and bar update even if the sidebar function had a typo
        updateCartTotals(); 
        
    } catch (localError) {
        console.error("STOPPING THE CRASH:", localError);
        // We don't show a toast here anymore because we handled it!
    }
}

// Render the cart items in the sidebar
function commitPackToBag(influenceValue) {

    // --- FIX 1: UPDATE LOGIC ---
    // If we are editing, we need to REPLACE the old pack, not just push a new one.
    // Otherwise the bar keeps adding the old value + the new value.
    if (editingPackOriginal) {
        const index = globalCartPacks.findIndex(p => p.id === editingPackOriginal.id);
        if (index !== -1) {
            globalCartPacks.splice(index, 1); 
        }
    }

    const newPackMultiplier = parseInt(document.getElementById('global-pack-multiplier').value) || 1;
    const itemsSubtotal = currentPackItems.reduce((sum, item) => sum + (item.price * item.qty), 0);
    // --- NEW: Add 50 if any item in the finalized pack has the charge flag ---
    const appliesPackCharge = currentPackItems.some(item => item.has_charge === true);
    const extraFee = appliesPackCharge ? 50 : 0;
    
    const finalTotal = (itemsSubtotal + (requiresPackFlag ? packContainerCost : 0) + extraFee) * newPackMultiplier;

    globalCartPacks.push({
        id: editingPackOriginal ? editingPackOriginal.id : uniquePackIdCounter++, 
        displayId: editingPackOriginal ? editingPackOriginal.displayId : packCounter++,    
        multiplier: newPackMultiplier,
        items: JSON.parse(JSON.stringify(currentPackItems)), 

        influence_value: influenceValue !== undefined && influenceValue !== null ? parseFloat(influenceValue) : newPackMultiplier,
        requiresPackFlag,
        selectedPackConfigId,
        packContainerCost,
        packContainerName,
        packContainerImage,
        finalTotal: finalTotal,
        maxCapacity: packMaxCapacity,
        maxOverflow: packMaxOverflow
    });

    editingPackOriginal = null; 
    closePackBuilder(); 
    saveToLocalStorage();
    renderPackBuilder();
    
    panel.classList.add('hidden');
    toggleBuilderPadding(false);

    // These functions rebuild the cart DOM
    renderCartSidebar(); 
    updateCartTotals();
    
    // --- BULLETPROOF MOBILE CART AUTO-OPEN ---
    // Wait for the browser to finish rendering the new DOM before animating
    requestAnimationFrame(() => {
        setTimeout(() => {
            if (window.innerWidth <= 1024) {
                const cart = document.querySelector('.terminal-cart');
                const overlay = document.getElementById('mobile-cart-overlay');
                
                if (cart) cart.classList.add('active');
                if (overlay) overlay.classList.add('active');
            }
        }, 50); // 50ms delay perfectly bypasses synchronous DOM wipes
    });
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

    // NEW: Inject the sticky action bar before looping through the packs
    cartContainer.innerHTML = `
        <div class="cart-actions-bar">
            <button class="btn-clear-cart" onclick="clearCart()">
                <i class="bi bi-trash3-fill"></i> Clear Bag
            </button>
        </div>
    `;
 
    globalCartPacks.forEach(pack => {
        let itemsListHtml = pack.items.map(i => `<li><b>${i.qty}x</b> ${i.name}</li>`).join('');

        // NEW: Safely determine what to put in the icon box
        let iconDisplay = (pack.requiresPackFlag && pack.packContainerImage && pack.packContainerImage !== 'placeholder') 
            ? `<img src="${pack.packContainerImage}" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;" alt="Pack">` 
            : `<i class="bi bi-box-seam"></i>`;

        cartContainer.innerHTML += `
            <div class="cart-pack-item fade-in" id="cart-pack-${pack.id}">
                ${pack.multiplier > 1 ? `<div class="pack-qty-badge">${pack.multiplier}</div>` : ''}
                <div class="cart-pack-header">
                    <div style="display:flex; align-items:center; gap:10px;">
                        
                        <div class="pack-icon">${iconDisplay}</div>
                        
                        <div>
                            <div class="pack-title">Bundle ${pack.displayId} ${pack.multiplier > 1 ? `<span class="multiplier-tag">x${pack.multiplier}</span>` : ''}</div>
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

// --- CLEAR CART LOGIC ---
function clearCart() {
    if (!confirm("Are you sure you want to completely empty your Crave Bag?")) return;
    
    // Clear the global array
    globalCartPacks = [];
    
    // If they happen to be editing a pack while they click clear, close the builder
    if (!panel.classList.contains('hidden')) {
        closePackBuilder();
    }
    
    // Update UI and Storage
    renderCart();
    saveToLocalStorage();
}

// Remove entire pack from cart (Globally accessible)
function removePack(packId) {
    if(!confirm("Remove this pack from your bag?")) return;
    globalCartPacks = globalCartPacks.filter(p => p.id !== packId);
    renderCart();
    saveToLocalStorage();
}

// Edit pack - loads the pack back into the builder for editing (Globally accessible)
function editPack(packId) {
    const packToEdit = globalCartPacks.find(p => p.id === packId);
    if (!packToEdit) return;
    toggleBuilderPadding(true);
    
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
    packContainerImage = p.packContainerImage || 'placeholder';
    packMaxCapacity = p.maxCapacity || Infinity;
    packMaxOverflow = p.maxOverflow || Infinity;
    
    document.getElementById('global-pack-multiplier').value = p.multiplier || 1;
    panel.classList.remove('hidden');
    packNameEl.innerText = `Bundle ${p.displayId}`;

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





const SPECIAL_RESTRICTIONS = {
    'large_bread': { extra_fee: 250 },
    'medium_bread':{ extra_fee: 200 },
    'small_bread': { extra_fee: 125 },
    'bread_egg': { extra_fee: 0 },
};

function updateCartTotals() {
    let subtotal = 0;
    let totalSurchargeFee = 0;
    let standardPackCount = 0; 
    let totalInfluence = 0; 
    let hasBreadEggInCart = false; // --- NEW: Track if bread_egg exists ---

    globalCartPacks.forEach(p => {
        subtotal += p.finalTotal;
        
        // --- COURION WEIGHT CALCULATION ---
        let weight = 0;
        if (p.influence_value !== undefined && p.influence_value !== null) {
            weight = parseFloat(p.influence_value);
        } else {
            weight = parseFloat(p.multiplier || 1);
        }
        totalInfluence += weight;

        let hasNormalItem = false;
        let packSpecificSurcharge = 0; 
        let breadEggQty = 0; // --- NEW: Track bread eggs in this specific pack ---
        const packMultiplier = (p.multiplier || 1); 

        p.items.forEach(item => {
            const isStrange = String(item.is_strange) === 'true';
            if (!isStrange) {
                hasNormalItem = true; 
            }

            // --- NEW: Tally Bread Eggs ---
            if (item.strange_value === 'bread_egg') {
                breadEggQty += parseInt(item.qty) || 1;
                hasBreadEggInCart = true;
            }

            const restriction = SPECIAL_RESTRICTIONS[item.strange_value];
            if (restriction) {
                const fee = restriction.extra_fee;
                packSpecificSurcharge += (item.qty * fee); 
                totalSurchargeFee += (item.qty * packMultiplier) * fee; 
            }
        });

        // --- THE FIX: DYNAMIC PACK COUNTING ---
        if (hasNormalItem || packSpecificSurcharge < 1) {
            const baseCount = breadEggQty > 0 ? breadEggQty : 1;
            standardPackCount += (baseCount * packMultiplier);
        }
    });
    
    // Tiered Logic for Standard Delivery
    let standardDeliveryPrice = 0;
    let calcText = "";
    
    if (standardPackCount > 0) {
        let count = Math.min(standardPackCount, 10);
        let ratePerPack = (count === 10) ? 300 : (400 - ((count - 1) * 10));
        // let ratePerPack = 200; // FLAT RATE FOR ALL PACKS IN THE STANDARD POOL - PROMO OFFER

        
        standardDeliveryPrice = count * ratePerPack;
        calcText = `${count} x ₦${ratePerPack}`;
    }
    
    // --- NEW: RUSH HOUR WAIT FEE LOGIC ---
    let waitFee = 0;
    
    // Check if we are at BackYard Caf
    if (window.CURRENT_OUTLET_NAME && window.CURRENT_OUTLET_NAME.toLowerCase().includes('backyard')) {
        const now = new Date();
        const hour = now.getHours();
        const mins = now.getMinutes();
        
        // Check if time is between 17:30 (5:00 PM) and 18:59 (6:59 PM)
        if ((hour === 17) || (hour === 18)) {
            waitFee = 300;
        }
    }
    
    // Add waitFee to your final total
    const finalTotal = subtotal + standardDeliveryPrice + totalSurchargeFee + waitFee;

    // --- UI RENDERING FOR THE WAIT FEE & CUSTOM TOOLTIP ---
    const elWaitFeeRow = document.getElementById('wait-fee-row');
    const elWaitFeePrice = document.getElementById('wait-fee-price');
    
    if (elWaitFeeRow && elWaitFeePrice) {
        if (waitFee > 0 && standardPackCount > 0) {
            elWaitFeeRow.style.display = 'flex';
            // Inject the price and the Custom Tooltip HTML
            elWaitFeePrice.innerHTML = `+₦${waitFee} 
                <div class="crave-tooltip-wrapper">
                    <i class="bi bi-info-circle-fill" style="color: #94a3b8; font-size: 0.85rem;"></i>
                    <span class="crave-tooltip-text">100% of this fee goes directly to your courier to compensate for their time waiting in the extreme rush hour queue at BackYard. Luxa takes 0%.</span>
                </div>`;
        } else {
            elWaitFeeRow.style.display = 'none';
        }
    }

    // --- SAFE UI UPDATES ---
    const elSubtotal = document.getElementById('cart-subtotal');
    if (elSubtotal) elSubtotal.innerText = `₦${subtotal.toLocaleString()}`;
    
    const elDeliveryPrice = document.getElementById('cart-delivery-price');
    if (elDeliveryPrice){
        elDeliveryPrice.innerText = `₦${standardDeliveryPrice.toLocaleString()}`;
    } 
    
    // --- NEW: INJECT CALC TEXT & INFO ICON ---
    const elDeliveryCalc = document.getElementById('cart-delivery-calc');
    if (elDeliveryCalc) {
        if (standardPackCount > 0) {
            const infoIcon = hasBreadEggInCart ? ` <i class="bi bi-info-circle-fill" style="color: #94a3b8; font-size: 0.85rem; cursor: help; margin-left: 3px;" title="Due to courier bag constraints, each special item such as bread and egg or sharwarma acts as a separate pack for delivery calculation."></i>` : '';
            elDeliveryCalc.innerHTML = `(${calcText})${infoIcon}`; // IMPORTANT: Use innerHTML to render the icon!
        } else {
            elDeliveryCalc.innerHTML = '';
        }
    }

    const elSurchargeRow = document.getElementById('surcharge-row');
    const elSurchargePrice = document.getElementById('surcharge-delivery-price');
    if (elSurchargeRow && elSurchargePrice) {
        if (totalSurchargeFee > 0) {
            elSurchargeRow.style.display = 'flex';
            elSurchargePrice.innerText = `+₦${totalSurchargeFee.toLocaleString()}`;
        } else {
            elSurchargeRow.style.display = 'none';
        }
    }

    const elTotal = document.getElementById('cart-total');
    if (elTotal) elTotal.innerText = `₦${finalTotal.toLocaleString()}`;

    if (typeof updateCartBadge === 'function') updateCartBadge();

    // --- SAFE COURION BAR ---
    const bar = document.getElementById('courion-progress');
    const statusText = document.getElementById('courion-status');
    if (bar && statusText) {
        const percent = (totalInfluence / 10) * 100;
        bar.style.width = Math.min(percent, 100) + '%';
        statusText.innerText = `${totalInfluence} / 10`;
        
        if (percent > 85) bar.style.background = '#ef4444';
        else if (percent > 60) bar.style.background = '#f59e0b';
        else bar.style.background = '#16a34a';
    }
}


// FUNCTION TO HANDLE CHECKOUT - SECURELY SAVES DATA TO SESSION THEN REDIRECTS TO CHECKOUT PAGE
document.getElementById('checkout-btn').addEventListener('click', async () => {
    if (globalCartPacks.length === 0) return;

    // --- OUTLET AVAILABILITY CHECK ---
    const isOutletOpen = document.getElementById('outlet-is-open').value === 'true';
    if (!isOutletOpen) {
        showToast("Sorry, this outlet is currently closed!");
        return; // Terminates the checkout completely
    }

    const btn = document.getElementById('checkout-btn');
    const checkoutUrl = document.getElementById('checkout-url').value;
    
    // Save the original text to restore it later if validation fails
    const originalHTML = 'Checkout <i class="bi bi-arrow-right"></i>';
    
    btn.disabled = true;
    btn.innerHTML = 'Verifying Bag... <i class="bi bi-shield-lock-fill"></i>';

    try {
        const response = await fetch(checkoutUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            // NEW: Send the forced_gender if they just filled out the modal!
            body: JSON.stringify({ 
                bag: globalCartPacks,
                forced_gender: window.terminalForcedGender || null 
            }) 
        });

        const result = await response.json();

        // 1. SUCCESS
        if (response.ok && result.status === 'success') {
            window.location.href = result.redirect; 
        } 
        
        // 2. NEW: CATCH THE MISSING GENDER STATUS
        else if (result.status === 'missing_gender') {
            openCraveModal('genderPromptModal');
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }

        // 3. AVAILABILITY FAILED
        else if (result.status === 'availability_failed') {
            const errorContainer = document.getElementById('availability-error-list');
            
            errorContainer.innerHTML = result.errors.map(err => `
                <div class="error-item-msg">
                    <span>• ${err.name}</span>
                    <span style="color: #ef4444; font-weight: normal;">${err.reason}</span>
                </div>
            `).join('');

            openCraveModal('availabilityErrorModal');
            
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }

        // 4. INTEGRITY FAILED
        else if (result.status === 'integrity_failed') {
            showToast(result.message); 
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }

        // 5. CATCH-ALL ERROR
        else {
            showToast(result.message || "Checkout failed.");
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }

    } catch (error) {
        console.error("Gatekeeper Error:", error);
        showToast("Network error. Could not verify bag.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
});

// --- NEW: HANDLE TERMINAL GENDER SUBMISSION ---
window.submitTerminalGender = function() {
    const selectedGender = document.getElementById('terminal_prompt_gender').value;
    
    if (!selectedGender) {
        alert("Please select a gender to continue.");
        return;
    }
    
    // Store it globally so the next fetch picks it up
    window.terminalForcedGender = selectedGender; 
    
    // Close the modal
    closeCraveModal('genderPromptModal');
    
    // Give the modal 300ms to visually close, then automatically click the checkout button again!
    setTimeout(() => {
        const checkoutBtn = document.getElementById('checkout-btn');
        if (checkoutBtn) checkoutBtn.click();
    }, 300);
}

// --- MODAL LOGIC ---
function openCraveModal(id) { 
    const el = document.getElementById(id);
    el.style.display = 'flex';
    setTimeout(() => el.classList.add('show'), 10);
}

function closeCraveModal(id) { 
    const el = document.getElementById(id);
    el.classList.remove('show');
    setTimeout(() => el.style.display = 'none', 300);
}

// --- SAVE PRESET LOGIC ---
function submitSavePreset(outletId) {
    const nameInput = document.getElementById('presetNameInput').value.trim();
    const btn = document.getElementById('btn-submit-preset');
    
    if (!nameInput) return alert("Please enter a name for your preset.");
    
    if (currentPackItems.length === 0) {
        closeCraveModal('createPresetModal');
        return showToast("Cannot save an empty pack!");
    }

    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
    btn.disabled = true;

    // 1. Check if the multiplier stepper exists, default to 1 if it doesn't
    const multiplierInput = document.getElementById('global-pack-multiplier');
    const currentMultiplier = multiplierInput ? parseInt(multiplierInput.value) : 1;

    // 2. Build the payload
    const payload = {
        preset_name: nameInput,
        outlet_id: outletId,
        pack_config_id: selectedPackConfigId,
        items: currentPackItems.map(i => ({ id: i.id, qty: i.qty })),
        pack_multiplier: currentMultiplier // <-- Sends the multiplier to Python
    };

    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch('/api/save-preset/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Saved!';
            btn.style.background = '#22c55e';
            
            setTimeout(() => { 
                closeCraveModal('createPresetModal'); 
                showToast("Preset Saved! Reloading...");
                setTimeout(() => window.location.reload(), 1000);
            }, 1000);
        } else {
            alert("Error saving preset: " + data.message);
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    })
    .catch(err => {
        console.error(err);
        alert("Network Error");
        btn.innerHTML = originalText;
        btn.disabled = false;
    });
}
    
// --- PRESET INJECTION LOGIC ---
async function injectPresetToCart(presetId, btnElement) {
    const originalHtml = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="bi bi-hourglass-split"></i> Loading...';
    btnElement.disabled = true;

    try {
        const response = await fetch(`/api/get-preset/${presetId}/`);
        const data = await response.json();
        
        if (data.status === 'success') {
            const pd = data.pack_data;
            
            let itemsTotal = 0;
            let needsPackFlag = false;
            
            pd.items.forEach(item => {
                itemsTotal += (item.price * item.qty);
                if (item.needsPack) needsPackFlag = true;
            });
            
            // Grab the multiplier fetched from the database
            const savedMultiplier = parseInt(pd.pack_multiplier) || 1;
            let finalTotal = (itemsTotal + (needsPackFlag ? pd.packContainerCost : 0)) * savedMultiplier;
            
            // SECURITY CATCH: Ensure influence value is NEVER undefined
            const parsedInfluenceValue = parseFloat(pd.influence_value) || 1;
            
            // Inject into global cart state
            globalCartPacks.push({
                id: uniquePackIdCounter++, 
                displayId: packCounter++,    
                multiplier: savedMultiplier, // <-- Injecting the saved multiplier
                items: pd.items, 
                requiresPackFlag: needsPackFlag,
                selectedPackConfigId: pd.selectedPackConfigId,
                packContainerCost: needsPackFlag ? pd.packContainerCost : 0,
                packContainerName: pd.packContainerName,
                packContainerImage: pd.packContainerImage, 
                finalTotal: finalTotal,
                maxCapacity: pd.maxCapacity,
                maxOverflow: pd.maxOverflow,
                influence_value: parsedInfluenceValue // <-- Accurate Courion Count
            });
            
            // Update UI Safely
            if (typeof renderCartSidebar === 'function') renderCartSidebar();
            else if (typeof renderCart === 'function') renderCart();
            
            if (typeof updateCartTotals === 'function') updateCartTotals();
            if (typeof saveToLocalStorage === 'function') saveToLocalStorage();
            
            btnElement.innerHTML = '<i class="bi bi-check2"></i> Added!';
            btnElement.style.background = '#22c55e'; 
            btnElement.style.color = 'white';
            
            setTimeout(() => {
                btnElement.innerHTML = originalHtml;
                btnElement.style.background = '';
                btnElement.style.color = '';
                btnElement.disabled = false;
            }, 2000);

        } else {
            alert("Error loading preset: " + data.message);
            btnElement.innerHTML = originalHtml;
            btnElement.disabled = false;
        }
    } catch (error) {
        console.error(error);
        alert("Network error while loading preset.");
        btnElement.innerHTML = originalHtml;
        btnElement.disabled = false;
    }
}

// --- DELETE PRESET LOGIC ---
async function deletePreset(presetId, btnElement) {
    if (!confirm("Are you sure you want to permanently delete this preset?")) return;

    const originalHtml = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="bi bi-hourglass"></i>';
    btnElement.disabled = true;

    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    await fetch(`/api/delete-preset/${presetId}/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            // Smoothly fade out the card
            const card = document.getElementById(`preset-card-${presetId}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    card.remove();
                    // If that was the last preset, reload the page to show the empty state
                    const remainingCards = document.querySelectorAll('.preset-card-modal');
                    if (remainingCards.length === 0) {
                        window.location.reload();
                    }
                }, 300);
            }
            showToast("Preset deleted successfully!");
        } else {
            alert("Error deleting preset: " + data.message);
            btnElement.innerHTML = originalHtml;
            btnElement.disabled = false;
        }
    })
    .catch(err => {
        console.error(err);
        alert("Network Error");
        btnElement.innerHTML = originalHtml;
        btnElement.disabled = false;
    });
}

let scrollPosition = 0;
const body = document.body;

// --- MOBILE CART TOGGLE & BADGE LOGIC ---
function toggleMobileCart() {
    const cart = document.querySelector('.terminal-cart');
    const overlay = document.getElementById('mobile-cart-overlay');
    if (!cart || !overlay) return;

    if (cart.classList.contains('active')) {
        cart.classList.remove('active');
        overlay.classList.remove('active');
        body.classList.remove('no-scroll-ios');
        body.style.top = '';
        window.scrollTo(0, scrollPosition);
    } else {
        cart.classList.add('active');
        overlay.classList.add('active');
        scrollPosition = window.pageYOffset;
        body.style.top = `-${scrollPosition}px`;
        body.classList.add('no-scroll-ios');
    }
}

function updateCartBadge() {
    const badge = document.getElementById('cart-fab-badge');
    if (badge) {
        const totalPacks = globalCartPacks.reduce((sum, p) => sum + (p.multiplier || 1), 0);
        badge.innerText = totalPacks;
        
        // Add a little pop animation
        badge.style.transform = 'scale(1.3)';
        setTimeout(() => badge.style.transform = 'scale(1)', 200);
    }
}
