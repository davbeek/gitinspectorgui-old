// Global variables to store the state of the buttons in the Code column of the blame
// tables. These variables are used to determine which rows to display based on the
// button state. The variables are toggled by clicking the buttons in the Code column.
var isExclusionsPressed = '<%= blame_exclusions_hide %>';
var isEmptyLinesPressed = isExclusionsPressed;
var isHideColorsPressed = false;
