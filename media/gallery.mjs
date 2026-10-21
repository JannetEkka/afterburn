import { chromium } from 'playwright';
const OUT = '/home/user/afterburn/media/gallery';
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 1.2 });
const wait = (ms) => page.waitForTimeout(ms);
const top = (sel, off = 56) => page.evaluate(([s, o]) => { const el = document.querySelector(s); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - o }); }, [sel, off]);
const layer = (i, on) => page.evaluate(([i, on]) => { const el = document.querySelectorAll('.legend-row input')[i]; if (el.checked !== on) el.click(); }, [i, on]);
await page.goto('http://localhost:8766/docs/', { waitUntil: 'networkidle' });
await wait(2500);
await page.screenshot({ path: `${OUT}/1-hero.png` });
// the map, zoomed into the densest burning: scars on, then what the official count alone shows
await top('#map', 0);
await page.evaluate(() => { map.setView([31.5, 75.2], 13); });
await wait(4000);
await page.screenshot({ path: `${OUT}/2-scars.png` });
await layer(0, false);
await wait(1500);
await page.screenshot({ path: `${OUT}/3-official-count-only.png` });
await layer(0, true);
// plot 19
await page.evaluate(() => { openPlot(19); });
await wait(4000);
await page.screenshot({ path: `${OUT}/4-plot-19.png` });
await page.evaluate(() => { closePlot(); });
// the pact
await top('#pact', 0);
await wait(1500);
await page.screenshot({ path: `${OUT}/5-pact-on-chain.png` });
// recheck
await page.goto('http://localhost:8766/media/terminal.html', { waitUntil: 'networkidle' });
await wait(14000);
await page.screenshot({ path: `${OUT}/6-recheck.png` });
await browser.close();
console.log('done');
