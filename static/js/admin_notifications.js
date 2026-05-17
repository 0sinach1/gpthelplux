document.addEventListener('DOMContentLoaded', function() {
    // Move #changelist-filter to be a sibling of .changelist-form-container
    const changelistFilter = document.querySelector('#changelist-filter');
    const changelistFormContainer = document.querySelector('.changelist-form-container');
    const changelist = document.querySelector('#changelist');

    if (changelistFilter && changelistFormContainer && changelist) {
        changelist.appendChild(changelistFilter);
    }

    const btn = document.getElementById('enable-notifs-btn');
    
    // 1. Setup Button Logic
    if (Notification.permission !== "granted") {
        if(btn) btn.style.display = "block";
    }

    if(btn) {
        btn.addEventListener('click', function() {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    btn.style.display = "none";
                    new Notification("Notifications Enabled", { body: "You will receive alerts for new orders and signups." });
                }
            });
        });
    }

    // 2. LOGIC FIX: Start with null so we know it's the first run
    let lastCount = null;

    function checkNewNotifications() {
        // If permission isn't granted, don't waste bandwidth checking
        if (Notification.permission !== "granted") return;

        fetch('/admin/api/check-notifications/')
        .then(res => {
            if (!res.ok) throw new Error("API Response invalid");
            return res.json();
        })
        .then(data => {
            const currentCount = data.count;

            // SCENARIO 1: First Run (Page Load)
            if (lastCount === null) {
                console.log(`Baseline established: ${currentCount} unread messages.`);
                lastCount = currentCount;
                return; // Stop here! Don't notify on first load.
            }

            // SCENARIO 2: New Data Detected
            if (currentCount > lastCount) {
                console.log("🔥 New Notification Detected!");
                
                const notif = new Notification(data.latest_title || "New System Alert", {
                    body: data.latest_message || "Check your admin dashboard for details.",
                    // FIX FOR 404 ERROR:
                    icon: '/static/images/titlelogo.png', 
                    tag: 'admin-alert', // Prevents duplicate stacking
                    requireInteraction: true // Keeps it on screen until clicked
                });

                notif.onclick = function() {
                    window.focus();
                    window.location.href = '/admin/MAIN/adminnotification/';
                    notif.close();
                };
            }

            // Always update the counter
            lastCount = currentCount;
        })
        .catch(err => console.error("Notification Check Failed:", err));
    }
    
    // Check immediately (to set baseline), then every 15 seconds
    checkNewNotifications();
    setInterval(checkNewNotifications, 15000); 
});