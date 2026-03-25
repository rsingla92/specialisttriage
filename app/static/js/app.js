/* SpecialistTriage BC – client-side helpers */

// Auto-dismiss alerts after 6 seconds
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(function (el) {
    setTimeout(function () {
      if (typeof bootstrap !== 'undefined') {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
        bsAlert.close();
      } else {
        el.style.display = 'none';
      }
    }, 6000);
  });
});
