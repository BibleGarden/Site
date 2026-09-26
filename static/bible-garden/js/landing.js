// === Navbar scroll ===
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
    navbar.classList.toggle('nav-solid', window.scrollY > 50);
}, { passive: true });

// === Mobile menu ===
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const mobileMenu = document.getElementById('mobile-menu');
mobileMenuBtn.addEventListener('click', () => {
    mobileMenu.classList.toggle('hidden');
    // Add solid background when mobile menu is open
    if (!mobileMenu.classList.contains('hidden')) {
        navbar.classList.add('nav-solid');
    } else if (window.scrollY <= 50) {
        navbar.classList.remove('nav-solid');
    }
});
// Close mobile menu on link click
mobileMenu.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
        if (window.scrollY <= 50) {
            navbar.classList.remove('nav-solid');
        }
    });
});

// === Scroll reveal ===
const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            revealObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// === Smooth scroll for nav links ===
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// === Coverflow carousel (circular) ===
(() => {
    const slides = document.querySelectorAll('.coverflow-slide');
    const dots = document.querySelectorAll('#coverflow-dots .carousel-dot');
    const total = slides.length;
    let current = 0;
    let interval;

    function getSpacing() {
        return window.innerWidth < 768 ? 100 : 125;
    }

    function getScale() {
        return window.innerWidth < 768
            ? { center: 1.1, near: 0.88, far: 0.72 }
            : { center: 1.15, near: 0.9, far: 0.75 };
    }

    // Shortest circular distance from index i to current
    function circularOffset(i, center) {
        let diff = i - center;
        if (diff > total / 2) diff -= total;
        if (diff < -total / 2) diff += total;
        return diff;
    }

    function layout() {
        const spacing = getSpacing();
        const scale = getScale();

        slides.forEach((slide, i) => {
            const offset = circularOffset(i, current);
            const absOff = Math.abs(offset);

            slide.classList.remove('cf-center', 'cf-left-1', 'cf-right-1', 'cf-left-2', 'cf-right-2', 'cf-hidden');

            if (absOff === 0) {
                slide.classList.add('cf-center');
                slide.style.transform = `translate(-50%, -50%) translateX(0) scale(${scale.center})`;
            } else if (absOff === 1) {
                slide.classList.add(offset < 0 ? 'cf-left-1' : 'cf-right-1');
                slide.style.transform = `translate(-50%, -50%) translateX(${offset * spacing}px) scale(${scale.near})`;
            } else if (absOff === 2) {
                slide.classList.add(offset < 0 ? 'cf-left-2' : 'cf-right-2');
                slide.style.transform = `translate(-50%, -50%) translateX(${offset * spacing}px) scale(${scale.far})`;
            } else {
                slide.classList.add('cf-hidden');
                const dir = offset > 0 ? 1 : -1;
                slide.style.transform = `translate(-50%, -50%) translateX(${dir * 3 * spacing}px) scale(0.6)`;
            }
        });

        dots.forEach((dot, i) => {
            dot.classList.toggle('active', i === current);
        });
    }

    function goTo(index) {
        current = ((index % total) + total) % total;
        layout();
    }

    function next() { goTo(current + 1); }

    function startAutoplay() { interval = setInterval(next, 4000); }
    function resetAutoplay() { clearInterval(interval); startAutoplay(); }

    dots.forEach(dot => {
        dot.addEventListener('click', () => {
            goTo(parseInt(dot.dataset.slide));
            resetAutoplay();
        });
    });

    slides.forEach(slide => {
        slide.addEventListener('click', () => {
            const idx = parseInt(slide.dataset.index);
            if (idx !== current) { goTo(idx); resetAutoplay(); }
        });
    });

    window.addEventListener('resize', layout);
    layout();
    startAutoplay();
})();

// === Canvas fireflies (from v2) ===
(() => {
    const canvas = document.getElementById('fireflies');
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animId;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function createParticles() {
        const count = Math.min(Math.floor(window.innerWidth / 25), 50);
        particles = [];
        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                size: Math.random() * 2.5 + 1,
                speedX: (Math.random() - 0.5) * 0.3,
                speedY: (Math.random() - 0.5) * 0.3,
                opacity: Math.random(),
                opacityDir: (Math.random() - 0.5) * 0.015,
                hue: Math.random() > 0.3 ? 45 : 100,
            });
        }
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.x += p.speedX;
            p.y += p.speedY;
            p.opacity += p.opacityDir;

            if (p.opacity <= 0.05 || p.opacity >= 0.9) p.opacityDir *= -1;
            if (p.x < -10) p.x = canvas.width + 10;
            if (p.x > canvas.width + 10) p.x = -10;
            if (p.y < -10) p.y = canvas.height + 10;
            if (p.y > canvas.height + 10) p.y = -10;

            const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 3);
            const color = p.hue === 45
                ? `rgba(229, 168, 50, ${p.opacity * 0.6})`
                : `rgba(100, 180, 80, ${p.opacity * 0.4})`;
            gradient.addColorStop(0, color);
            gradient.addColorStop(1, 'transparent');

            ctx.beginPath();
            ctx.fillStyle = gradient;
            ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
            ctx.fill();

            ctx.beginPath();
            ctx.fillStyle = p.hue === 45
                ? `rgba(240, 210, 120, ${p.opacity})`
                : `rgba(160, 220, 120, ${p.opacity * 0.8})`;
            ctx.arc(p.x, p.y, p.size * 0.5, 0, Math.PI * 2);
            ctx.fill();
        });
        animId = requestAnimationFrame(animate);
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!prefersReducedMotion.matches) {
        resize();
        createParticles();
        animate();
        window.addEventListener('resize', () => { resize(); createParticles(); });
    }

    prefersReducedMotion.addEventListener('change', (e) => {
        if (e.matches) {
            cancelAnimationFrame(animId);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        } else {
            resize();
            createParticles();
            animate();
        }
    });
})();
