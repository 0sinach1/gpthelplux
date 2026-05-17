
document.addEventListener("DOMContentLoaded", () => {

    const track = document.querySelector(".hero-slider-tracker");
    const cards = Array.from(document.querySelectorAll(".hero-card"));
    const prevBtn = document.getElementById("heroPrevBtn");
    const nextBtn = document.getElementById("heroNextBtn");

    if (!track || cards.length === 0) return;

    // 🔥 CLONE FOR INFINITE LOOP
    const firstClones = cards.slice(0, 4).map(card => card.cloneNode(true));
    const lastClones = cards.slice(-4).map(card => card.cloneNode(true));

    firstClones.forEach(clone => track.appendChild(clone));
    lastClones.reverse().forEach(clone => track.insertBefore(clone, track.firstChild));

    const allCards = document.querySelectorAll(".hero-card");

    let index = 4; // start after clones
    const cardWidth = allCards[0].offsetWidth + 20;

    let position = index * cardWidth;

    track.style.transform = `translateX(-${position}px)`;

    let isPaused = false;
    let isInteracting = false;

    const dotsContainer = document.getElementById("heroDots");
    const visibleCards = 3;
    const totalRealCards = cards.length;
    const totalSlides = totalRealCards - visibleCards + 1;

    let dots = [];

    // 🔥 CREATE DOTS
    for (let i = 0; i < totalSlides; i++) {
        const dot = document.createElement("span");
        dot.classList.add("dot");

        if (i === 0) dot.classList.add("active");

        dot.addEventListener("click", () => {
            isInteracting = true;
            moveTo(i + 4); // +4 because of clones
            setTimeout(() => isInteracting = false, 2000);
        });

        dotsContainer.appendChild(dot);
        dots.push(dot);
    }

    function updateDots() {
        // normalize index (remove clone offset)
        let realIndex = index - 4;

        if (realIndex < 0) realIndex = totalSlides - 1;
        if (realIndex >= totalSlides) realIndex = 0;

        dots.forEach(dot => dot.classList.remove("active"));
        if (dots[realIndex]) dots[realIndex].classList.add("active");
    }

    // 🔁 AUTO SCROLL
    function autoSlide() {
        if (!isPaused && !isInteracting) {
            moveTo(index + 1);
        }
        setTimeout(autoSlide, 2500);
    }

    autoSlide();

    // 🔥 MOVE FUNCTION
    function moveTo(i) {
        track.style.transition = "transform 0.5s ease";
        index = i;
        position = index * cardWidth;

        track.style.transform = `translateX(-${position}px)`;

        updateDots(); // 🔥 ADD THIS
    }

    // 🔁 INFINITE FIX (NO JUMP)
    track.addEventListener("transitionend", () => {

        if (index >= allCards.length - 4) {
            track.style.transition = "none";
            index = 4;
            position = index * cardWidth;
            track.style.transform = `translateX(-${position}px)`;
        }

        if (index <= 0) {
            track.style.transition = "none";
            index = allCards.length - 8;
            position = index * cardWidth;
            track.style.transform = `translateX(-${position}px)`;
        }

        updateDots();
    });

    // ⬅️➡️ ARROWS (THIS WAS MISSING 🔥)
    nextBtn.addEventListener("click", () => {
        isInteracting = true;
        moveTo(index + 1);
        setTimeout(() => isInteracting = false, 2000);
    });

    prevBtn.addEventListener("click", () => {
        isInteracting = true;
        moveTo(index - 1);
        setTimeout(() => isInteracting = false, 2000);
    });

    // 🖱️ HOVER PAUSE
    track.addEventListener("mouseenter", () => isPaused = true);
    track.addEventListener("mouseleave", () => isPaused = false);

});
