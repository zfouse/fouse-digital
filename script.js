/* Requests open in the visitor's email app. This static site stores no requests. */
const REVIEW_EMAIL = 'fousedigital@gmail.com';

const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#site-nav');
if (menuButton && navigation) {
  menuButton.hidden = false;
  navigation.dataset.enhanced = 'true';
  const closeMenu = () => {
    navigation.classList.remove('is-open');
    menuButton.setAttribute('aria-expanded', 'false');
  };
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('is-open', open);
  });
  navigation.addEventListener('click', event => {
    if (event.target.closest('a')) closeMenu();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && navigation.classList.contains('is-open')) {
      closeMenu();
      menuButton.focus();
    }
  });
}

document.querySelectorAll('[data-interest]').forEach(link => {
  link.addEventListener('click', () => {
    document.querySelector('#interest').value = link.dataset.interest;
  });
});

document.querySelector('#year').textContent = new Date().getFullYear();
const reviewForm = document.querySelector('#review-form');
const formStatus = document.querySelector('#form-status');
if (REVIEW_EMAIL) {
  document.querySelector('#delivery-note').textContent = 'This prepares an email in your email app. Send it there to complete your request.';
  const submitButton = reviewForm.querySelector('button[type="submit"]');
  submitButton.disabled = false;
  submitButton.textContent = 'Prepare my review request ↗';
}
reviewForm.addEventListener('submit', event => {
  event.preventDefault();
  if (!reviewForm.reportValidity()) return;
  if (!REVIEW_EMAIL) {
    formStatus.textContent = 'This request has not been sent. The contact inbox is not connected yet.';
    return;
  }
  const data = new FormData(reviewForm);
  const field = name => String(data.get(name) || '').trim();
  const subject = `Free lead-path review: ${field('business').replace(/[\r\n]/g, ' ')}`;
  const body = [
    'I would like a free lead-path review.', '',
    `Name: ${field('name')}`, `Business: ${field('business')}`,
    `Reply email: ${field('email')}`, `Website or listing: ${field('website') || 'None yet'}`,
    `Service and area: ${field('service')}`, `Interested in: ${field('interest')}`
  ].join('\n');
  window.location.href = `mailto:${REVIEW_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  formStatus.textContent = 'Your email app should open with your request. Send the email there to finish. Nothing has been submitted on this page.';
});
