// Cloudinary background removal may initially return 423 while preparing a cutout.
// Retry the app-owned endpoint; never substitute the merchant original.
export function retryProductImage(image, fallback) {
  const attempt = Number(image.dataset.cleanupAttempt || 0) + 1;
  image.dataset.cleanupAttempt = String(attempt);
  if (attempt > 6 || !image.getAttribute('src')?.startsWith('/api/v1/product-images/')) {
    fallback(); return;
  }
  image.style.visibility = 'hidden';
  image.addEventListener('load', () => { image.style.visibility = ''; }, { once: true });
  setTimeout(() => {
    if (image.isConnected) image.src = image.getAttribute('src').split('?')[0] + '?retry=' + Date.now();
  }, Math.min(5000, attempt * 1500));
}
