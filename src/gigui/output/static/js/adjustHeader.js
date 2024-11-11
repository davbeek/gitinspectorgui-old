
// Adjust the top position of the header rows based on the height of the tab row
// This allow the header rows to be displayed below the tab row, which is necessary to
// freeze the header row under the tab row when scrolling
window.addEventListener('load', function () {
    var tabRow = document.getElementById('tabRow');
    var headerRows = document.querySelectorAll('.headerRow');
    var tabRowHeight = tabRow.offsetHeight;
    headerRows.forEach(function (headerRow) {
        headerRow.style.top = tabRowHeight + 'px';
    });
});
