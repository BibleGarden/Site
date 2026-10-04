---
title: "Open-Source Bible App: Why Bible Garden's Code Is Open and How to Help"
description: "Bible Garden is a free, open-source Bible app for iPhone and iPad. See what's on GitHub under GPL-3.0, how Bible texts and audio are licensed, and how to get involved."
date: 2026-10-04
draft: true
---

[Bible Garden](/) is a free Bible app for reading and listening on iPhone and iPad, with no ads and no in-app purchases. The code for the app, the server, the admin tools, and this website is on [GitHub](https://github.com/BibleGarden/) under the GPL-3.0 license: you can read it, check it, build on it, and suggest changes. Below: what exactly is open, why, how the Bible texts and recordings are licensed, and how you can help. To be upfront, the project was created and is run by one person, Maria Novikova, so every bit of help counts.

## What's open, and under which license
<!-- screen: home -->

As of October 4, 2026, these repositories in the [BibleGarden organization on GitHub](https://github.com/BibleGarden/) are public:

| Repository | What's inside |
|---|---|
| [iOS-App](https://github.com/BibleGarden/iOS-App) | the iPhone and iPad app (SwiftUI) |
| [Bible-API](https://github.com/BibleGarden/Bible-API) | the server: texts, audio, and verse timings in the recordings |
| [Dashboard-API](https://github.com/BibleGarden/Dashboard-API) and [Dashboard-Web](https://github.com/BibleGarden/Dashboard-Web) | the admin tools: checking how audio lines up with the text, and preparing data |
| [Site](https://github.com/BibleGarden/Site) | the bible.garden website and these articles |
| [Architecture](https://github.com/BibleGarden/Architecture) | system overview and architecture decisions |

All of it is licensed under GPL-3.0. It's a free software license: you can use, modify, and share the code; if you distribute a modified version, it must also be released under GPL-3.0 together with its source code ([license text](https://www.gnu.org/licenses/gpl-3.0.html)).

A few internal pieces stay private: production server settings and keys, the scripts that prepare texts and audio for import, and our AI model research.

## Why we keep the code open

**So you can verify our promises.** Our [privacy policy](/privacy.html?lang=en) says the app needs no account, has no analytics, ads, or third-party trackers, and talks only to our own server, api.bible.garden. With open code, you don't have to take our word for it: a developer can read the code and check.

**So it's clear the app is truly free.** Bible Garden has no ads, subscriptions, or paid features, and the code shows there's no hidden monetization either.

**So others can learn from the work.** The most laborious part of the project is marking the exact second each verse starts in a recording. The code that stores and serves those timings, and the admin tools used to check them, are open.

**So you can build something better on top of it.** Want to make your own app? Fork it, improve it, ship it — we'd love that. If you distribute a modified version, GPL-3.0 requires you to share its source code under the same license. You can ask us for an API key and the prepared data, within the rights for each text and recording.

## What's inside: a Bible you can listen to verse by verse
<!-- screen: multi-reading -->

Bible Garden is built for listening first. The audio is timed verse by verse, so the "previous / next verse" buttons jump to the exact start of a verse, and you can add a pause after every verse, paragraph, or section — for a few seconds or until you tap Play. For BSB, you can choose Bob Souer or David; the US edition of WEB is read by Winfred Henson. You can hear a sample of each voice before you choose.

<div class="article-callout" markdown="1">
**Bible Garden's signature feature is Multi Reading.** You build a sequence — a translation, a pause, another translation — and every verse, paragraph, section, or chapter plays in each translation in turn. For example, a verse in the Berean Standard Bible, then the same verse in the World English Bible, or in Russian or Ukrainian. The screen shows the same verse in every translation of the sequence. Multi Reading pairs verses by their position, not by matching their meaning. For Psalms, use translations with the same psalm numbering: BSB and both WEB editions use Hebrew numbering, as does the Ukrainian Khomenko translation. The Russian Synodal and Kulakov translations and Ukrainian NPU use Greek numbering; avoid mixing the two groups in Psalms. More in "[Bilingual Bible App](/articles/bible-in-two-languages/)."
</div>

What the app doesn't have yet: offline audio downloads, search, bookmarks, notes, reading plans, and reminders. A web version and Android are in our plans.

## Bible texts and recordings: the code license doesn't cover them
<!-- screen: translation-picker-english -->

GPL-3.0 applies only to our code. Bible texts and audio recordings are other people's works, and each has its own status:

- **Berean Standard Bible (BSB)** — the publishers placed it in the public domain on April 30, 2023 ([berean.bible](https://berean.bible/licensing.htm)).
- **World English Bible (WEB)** — also public domain, but the name is a trademark: a changed text can't be called the WEB ([eBible.org](https://ebible.org/eng-web/copyright.htm)). The app has its US and British editions.
- **Russian Synodal Bible** — first published in full in 1876 and in the public domain ([Wikipedia](https://en.wikipedia.org/wiki/Russian_Synodal_Bible)).
- **New Ukrainian Translation (NPU)** by Biblica — New Testament and Psalms, licensed CC BY-SA 4.0 ([eBible.org](https://ebible.org/find/details.php?id=ukronpu)). Biblica released the NPU audio under the same license ([Open.Bible](https://open.bible/bibles/ukrainian-biblica-audio-nt/)).
- **The Kulakov translation (Russian), the Khomenko translation (Ukrainian), and the other recordings** belong to their rights holders. Our code license doesn't extend to them.

That's a big reason we offer BSB and WEB in English: both are modern, readable, and free for anyone to use. The prepared data — texts and verse timings for the audio — isn't in the repositories, but we can share it on request (see the developer section below). What we can share depends on the rights for each text and recording.

It's also why the selection is small: BSB and WEB in English, Synodal and Kulakov in Russian, Khomenko and NPU in Ukrainian. Every new text and recording comes down to rights, and we also pick recordings by ear. For help choosing, see "[Which Bible Translation Is Best?](/articles/which-bible-translation/)" and, on narrators, "[Audio Bible narrators](/articles/audio-bible-narrators/)." If you're a rights holder and believe a text or recording is used improperly, message us on [Telegram](https://t.me/Mandarinka4) and we'll look into it and fix it.

## How to help
<!-- screen: classic-reading-english -->

What the project needs most is people who can help add new languages: find good translations and recordings, sort out the rights, and check how the audio lines up with the text. Maria coordinates this work and helps at every step.

For the steps involved and how to get started, see "[How to help Bible Garden](/articles/help-bible-garden/)."

## For developers

- **The iOS app** is written in SwiftUI and runs on iOS 15 or later, on iPhone and iPad. The API client is generated from an OpenAPI spec at build time. To build it, you need an API URL and key in local config files (see the repository's README).
- **Server and admin tools:** Bible-API and Dashboard-API use FastAPI and MySQL; the Dashboard-Web admin uses Vue 3. The same Bible-API also powers our second app, [Lampada](https://lampada.app/), a space for personal prayer. The website is built by a small Python generator from Markdown and YAML.
- **API access requires an app key.** If you're building an app or doing research, message us on [Telegram](https://t.me/Mandarinka4) or open an issue in [GitHub Issues](https://github.com/BibleGarden/Bible-API/issues): tell us about your project, and we'll issue a key. You can also request the prepared data — texts and verse timings — to run the server from source yourself. One caveat: some translations and recordings can only be shared within their licenses, so what we can provide depends on what the rights holders allow.
- **There's no CONTRIBUTING file or issue templates yet.** Code and testing conventions are described in CLAUDE.md files (plus AGENTS.md in the app and Bible-API) in the app, server, and admin repositories. Before a large change, open an issue and describe your idea so your work doesn't go to waste. For a machine-readable index of this site, see [llms.txt](/llms.txt).

## Other open-source Bible apps

If open source is what matters most to you, here are a few long-running projects (licenses checked on GitHub on October 4, 2026):

- **[AndBible](https://andbible.org/)** — a Bible study app for Android, GPL-3.0;
- **[Quick Bible](https://github.com/yukuku/androidbible)** (Alkitab in Indonesia) — a Bible reader for Android, Apache-2.0;
- **[Xiphos](https://xiphos.org/)** and **[BibleTime](https://github.com/bibletime/bibletime)** — Bible study software for desktop computers, GPL-2.0.

They're strong at reading, study, and module libraries; Bible Garden is strong at listening: verse by verse, with pauses, in several translations in a row. For a comparison of popular free listening apps, see "[Free audio Bible apps](/articles/free-audio-bible-apps/)."

## Frequently asked questions {#faq}

### Is Bible Garden really free?

Yes. The app has no ads, subscriptions, or purchases, and no account is needed. It runs on iPhone and iPad with iOS 15 or later.

### What license is Bible Garden's code under?

GPL-3.0: the iOS app, the server, the admin tools, the website, and the architecture docs. Internal pieces — server settings, data preparation scripts, and AI model research — are private.

### Can I use the Bible texts and audio from the app in my own project?

Our code license doesn't cover them. BSB, WEB, and the Russian Synodal Bible are in the public domain; the Ukrainian NPU text and audio are under CC BY-SA 4.0. The Kulakov and Khomenko translations and the other recordings belong to their rights holders, so check their terms of use.

### Can my app use the Bible Garden API?

Yes, with a key: every API request requires an app key. Message us on [Telegram](https://t.me/Mandarinka4) or in [GitHub Issues](https://github.com/BibleGarden/Bible-API/issues), tell us about your project, and we'll issue one. You can also request the prepared data to run the server yourself. Some translations and recordings can only be shared within their licenses.

### Is Bible Garden available on Android or the web?

Not yet; the app is only for iPhone and iPad. A web version and Android are in our plans. If you need an open-source Android Bible app today, try AndBible.

### How can I help add a new language to Bible Garden?

Message us on [Telegram](https://t.me/Mandarinka4) with the language and how you'd like to help: finding translations and recordings, sorting out rights, or checking how the text and audio line up. Maria coordinates this work and helps along the way.
