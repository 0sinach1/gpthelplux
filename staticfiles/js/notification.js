// ----- JS FOR NOTIFICATION.HTML -----

document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll('#type span');
    const unread = document.querySelector('#readmsgs .unread');
    const read = document.querySelector('#readmsgs .read');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active-type'));
            tab.classList.add('active-type');

            if (tab.textContent === 'Unread') {
                unread.style.display = 'flex';
                read.style.display = 'none';
            } else {
                unread.style.display = 'none';
                read.style.display = 'flex';
            }
        });
    });

    const unreadBox = document.querySelector('#readmsgs .unread');
    const readBox = document.querySelector('#readmsgs .read');

    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('mark-read')) {
            const msg = e.target.closest('.msg');  // the whole message block

            // Move to the read section
            readBox.appendChild(msg);

            // Remove the button so read messages don't have it
            e.target.remove();
        }
    });

    document.addEventListener('click', (e) => {
        // Delete button logic
        if (e.target.classList.contains('delete-msg')) {
            const confirmDelete = confirm("Are you sure you want to remove this message?");
            const msg = e.target.closest('.msg');
            if (confirmDelete) {
                msg.remove();
            }  
        }
    });

})