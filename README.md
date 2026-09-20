# Bible Garden — Website

Static public websites for the Bible Garden and Lampada apps.

Domains:

- [bible.garden](https://bible.garden) — Bible Garden
- [lampada.app](https://lampada.app) — Lampada

## Features

- Coverflow phone carousel with app screenshots
- Canvas firefly particle animation
- Responsive design (Tailwind CSS)
- i18n with localStorage persistence
- Separate Lampada site in `lampada/` with EN/RU/UK translations
- Lampada privacy policy at `/privacy` and a reserved support page at `/support`
- Language selection uses `?lang=en|ru|uk`, remembers the choice and detects
  browser languages; `ua` links are accepted as an alias for Ukrainian (`uk`).

The Lampada logo assets are optimized derivatives of
`assets/icon.png` from `BibleGarden/Lampada-Mobile`. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and license.

## Stack

- HTML + Tailwind CSS (CDN)
- Google Fonts: Lora + Inter on the Bible Garden site
- Vanilla JavaScript
- No build step required

The Lampada site uses system fonts and makes no font or analytics requests to
third parties.

## Run locally

```bash
python3 -m http.server 8080
# open http://localhost:8080

# Preview the Lampada virtual host content
cd lampada && python3 -m http.server 8081
# open http://localhost:8081
```

## License

GPL v3 — see [LICENSE](LICENSE).
