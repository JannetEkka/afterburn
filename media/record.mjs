import { chromium } from 'playwright';
import { execFileSync, spawn } from 'child_process';
import fs from 'fs';
const AUDIO = '/home/user/afterburn/media/audio';
const dur = fs.readdirSync(AUDIO).filter(f => /^scene\d+\.mp3$/.test(f)).sort().map(f =>
  1000 * parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', `${AUDIO}/${f}`]).toString()));
const W = 1440, H = 810, BASE = 'http://localhost:8766';
// A real Chromium window on a virtual 1920x1080 display, recorded by ffmpeg at near-lossless quality.
// The 4/3 device scale keeps the page laid out at 1440x810 CSS px, as in the earlier cut.
const DISPLAY = process.env.DISPLAY || ':99';
// a persistent context reuses the launch window, so kiosk mode holds and no browser UI takes space
fs.rmSync('profile', { recursive: true, force: true });
const ctx = await chromium.launchPersistentContext(`${process.cwd()}/profile`, {
  executablePath: '/opt/pw-browsers/chromium', headless: false, viewport: null,
  args: ['--kiosk', '--window-position=0,0', '--window-size=1440,810', '--force-device-scale-factor=1.3333333', '--hide-scrollbars'],
  ignoreDefaultArgs: ['--enable-automation'], env: { ...process.env, DISPLAY },
});
const page = ctx.pages()[0] || await ctx.newPage();
const wait = ms => page.waitForTimeout(ms);
const scrollTo = sel => page.evaluate(s => { const el = document.querySelector(s); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 56, behavior: 'smooth' }); }, sel);
// set a map layer on or off by its legend checkbox (idempotent, so a missed or doubled click can't flip it the wrong way)
const layer = (i, on) => page.evaluate(([i, on]) => { const el = document.querySelectorAll('.legend-row input')[i]; if (el.checked !== on) el.click(); }, [i, on]);
async function scene(i, fn) { const t = Date.now(); await fn(); const left = dur[i] - (Date.now() - t); if (left > 0) await wait(left); }

await page.goto(`${BASE}/docs/`, { waitUntil: 'networkidle' });
console.log('css viewport', await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio]));
await wait(2500);  // tiles and chain reads
fs.mkdirSync('x11', { recursive: true });
const grab = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '30', '-video_size', '1920x1080', '-i', `${DISPLAY}.0+0,0`,
  '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '10', '-pix_fmt', 'yuv444p', 'x11/raw.mkv'], { stdio: ['pipe', 'inherit', 'inherit'] });
const t0 = Date.now();
await wait(1500);  // let ffmpeg start; this lead-in is trimmed
const start = Date.now();
// 1 hero
await scene(0, async () => {});
// 2 the timing finding: bring the stat cards into focus
await scene(1, async () => { await page.evaluate(() => window.scrollTo({ top: 120, behavior: 'smooth' })); });
// 3 the map
await scene(2, async () => { await scrollTo('#map'); });
// 4 zoom into the densest burning, scars off, then on
await scene(3, async () => { await page.evaluate(() => { map.flyTo([31.5, 75.2], 13, { duration: 2.5 }); }); await wait(5000); await layer(0, false); await wait(5500); await layer(0, true); });
// 5 flames: hide scars and VIIRS for a moment to show the fires Sentinel-2 caught burning
await scene(4, async () => { await page.evaluate(() => { map.flyTo(map.getCenter(), 12, { duration: 1 }); }); await wait(2200); await layer(0, false); await layer(1, false); await wait(9000); await layer(0, true); await layer(1, true); });
// 6 how the rule works + validation
await scene(5, async () => { await page.evaluate(() => { map.flyToBounds(state.layers.overlay_bounds, { duration: 1 }); }); await scrollTo('#how'); await wait(16000); await page.evaluate(() => window.scrollBy({ top: 330, behavior: 'smooth' })); });
// 7 the pact
await scene(6, async () => { await scrollTo('#pact'); await wait(13000); await page.evaluate(() => window.scrollBy({ top: 260, behavior: 'smooth' })); });
// 8 plot 19
await scene(7, async () => { await scrollTo('#map'); await wait(800); await page.evaluate(() => { openPlot(19); }); await wait(15000); await page.evaluate(() => document.getElementById('panel').scrollTo({ top: 420, behavior: 'smooth' })); });
// 9 recheck in the terminal
await scene(8, async () => { await page.goto(`${BASE}/media/terminal.html`, { waitUntil: 'domcontentloaded' }); });
// 10 the season on-chain
await scene(9, async () => { await page.goto(`${BASE}/docs/#pact`, { waitUntil: 'domcontentloaded' }); await wait(1500); await scrollTo('#pact'); await wait(1500); await page.evaluate(() => document.getElementById('timeline').scrollIntoView({ behavior: 'smooth', block: 'center' })); });
// 11 villages and the farmer's notice
await scene(10, async () => {
  await page.evaluate(() => document.getElementById('villages').scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await wait(6000); await scrollTo('#map'); await wait(800); await page.evaluate(() => { openPlot(1); }); await wait(1500);
  await page.evaluate(() => document.getElementById('panel').scrollTo({ top: 900, behavior: 'smooth' })); await wait(5000);
  await page.locator('.notice .tabs button').nth(1).click();
});
// 12 limits and close
await scene(11, async () => { await page.evaluate(() => { closePlot(); }); await page.evaluate(() => document.querySelector('.limits').scrollIntoView({ behavior: 'smooth', block: 'center' })); await wait(11000); await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); });
await wait(1500);
fs.writeFileSync('x11/offset.txt', String((start - t0) / 1000));
grab.stdin.write('q');
await new Promise((r) => grab.on('close', r));
console.log('recorded x11/raw.mkv; lead-in', (start - t0) / 1000, 's; narration', (dur.reduce((a, b) => a + b, 0) / 1000).toFixed(1), 's');
await ctx.close();
