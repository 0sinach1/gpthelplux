// JS FOR CUSTOMERPAGE.HTML

document.addEventListener("DOMContentLoaded", () => {
    const items = document.querySelectorAll('.menu li');
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

            if (tab.textContent === 'Completed/Delivered') {
                uncompleted.style.display = 'flex';
                completed.style.display = 'none';
            } else {
                uncompleted.style.display = 'none';
                completed.style.display = 'flex';
            }
        });
    });

})