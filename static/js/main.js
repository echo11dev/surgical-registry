/**
 * University of Miami Hip & Knee Arthroplasty Registry
 * Shared JavaScript utilities
 * Loaded from /static/js/main.js - cached by browser
 */

// Auto-dismiss non-persistent alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        document.querySelectorAll('.alert:not(.alert-persistent)').forEach(function(alert) {
            if (typeof bootstrap !== 'undefined' && bootstrap.Alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } else {
                alert.style.transition = 'opacity 0.3s';
                alert.style.opacity = '0';
                setTimeout(function() { alert.remove(); }, 300);
            }
        });
    }, 5000);
});

/**
 * Confirm delete with native dialog (used by delete buttons)
 * For production, could be upgraded to a Bootstrap modal confirmation.
 */
function confirmDelete(formId, entityName) {
    if (confirm('Are you sure you want to permanently delete this ' + entityName + '? This action cannot be undone.')) {
        const form = document.getElementById(formId);
        if (form) form.submit();
    }
}

/**
 * Generic flash message helper (if needed by other scripts)
 */
function showFlashMessage(message, type) {
    type = type || 'info';
    const container = document.getElementById('flash-container') || document.body;
    const div = document.createElement('div');
    div.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
    div.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.prepend(div);
    setTimeout(function() {
        if (div.parentNode) div.parentNode.removeChild(div);
    }, 5000);
}

// Expose for debugging / extension in dev
window.UMRegistry = { confirmDelete: confirmDelete, showFlashMessage: showFlashMessage };
