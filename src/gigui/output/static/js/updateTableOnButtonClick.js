// Function to update the visibility of rows based on the state of the buttons:
// .blame-exclusions-button, .blame-empty-lines-button, and .hide-colors-button
document.addEventListener("DOMContentLoaded", function () {

    const updateRows = () => {
        document.querySelectorAll('table').forEach(table => {
            const exclusionsButton = table.querySelector('.blame-exclusions-button');
            const emptyLinesButton = table.querySelector('.blame-empty-lines-button');
            const hideColorsButton = table.querySelector('.hide-colors-button');

            const isExclusionsPressed = exclusionsButton ? exclusionsButton.classList.contains('pressed') : false;
            const isEmptyLinesPressed = emptyLinesButton ? emptyLinesButton.classList.contains('pressed') : false;
            const isHideColorsPressed = hideColorsButton ? hideColorsButton.classList.contains('pressed') : false;

            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const codeCell = row.querySelector('.code-col');
                const firstCell = row.cells[0];
                const secondCell = row.cells[1];
                const isEmptyLine = codeCell && codeCell.textContent.trim() === '';
                const isExcludedAuthor = firstCell && secondCell && firstCell.textContent.trim() === '0' && !secondCell.textContent.includes('*');

                row.style.display = (isExcludedAuthor && isExclusionsPressed)
                    || (isEmptyLine && isEmptyLinesPressed) ? 'none' : '';

                if (isHideColorsPressed) {
                    row.classList.add('hide-colors');
                } else {
                    row.classList.remove('hide-colors');
                }
            });
        });
    };

    const addEventListenersToButtons = () => {
        document.querySelectorAll('.blame-empty-lines-button, .blame-exclusions-button, .hide-colors-button').forEach(button => {
            if (!button.classList.contains('hide-colors-button')) {
                // Set initial state based on the presence of the 'pressed' class
                updateRows()
            };

            button.onclick = function () {
                button.classList.toggle('pressed');
                updateRows();
            };
        });
    };

    // Use MutationObserver to watch for changes in the DOM and add event listeners to the buttons
    const observer = new MutationObserver((mutationsList) => {
        for (const mutation of mutationsList) {
            if (mutation.type === 'childList') {
                addEventListenersToButtons();
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Initial call to add event listeners to existing buttons
    addEventListenersToButtons();
});
