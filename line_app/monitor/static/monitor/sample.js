console.log('Sample script loaded.');

const bar = 2 + 2;

console.log('Sample calculation result:', bar);

document.addEventListener('DOMContentLoaded', function () {
	const sampleButton = document.getElementById('sampleButton');
	const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

	if (sampleButton) {
		sampleButton.addEventListener('click', function () {
			const isCancel = sampleButton.textContent === '解除';
			fetch('log/', {
				method: 'POST',
				headers: {
					'X-CSRFToken': csrfToken || '',
					'Content-Type': 'application/json'
				},
				credentials: 'same-origin',
				body: JSON.stringify({ is_cancel: isCancel , ok: true })
			})
			.then(response => response.json())
			.then(data => {
				if (data.ok) {
					console.log('サーバーとの通信成功');
					sampleButton.textContent = sampleButton.textContent === 'サンプルボタン' ? '解除' : 'サンプルボタン';
				}
			})
			.catch(error => console.error('通信エラー:', error));
		});
	}
});

if (confirm('サンプルスクリプトが正常に読み込まれました。')) {
	console.log('ユーザーは確認しました。');
}
else {
	console.log('ユーザーはキャンセルしました。');
}

const sampleElement = document.querySelectorAll('.sample-element');
console.log('Sample element:', sampleElement);
console.log('Number of sample elements:', sampleElement.length);
console.log('First sample element text:', sampleElement[0]?.textContent);
console.log('Second sample element text:', sampleElement[0]);