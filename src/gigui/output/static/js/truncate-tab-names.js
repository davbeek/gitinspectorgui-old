// Function to truncate the length of tab names longer than 20 characters, but
// only if the tab row height exceeds 3 times the default text height.
document.addEventListener("DOMContentLoaded", function () {
    const tabRow = document.getElementById('tabRow');
    const tabs = document.querySelectorAll('.nav-link');
    const defaultTextHeight = tabs[0].offsetHeight;

    if (tabRow.offsetHeight > 3 * defaultTextHeight) {
        tabs.forEach(tab => {
            const fullText = tab.textContent;
            if (fullText.length > 20) {
                tab.textContent = fullText.substring(0, 20) + '...';
                tab.setAttribute('title', fullText);
            }
        });
    }
});
