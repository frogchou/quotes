function copyLink() {
    const input = document.getElementById('share-link');
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999);
    document.execCommand('copy');
    alert('Link copied. Share it in WeChat or anywhere.');
}
