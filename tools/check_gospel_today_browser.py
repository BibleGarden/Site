"""Headless Chromium checks against a fixture preview and real local Bible-API audio.

Requires Playwright in the invoking Python and a separately served preview with
/tests/fixtures/gospel-today copied into its temporary article content directory.
No audio responses or timing data are mocked. Screenshots/report stay outside git.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def run(base_url, output):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for lang in ('ru', 'uk'):
            for date in ('2026-10-05', '2026-04-09'):
                for width in (1440, 390):
                    for theme in ('light', 'dark'):
                        context = browser.new_context(viewport={'width': width, 'height': 1000}, color_scheme=theme)
                        page = context.new_page()
                        errors, media_requests = [], []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.on('request', lambda r: media_requests.append(urlsplit(r.url).path) if '/api/audio/' in r.url else None)
                        page.add_init_script(f"""const NativeDate=Date;
window.Date=class extends NativeDate {{constructor(...args){{super(...(args.length?args:['{date}T12:00:00']));}} static now(){{return new NativeDate('{date}T12:00:00').getTime();}}}};
window.__media=[]; const NativeAudio=Audio;
window.Audio=function(){{const a=new NativeAudio();__media.push(a);return a;}};
Object.defineProperty(window,'GospelAudio',{{get(){{return this.__audioApi;}},set(api){{
 const original=api.mountAudio; api.mountAudio=(controls,playlist,...args)=>{{
  window.__playlist=playlist;window.__controls=controls;
  return window.__player=original(controls,playlist,...args);
 }};this.__audioApi=api;
}}}});
document.addEventListener('DOMContentLoaded',()=>document.documentElement.dataset.theme='{theme}');""")
                        page.goto(f'{base_url}/{lang}/articles/gospel-today-fixture/')
                        page.wait_for_selector('[data-gospel-status]', state='hidden')
                        page.wait_for_load_state('networkidle')
                        page.evaluate('document.fonts.ready')
                        assert not media_requests and page.evaluate('__media.length') == 0
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        assert page.locator('.gospel-today-links').evaluate('(e)=>!e.closest(".gospel-today")')
                        assert page.locator('.gospel-today-window').evaluate('(e)=>getComputedStyle(e).overflowY === "visible" && e.scrollHeight <= e.clientHeight+1')
                        contrast = page.locator('.gospel-today').evaluate('''e => {
 const s=getComputedStyle(e),rgb=v=>v.match(/[0-9.]+/g).slice(0,3).map(Number);
 const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
 const a=lum(rgb(s.color)),b=lum(rgb(s.backgroundColor));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}''')
                        assert contrast >= 4.5, contrast
                        before = page.locator('.gospel-today').bounding_box()['height']
                        page.locator('.gospel-player-toggle').click()
                        page.wait_for_function('__media.length===1 && !__media[0].paused && __media[0].currentTime>__playlist[0].begin', timeout=15000)
                        assert page.locator('[aria-current="true"]').count() == 1
                        assert page.locator('.gospel-reading.is-current').count() == 1
                        first_path = urlsplit(page.evaluate('__media[0].src')).path
                        first_reading = page.evaluate('__playlist[0].reading')
                        page.locator('.gospel-player-toggle').click()
                        assert page.evaluate('__media[0].paused')
                        page.locator('.gospel-player-toggle').click()
                        # Seek to the final selected verse of the Apostle. Real playback crosses
                        # its boundary naturally and must start the next reading/chapter.
                        next_index = page.evaluate('__playlist.findIndex(s=>s.reading!==__playlist[0].reading)')
                        assert next_index > 0
                        page.evaluate('(n)=>__player.jump(n-1)', next_index)
                        page.wait_for_function('(n)=>!__media[0].paused && __media[0].currentTime>=__playlist[n-1].begin', arg=next_index)
                        page.evaluate('(n)=>{__media[0].currentTime=__playlist[n-1].end-0.12;}', next_index)
                        page.wait_for_function('(n)=>__controls.current.textContent===__playlist[n].reading && !__media[0].paused && __media[0].currentTime>__playlist[n].begin', arg=next_index, timeout=15000)
                        assert page.locator('.gospel-player-row input').evaluate('(e)=>Number(e.value)>0')
                        second_path = urlsplit(page.evaluate('__media[0].src')).path
                        assert first_path != second_path
                        second_reading = page.evaluate('__controls.current.textContent')
                        assert abs(before - page.locator('.gospel-today').bounding_box()['height']) < 1
                        page.locator('.gospel-player-toggle').click()
                        # Per-reading button restarts the Apostle using the same player.
                        page.locator('.gospel-reading-play').first.click()
                        page.wait_for_function('__controls.current.textContent===__playlist[0].reading && !__media[0].paused')
                        page.locator('.gospel-player-toggle').click()
                        page.locator('[data-gospel-today]').evaluate('(e)=>scrollTo(0,e.getBoundingClientRect().top+scrollY-24)')
                        screenshot = f'{lang}-{date}-{width}-{theme}.png'
                        page.screenshot(path=str(output / screenshot))
                        assert not errors, errors
                        results.append({'lang': lang, 'date': date, 'width': width, 'theme': theme,
                                        'first': first_reading, 'second': second_reading,
                                        'audio_paths': [first_path, second_path], 'screenshot': screenshot,
                                        'layout_shift': 0, 'text_contrast': round(contrast,2)})
                        print(f'{lang} {date} {width} {theme}: Apostle → Gospel; actual audio, jump, highlight, progress, layout OK', flush=True)
                        context.close()
        # Text choices preserve the page's date/calendar, reuse the day on voice change,
        # persist on reload and show NPU's missing OT explicitly.
        for lang in ('ru','uk'):
            context = browser.new_context(viewport={'width':390,'height':1000})
            page = context.new_page()
            page.add_init_script("const NativeDate=Date;window.Date=class extends NativeDate {constructor(...a){super(...(a.length?a:['2026-03-02T12:00:00']));} static now(){return new NativeDate('2026-03-02T12:00:00').getTime();}};")
            requests = []
            page.on('request',lambda r: requests.append(urlsplit(r.url).path) if '/data/gospel-today/' in r.url else None)
            page.goto(f'{base_url}/{lang}/articles/gospel-today-fixture/')
            page.wait_for_selector('[data-gospel-status]',state='hidden')
            calendar = page.locator('.gospel-calendar').text_content()
            page.locator('[data-gospel-language]').select_option('uk')
            page.locator('[data-gospel-edition]').select_option('npu')
            page.wait_for_function('document.querySelector("[data-gospel-status]").hidden && document.querySelector(".gospel-unavailable")')
            assert page.locator('.gospel-unavailable').count() >= 3
            assert page.locator('.gospel-reading-play').count() == 0
            assert page.locator('.gospel-calendar').text_content() == calendar
            page.reload(); page.wait_for_selector('[data-gospel-status]',state='hidden')
            assert page.locator('[data-gospel-edition]').input_value() == 'npu'
            page.locator('[data-gospel-language]').select_option('ru')
            page.wait_for_selector('.gospel-reading-play')
            count = len(requests)
            page.locator('[data-gospel-narrator]').select_option('bondarenko')
            page.wait_for_selector('.gospel-unavailable')
            assert page.locator('.gospel-reading-play').count() > 0
            assert len(requests) == count
            context.close()
        browser.close()
    (output / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(results)} visual/playback cases + persistence, fixed calendar, partial/absent audio cases passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.base_url.rstrip('/'), args.output)
