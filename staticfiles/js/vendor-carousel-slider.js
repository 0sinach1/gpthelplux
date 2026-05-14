const track = document.getElementById("vendorsTrack");
const cards = document.querySelectorAll(".vendor-card");

const nextBtn = document.getElementById("nextBtn");
const prevBtn = document.getElementById("prevBtn");

let index = 0;
let visibleCards = getVisibleCards();
let cardWidth = getCardWidth();

/* 🔥 DETERMINE CARDS PER SCREEN */
function getVisibleCards() {
    if (window.innerWidth <= 480) return 1;
    if (window.innerWidth <= 768) return 2;
    if (window.innerWidth <= 1024) return 3;
    return 4;
}

/* 🔥 GET CARD WIDTH */
function getCardWidth() {
    return cards[0].offsetWidth + 20; // include gap
}

/* 🔥 UPDATE SLIDER POSITION */
function updateSlider() {
    track.style.transform = `translateX(-${index * cardWidth}px)`;
}

/* NEXT */
nextBtn.addEventListener("click", () => {
    if (index >= cards.length - visibleCards) {
        index = 0; // loop
    } else {
        index++;
    }
    updateSlider();
});

/* PREV */
prevBtn.addEventListener("click", () => {
    if (index <= 0) {
        index = cards.length - visibleCards;
    } else {
        index--;
    }
    updateSlider();
});

/* 🔥 HANDLE RESIZE LIKE A PRO */
window.addEventListener("resize", () => {
    visibleCards = getVisibleCards();
    cardWidth = getCardWidth();

    // prevent overflow bugs
    if (index > cards.length - visibleCards) {
        index = 0;
    }

    updateSlider();
});