// Generate a random 12-character alphanumeric string to force reload
function generateRandomString(length) {
    const characters = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * characters.length));
    }
    return result;
}
const cacheBuster = generateRandomString(12);
if (!window.location.search.includes('v=')) {
    window.location.search += (window.location.search ? '&' : '?') + 'v=' + cacheBuster;
}
