window.addEventListener('beforeunload', function (event) {
    const port = window.location.port;
    const browserId = '<%= browser_id %>'; // This will be replaced with the actual browser ID
    const url = `http://localhost:${port}/shutdown?id=${browserId}`; // Include the browser ID in the URL

    if (navigator.sendBeacon) {
        const data = new Blob([], { type: 'application/x-www-form-urlencoded' });
        navigator.sendBeacon(url, data);
    } else {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url, false);
        xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
        xhr.send();
    }
});
