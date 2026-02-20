console.log('Auto-update script loaded.');

console.log('Current cookies:', document.cookie);

if (document.cookie === undefined) {
	console.warn('Cookies are not supported in this environment. Auto-update may not work properly.');
} else {
	console.log('Cookies are supported. Auto-update should work properly.');
	console.log('Current cookies:', document.cookie);
}

const foo = 1 + 1;

setInterval(() => {
	// console.log('5秒経過しました');

	fetch(window.location.href)
		.then(response => response.text())
		// .then(data => console.log('Response data:', data))
}, 5000);

