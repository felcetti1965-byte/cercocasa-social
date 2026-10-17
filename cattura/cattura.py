import asyncio, base64, json, os, re, time, pathlib
from playwright.async_api import async_playwright
OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
B = "https://www.cercocasaumbria.it"
log = []
def L(*a):
    s=" ".join(map(str,a)); print(s, flush=True); log.append(s)

async def warm(page):
    h = await page.evaluate("document.documentElement.scrollHeight")
    y=0
    while y < h:
        await page.evaluate(f"window.scrollTo(0,{y})"); await page.wait_for_timeout(250); y+=500
        h = await page.evaluate("document.documentElement.scrollHeight")
    await page.wait_for_timeout(1500); await page.evaluate("window.scrollTo(0,0)"); await page.wait_for_timeout(800)

async def kill_banners(page):
    for sel in ["text=Accetta", "text=Accetto", "text=Accetta tutti", "button:has-text('OK')", "text=Rifiuta"]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=500): await el.click(timeout=1500); await page.wait_for_timeout(500)
        except Exception: pass

class Cast:
    def __init__(s, page, name): s.page=page; s.name=name; s.n=0; s.meta=[]
    async def start(s):
        s.cdp = await s.page.context.new_cdp_session(s.page)
        d = OUT/ s.name; d.mkdir(exist_ok=True)
        async def on(ev):
            s.n+=1; f=d/f"{s.n:05d}.jpg"; f.write_bytes(base64.b64decode(ev["data"]))
            s.meta.append([f.name, ev["metadata"]["timestamp"]])
            try: await s.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception: pass
        s.cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(on(ev)))
        await s.cdp.send("Page.startScreencast", {"format":"jpeg","quality":92,"everyNthFrame":1})
    async def stop(s):
        await s.cdp.send("Page.stopScreencast"); await asyncio.sleep(0.5)
        (OUT/s.name/"meta.json").write_text(json.dumps(s.meta)); L("cast", s.name, s.n, "frames")

async def smooth_scroll(page, total, dur_ms):
    await page.evaluate("""([total,dur])=>new Promise(r=>{const y0=scrollY,t0=performance.now();
      const e=t=>t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
      (function f(){const k=Math.min(1,(performance.now()-t0)/dur);scrollTo(0,y0+total*e(k));k<1?requestAnimationFrame(f):r()})()})""", [total, dur_ms])

async def shoot(ctx, tag, path, full=True, cast_scroll=None, wait=3000):
    page = await ctx.new_page()
    try:
        await page.goto(B+path, wait_until="networkidle", timeout=60000)
    except Exception as e: L("goto warn", path, e)
    await page.wait_for_timeout(wait); await kill_banners(page); await warm(page)
    await page.wait_for_timeout(1500)
    if full:
        await page.screenshot(path=str(OUT/f"{tag}_full.png"), full_page=True)
    await page.screenshot(path=str(OUT/f"{tag}_top.png"))
    if cast_scroll:
        c=Cast(page, tag+"_cast"); await c.start(); await page.wait_for_timeout(800)
        h = await page.evaluate("document.documentElement.scrollHeight-innerHeight")
        await smooth_scroll(page, min(h, cast_scroll[0]), cast_scroll[1]); await page.wait_for_timeout(800)
        await c.stop()
    await page.close()

async def rivista(ctx, tag, ed):
    page = await ctx.new_page()
    await page.goto(B+"/rivista.php?edizione="+ed, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(5000); await kill_banners(page)
    await page.screenshot(path=str(OUT/f"{tag}_0.png"))
    fr = None
    for f in page.frames:
        if "rivista-demo" in f.url: fr=f
    if fr:
        try: (OUT/f"{tag}_iframe.html").write_text(await fr.content())
        except Exception as e: L("iframe html", e)
    c=Cast(page, tag+"_cast"); await c.start(); await page.wait_for_timeout(1500)
    vw = page.viewport_size["width"]; vh = page.viewport_size["height"]
    for i in range(7):
        await page.keyboard.press("ArrowRight"); await page.wait_for_timeout(1800)
        await page.screenshot(path=str(OUT/f"{tag}_k{i+1}.png"))
    for i in range(3):
        await page.mouse.click(int(vw*0.9), int(vh*0.5)); await page.wait_for_timeout(1800)
        await page.screenshot(path=str(OUT/f"{tag}_c{i+1}.png"))
    await c.stop(); await page.close()

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for mode, vp, dpr, mob in [("m", {"width":540,"height":540}, 2, True), ("d", {"width":1080,"height":1080}, 1, False)]:
            ctx = await br.new_context(viewport=vp, device_scale_factor=dpr, is_mobile=mob, has_touch=mob, locale="it-IT")
            await shoot(ctx, mode+"_home", "/", cast_scroll=(6000, 9000))
            for ed,t in [("Perugia","per"),("Terni","ter"),("Vetrina%20Umbria","vet")]:
                try: await rivista(ctx, f"{mode}_riv_{t}", ed)
                except Exception as e: L("rivista err", ed, e)
            for pid in ["2164","3995"]:
                await shoot(ctx, f"{mode}_imm{pid}", f"/immobile.php?id={pid}", cast_scroll=(9000, 12000), wait=6000)
            await shoot(ctx, mode+"_mutuo", "/mutuo.php", cast_scroll=(2500, 5000))
            await shoot(ctx, mode+"_mappa", "/mappa-ricerca.php?operation=vendita", cast_scroll=(4000, 7000), wait=6000)
            await shoot(ctx, mode+"_valuta", "/valuta-casa.php", cast_scroll=(2500, 5000))
            await shoot(ctx, mode+"_vendi", "/vendi-con-agenzia.php?source=portale", cast_scroll=(2500, 5000))
            await ctx.close()
        await br.close()
    (OUT/"log.txt").write_text("\n".join(log))
asyncio.run(main())
