setInterval(function () {
    fetch(window.location.href)
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(html, 'text/html');
            const newContent = newDoc.querySelector('.monitor-section');
            const oldContent = document.querySelector('.monitor-section');
            if (newContent && oldContent) {
                oldContent.replaceWith(newContent);
            }
        })
        .catch(error => console.error('Update error:', error));
}, 5000);
