function copyLink() {
    const input = document.getElementById('share-link');
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999);
    document.execCommand('copy');
    alert('Link copied. Share it in WeChat or anywhere.');
}

document.addEventListener('DOMContentLoaded', () => {
    const aiButton = document.getElementById('ai-explain-btn');
    const contentField = document.getElementById('quote-content');
    const explanationField = document.getElementById('quote-explanation');
    const promptField = document.getElementById('ai-prompt');
    const hint = document.getElementById('ai-explain-hint');

    if (!aiButton || !contentField || !explanationField) return;

    const setHint = (text, isError = false) => {
        if (!hint) return;
        hint.textContent = text;
        hint.style.color = isError ? '#9b1c1c' : '';
    };

    aiButton.addEventListener('click', async () => {
        const content = contentField.value.trim();
        if (!content) {
            setHint('请先填写语录内容。', true);
            return;
        }
        setHint('AI 正在生成解释…');
        aiButton.disabled = true;
        aiButton.textContent = '生成中…';
        try {
            const formData = new FormData();
            formData.append('content', content);
            formData.append('prompt', promptField ? promptField.value : '');
            const response = await fetch('/api/ai-explanation', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            if (!response.ok || data.error) {
                const message = data?.error?.message || 'AI 生成失败，请稍后再试。';
                setHint(message, true);
                return;
            }
            explanationField.value = data.explanation || '';
            setHint('已填充 AI 解释');
        } catch (err) {
            console.error(err);
            setHint('调用 AI 时出现问题，请稍后重试。', true);
        } finally {
            aiButton.disabled = false;
            aiButton.textContent = 'AI解释';
        }
    });
});
