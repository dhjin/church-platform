// Mobile Menu Toggle
const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
const navMenu = document.querySelector('.nav-menu');

if (mobileMenuToggle) {
    mobileMenuToggle.addEventListener('click', () => {
        mobileMenuToggle.classList.toggle('active');
        navMenu.classList.toggle('active');
    });

    // On mobile: dropdown parents toggle submenu; leaf links close nav
    document.querySelectorAll('.nav-menu a').forEach(link => {
        link.addEventListener('click', (e) => {
            const isMobile = window.innerWidth <= 1024;
            if (!isMobile) return; // Desktop uses CSS :hover, no JS needed

            const parentLi = link.closest('li.dropdown');
            if (parentLi && link.classList.contains('dropbtn')) {
                // Toggle the dropdown on this item
                e.preventDefault();
                // Close other open dropdowns
                document.querySelectorAll('.nav-item.dropdown.open').forEach(el => {
                    if (el !== parentLi) el.classList.remove('open');
                });
                parentLi.classList.toggle('open');
                return;
            }

            // It's a normal link (including sub-links) — close the nav
            mobileMenuToggle.classList.remove('active');
            navMenu.classList.remove('active');
            // Also close any open dropdowns
            document.querySelectorAll('.nav-item.dropdown.open').forEach(el => el.classList.remove('open'));
        });
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!navMenu.contains(e.target) && !mobileMenuToggle.contains(e.target)) {
            mobileMenuToggle.classList.remove('active');
            navMenu.classList.remove('active');
            document.querySelectorAll('.nav-item.dropdown.open').forEach(el => el.classList.remove('open'));
        }
    });
}

// Smooth scroll for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Active navigation link on scroll
const sections = document.querySelectorAll('section');
const navLinks = document.querySelectorAll('.nav-menu a');

window.addEventListener('scroll', () => {
    let current = '';

    sections.forEach(section => {
        const sectionTop = section.offsetTop;
        const sectionHeight = section.clientHeight;
        if (pageYOffset >= sectionTop - 200) {
            current = section.getAttribute('id');
        }
    });

    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${current}`) {
            link.classList.add('active');
        }
    });
});

// Add scroll effect to header
const header = document.querySelector('.header');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 100) {
        header.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.1)';
    } else {
        header.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
    }

    lastScroll = currentScroll;
});

// Intersection Observer for fade-in animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe all cards and announcement items
document.addEventListener('DOMContentLoaded', () => {
    const elements = document.querySelectorAll('.card, .announcement-item, .about-item, .contact-item');
    elements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });
});

// Naver Map Integration
// Map functionality removed - using static display instead

console.log('Church website loaded successfully!');

// Unified Video Tabs Functionality
function switchVideoTab(tabId) {
    // Exit "show all" mode
    const videoTabs = document.querySelector('.video-tabs');
    if (videoTabs) {
        videoTabs.classList.remove('show-all');
    }

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Find the button that was clicked and make it active
    const clickedBtn = document.querySelector(`.tab-btn[onclick="switchVideoTab('${tabId}')"]`);
    if (clickedBtn) {
        clickedBtn.classList.add('active');
    }

    // Update tab content panels
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    const targetContent = document.getElementById(`tab-${tabId}`);
    if (targetContent) {
        targetContent.classList.add('active');
    }
}

// Handle URL parameters for direct tab linking
function applyVideoTabFromHash() {
    const hash = window.location.hash; // e.g. "#videos?tab=sermons"
    if (hash && hash.includes('#videos')) {
        // Parse tab from the hash string itself (not window.location.search)
        const hashQuery = hash.split('?')[1] || '';
        const hashParams = new URLSearchParams(hashQuery);
        const tabParam = hashParams.get('tab');
        if (tabParam) {
            switchVideoTab(tabParam);
        }
        // Scroll the videos section into view
        const videosSection = document.getElementById('videos');
        if (videosSection) {
            setTimeout(() => {
                videosSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 50);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const hash = window.location.hash;
    if (hash && hash.includes('#videos')) {
        applyVideoTabFromHash();
    }
    // Default: show-all mode with no tab selected (class set in HTML)
});
window.addEventListener('hashchange', applyVideoTabFromHash);

// Intercept navbar dropdown video tab links on the same page (/#videos?tab=...)
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('a[href*="#videos?tab="], a[href*="/#videos?tab="]').forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            const tabMatch = href.match(/tab=([^&]+)/);
            if (!tabMatch) return;
            const tabId = tabMatch[1];

            // If on the homepage, prevent default and handle in-page
            if (window.location.pathname === '/' || window.location.pathname === '') {
                e.preventDefault();
                switchVideoTab(tabId);
                const videosSection = document.getElementById('videos');
                if (videosSection) {
                    videosSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
                // Update hash without reload
                history.pushState(null, '', `#videos?tab=${tabId}`);
            }
            // On other pages, let the default link navigate to /#videos?tab=... and
            // applyVideoTabFromHash will run on load
        });
    });
});

// YouTube Video Modal
function openVideoModal(videoId, isShorts) {
    const modal = document.getElementById('videoModal');
    const iframe = document.getElementById('videoIframe');
    const content = document.getElementById('videoModalContent');
    const container = document.getElementById('videoContainer');

    // 숏츠 모드: 세로 비율 (9:16)
    if (isShorts) {
        modal.classList.add('shorts-mode');
    } else {
        modal.classList.remove('shorts-mode');
    }

    iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeVideoModal(event) {
    if (event.target.classList.contains('video-modal') ||
        event.target.classList.contains('video-modal-close')) {
        const modal = document.getElementById('videoModal');
        const iframe = document.getElementById('videoIframe');
        iframe.src = '';
        modal.classList.remove('active');
        modal.classList.remove('shorts-mode');
        document.body.style.overflow = '';
    }
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('videoModal');
        if (modal.classList.contains('active')) {
            const iframe = document.getElementById('videoIframe');
            iframe.src = '';
            modal.classList.remove('active');
            modal.classList.remove('shorts-mode');
            document.body.style.overflow = '';
        }
    }
});

// Horizontal Carousel Scroll Function
function scrollCarousel(button, direction) {
    const container = button.closest('.carousel-container');
    if (!container) return;
    const track = container.querySelector('.carousel-track');
    if (!track) return;

    // Scroll by exact card width so snap boundaries align perfectly
    const firstCard = track.querySelector('.sermon-card, .shorts-card');
    const gap = parseFloat(getComputedStyle(track).gap) || 12;
    const scrollAmount = firstCard
        ? firstCard.offsetWidth + gap
        : track.clientWidth;

    track.scrollBy({ left: direction * scrollAmount, behavior: 'smooth' });
}
