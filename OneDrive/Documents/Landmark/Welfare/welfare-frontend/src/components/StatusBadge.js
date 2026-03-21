// src/components/StatusBadge.jsx
// Handles all status types including new notification statuses

export default function StatusBadge({ status, pickupType }) {
    // Emergency pickup request
    if (pickupType === 'emergency' && status === 'PICKUP_REQUESTED') {
        return (
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide bg-red-100 text-red-700 border border-red-200">
                <span>●</span> ⚡ Emergency
            </span>
        )
    }

    const styles = {
        // Package statuses
        PENDING_ARRIVAL: {
            classes: 'bg-yellow-50 text-yellow-700 border-yellow-200',
            label: '⏳ Pending Arrival',
        },
        ARRIVED: {
            classes: 'bg-blue-50 text-blue-700 border-blue-200',
            label: '📦 Arrived',
        },
        READY_FOR_PICKUP: {
            classes: 'bg-amber-50 text-amber-700 border-amber-200',
            label: '🔔 Ready for Pickup',
        },
        PICKUP_REQUESTED: {
            classes: 'bg-purple-50 text-purple-700 border-purple-200',
            label: '🙋 Pickup Requested',
        },
        PICKED_UP: {
            classes: 'bg-green-50 text-green-700 border-green-200',
            label: '✅ Picked Up',
        },
        // Notification statuses
        PENDING: {
            classes: 'bg-yellow-50 text-yellow-700 border-yellow-200',
            label: '⏳ Awaiting Confirmation',
        },
        APPROVED: {
            classes: 'bg-green-50 text-green-700 border-green-200',
            label: '✅ Approved',
        },
        REJECTED: {
            classes: 'bg-red-50 text-red-700 border-red-200',
            label: '❌ Rejected',
        },
    }

    const style = styles[status] || {
        classes: 'bg-slate-50 text-slate-600 border-slate-200',
        label: status,
    }

    return (
        <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold border ${style.classes}`}>
            {style.label}
        </span>
    )
}