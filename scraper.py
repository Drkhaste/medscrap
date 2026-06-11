import asyncio
import base64
import json
import re
import os
import aiohttp
from pathlib import Path
from playwright.async_api import async_playwright

class MedofastScraper:
    def __init__(self, logger_callback=None):
        self.logger = logger_callback
        self.is_paused = False
        self.is_stopped = False
        self.pause_event = asyncio.Event()
        self.pause_event.set()

        # Settings
        self.url = ""
        self.output_path = "questions.json"
        self.click_delay = 2.0
        self.question_load_delay = 3.0
        self.answer_load_delay = 2.0
        self.skip_explanation = False

        self.browser = None
        self.context = None
        self.page = None
        self.image_dir = Path("downloaded_images")
        self.debug_dir = Path("debug_screenshots")

    def log(self, message):
        if self.logger:
            self.logger(message)
        else:
            print(message)

    async def check_pause(self):
        await self.pause_event.wait()

    async def wait_for_question_load(self):
        try:
            await self.page.wait_for_selector("#questionSkeletonLoader", state="hidden", timeout=15000)
        except:
            pass
        await asyncio.sleep(self.question_load_delay)

    async def download_image(self, url):
        if not url: return None
        if url.startswith("/"):
            url = f"https://medofast.ir{url}"

        try:
            self.image_dir.mkdir(exist_ok=True)
            filename = re.sub(r'[^\w\-_\. ]', '_', url.split("/")[-1])
            if not filename or len(filename) < 5:
                filename = f"img_{hash(url)}.png"

            filepath = self.image_dir / filename
            if filepath.exists():
                return str(filepath)

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(filepath, "wb") as f:
                            f.write(content)
                        return str(filepath)
        except Exception as e:
            self.log(f"     ⚠️ Image download failed ({url}): {str(e)}")
        return url

    async def get_question_number_from_page(self):
        try:
            h6_text = await self.page.text_content("h6")
            if h6_text:
                m = re.search(r'سوال\s*(\d+)', h6_text)
                if m:
                    return int(m.group(1))
        except:
            pass
        return None

    async def extract_current_question(self, question_number):
        result = {}

        async def get_text(selector):
            try:
                el = await self.page.query_selector(selector)
                if el:
                    return (await el.inner_text()).strip()
            except:
                pass
            return ""

        # Metadata
        meta = {}
        meta["آزمون"] = await get_text("li:has(i.fa-books)")
        meta["تاریخ"] = await get_text("li:has(i.fa-calendar-check)")
        meta["درس"] = await get_text("li:has(i.fa-syringe)")
        meta["موضوع"] = await get_text("li:has(i.fa-hashtag)")

        diff_raw = await get_text("li:has(i.fa-fire-alt)")
        meta["سطح دشواری"] = re.sub(r'^سطح دشواری سوال[:\s]*', '', diff_raw).strip()

        stats_raw = await get_text("li:has(i.fa-chart-bar)")
        pct = re.search(r'(\d+)%', stats_raw)
        meta["درصد پاسخ صحیح"] = pct.group(1) + "%" if pct else ""

        try:
            h6_text = await self.page.text_content("h6")
            if h6_text:
                meta["موقعیت سوال"] = h6_text.strip()
        except:
            pass

        result["metadata"] = {k: v for k, v in meta.items() if v}

        # Question text + images
        question_text = ""
        question_images = []
        try:
            q_elem = await self.page.query_selector("#qtxt")
            if q_elem:
                question_text = await q_elem.inner_text()
                for img in await q_elem.query_selector_all("img"):
                    src = await img.get_attribute("src")
                    alt = await img.get_attribute("alt") or ""
                    if src:
                        local_path = await self.download_image(src)
                        question_images.append({"src": src, "alt": alt, "local_path": local_path})
        except:
            pass

        if not question_text.strip():
            try:
                q_elem = await self.page.query_selector(".qtext-before")
                if q_elem:
                    question_text = await q_elem.inner_text()
            except:
                pass

        result["question_text"] = question_text.strip()
        result["question_images"] = question_images

        # Options
        options = []
        for i, opt_elem in enumerate(await self.page.query_selector_all(".encoded-option"), start=1):
            text = await opt_elem.inner_text()
            if not text.strip():
                encoded = await opt_elem.get_attribute("data-encoded-text")
                if encoded:
                    try:
                        text = base64.b64decode(encoded).decode("utf-8")
                    except:
                        text = encoded
            options.append({"number": i, "text": text.strip()})

        if not any(o["text"] for o in options):
            try:
                encoded_attrs = await self.page.eval_on_selector_all(
                    ".encoded-option",
                    "els => els.map(e => e.getAttribute('data-encoded-text'))"
                )
                options = []
                for i, enc in enumerate(encoded_attrs, start=1):
                    text = ""
                    if enc:
                        try:
                            text = base64.b64decode(enc).decode("utf-8")
                        except:
                            text = enc
                    options.append({"number": i, "text": text})
            except:
                pass

        result["options"] = options

        # ── Submit answer ──
        self.log("     Submitting answer...")
        try:
            await self.page.evaluate("""() => {
                const radios = document.querySelectorAll('input[type="radio"]');
                radios.forEach(r => {
                    let p = r.closest('[inert]');
                    if (p) p.removeAttribute('inert');
                    r.disabled = false;
                });
                const r1 = document.querySelector('input[type="radio"][value="1"]');
                if (r1) r1.click();
            }""")
            await asyncio.sleep(self.click_delay)

            btn = await self.page.query_selector("#show-b-btn")
            if btn:
                await self.page.evaluate("btn => btn.click()", btn)
        except Exception as e:
            self.log(f"     ⚠️ Submit failed: {str(e)}")

        await asyncio.sleep(self.click_delay)

        # Handle explanatory answers
        answer_text = ""
        explanation_images = []

        if self.skip_explanation:
            self.log("     Skipping explanation wait.")
            # Quick check if it already appeared
            try:
                block = await self.page.query_selector("#block-b")
                if block and await block.is_visible():
                    answer_text = await block.inner_text()
            except: pass
        else:
            self.log("     Waiting for explanation...")
            try:
                await self.page.wait_for_function(
                    """() => {
                        const block = document.getElementById('block-b');
                        if (!block) return false;
                        const text = block.innerText || '';
                        return text.trim().length > 3;
                    }""",
                    timeout=10000
                )
                block = await self.page.query_selector("#block-b")
                if block:
                    answer_text = await block.inner_text()
                    # Also extract images from explanation
                    for img in await block.query_selector_all("img"):
                        src = await img.get_attribute("src")
                        alt = await img.get_attribute("alt") or ""
                        if src:
                            local_path = await self.download_image(src)
                            explanation_images.append({"src": src, "alt": alt, "local_path": local_path})
            except:
                for _ in range(5):
                    await asyncio.sleep(self.answer_load_delay)
                    try:
                        block = await self.page.query_selector("#block-b")
                        if block:
                            t = await block.inner_text()
                            if t.strip():
                                answer_text = t
                                break
                    except:
                        pass

        # ── Identify correct options (Exhaustive Search) ──
        correct_options = []

        # Method 1: Text-based (Arabic/Persian digits support)
        if answer_text:
            norm_text = answer_text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
            patterns = [
                r'پاسخ صحیح[:\s]*گزینه\s*(\d)',
                r'تایید گزینه\s*(\d)',
                r'گزینه\s*(\d)\s*صحیح است',
                r'گزینه\s*(\d)'
            ]
            for p in patterns:
                matches = re.findall(p, norm_text)
                if matches:
                    correct_options.extend([int(m) for m in matches])

        # Method 2: Comprehensive Visual DOM Inspection (Green and Blue)
        try:
            visual_results = await self.page.evaluate("""() => {
                const results = [];
                for (let i = 1; i <= 4; i++) {
                    const label = document.getElementById('label' + i);
                    const bar = document.getElementById('prograssBar' + i);

                    const checkElement = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const bg = style.backgroundColor;
                        const rgb = bg.match(/\\d+/g);
                        if (rgb && rgb.length >= 3) {
                            const r = parseInt(rgb[0]), g = parseInt(rgb[1]), b = parseInt(rgb[2]);

                            // Detect Green: G is dominant
                            if (g > r + 30 && g > b + 30 && g > 100) return true;

                            // Detect Blue (Medofast uses blue for correct answer in some views)
                            // Blue: B is dominant
                            if (b > r + 30 && b > g + 30 && b > 100) return true;
                        }

                        if (el.className.includes('success') || el.className.includes('correct') || el.className.includes('primary')) {
                             // But not 'danger' or 'error'
                             if (!el.className.includes('danger') && !el.className.includes('error')) return true;
                        }

                        if (el.querySelector('.fa-check, .fa-check-circle, .text-success, .text-primary, .tick')) return true;

                        return false;
                    };

                    if (checkElement(label) || checkElement(bar)) {
                        results.push(i);
                    }
                }
                return results;
            }""")
            if visual_results:
                correct_options.extend(visual_results)
        except Exception as e:
            self.log(f"     ⚠️ Visual inspection failed: {str(e)}")

        # Final De-duplicate and sort
        correct_options = sorted(list(set(correct_options)))

        # ── Debugging/Fallback if still failed ──
        if not correct_options:
            self.log(f"     ⚠️ No answer detected. Trying final fallback...")
            try:
                any_correct = await self.page.evaluate("""() => {
                    const found = [];
                    // Look for progress bars that are NOT red
                    for (let i = 1; i <= 4; i++) {
                        const bar = document.getElementById('prograssBar' + i);
                        if (bar) {
                            const bg = window.getComputedStyle(bar).backgroundColor;
                            const rgb = bg.match(/\\d+/g);
                            if (rgb && rgb.length >= 3) {
                                const r = parseInt(rgb[0]), g = parseInt(rgb[1]), b = parseInt(rgb[2]);
                                // If it's more blue or green than red, it might be the one
                                if ((b > r || g > r) && (b > 100 || g > 100)) found.push(i);
                            }
                        }
                    }
                    return found;
                }""")
                if any_correct:
                    correct_options = sorted(list(set(any_correct)))
            except:
                pass

        if not correct_options:
            self.log(f"     ❌ Still no correct option detected. Screenshot saved.")
            self.debug_dir.mkdir(exist_ok=True)
            await self.page.screenshot(path=str(self.debug_dir / f"fail_q{question_number}.png"))

        result["correct_options"] = correct_options
        result["answer_explanation"] = answer_text.strip() if not self.skip_explanation else ""
        result["explanation_images"] = explanation_images
        result["question_number"] = question_number

        return result

    async def go_to_next(self, current_number, logged_in_mode):
        next_btn = await self.page.query_selector("button[data-nav-role='next']")
        if not next_btn:
            return False

        cls = await next_btn.get_attribute("class") or ""
        if "turned-off" in cls:
            return False

        self.log(f"     Moving to next...")
        await asyncio.sleep(self.click_delay)

        try:
            if logged_in_mode:
                onclick = await next_btn.get_attribute("onclick") or ""
                url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
                if url_match:
                    nav_url = url_match.group(1)
                    full_url = f"https://medofast.ir{nav_url}" if nav_url.startswith("/") else nav_url
                    await self.page.goto(full_url, wait_until="networkidle", timeout=30000)
                else:
                    await next_btn.click(force=True)
            else:
                await next_btn.click(force=True)
        except:
            await self.page.evaluate("btn => btn.click()", next_btn)

        await self.wait_for_question_load()

        try:
            await self.page.wait_for_function(
                """(oldNum) => {
                    const h6 = document.querySelector('h6');
                    if (!h6) return false;
                    const text = h6.innerText || '';
                    const m = text.match(/سوال\\s*(\\d+)/);
                    return m && parseInt(m[1]) !== oldNum;
                }""",
                current_number,
                timeout=12000
            )
        except:
            pass

        new_number = await self.get_question_number_from_page()
        if new_number is not None and new_number == current_number:
            self.log(f"     ⚠️ Still on {current_number}. Navigation failed.")
            return False

        return True

    async def run(self, login_confirmed_event):
        async with async_playwright() as p:
            self.browser = await p.chromium.launch(headless=False)
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            self.page = await self.context.new_page()

            self.log("🌐 Opening login page...")
            await self.page.goto("https://medofast.ir/login", wait_until="networkidle", timeout=30000)

            self.log(f"⏳ Waiting for login confirmation...")
            while not login_confirmed_event.is_set():
                if self.is_stopped:
                    await self.browser.close()
                    return
                try:
                    await asyncio.wait_for(login_confirmed_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass

            self.log("🌐 Navigating to URL...")
            await self.page.goto(self.url, wait_until="networkidle", timeout=30000)
            await self.wait_for_question_load()

            logged_in_mode = await self.page.evaluate(
                "() => document.body.getAttribute('data-user-authenticated') === 'true'"
            )

            total_questions = None
            try:
                h6_text = await self.page.text_content("h6")
                if h6_text:
                    m = re.search(r'از\s*(\d+)', h6_text)
                    if m:
                        total_questions = int(m.group(1))
            except:
                pass

            if total_questions:
                self.log(f"📊 Total: {total_questions}")

            all_questions = []
            consecutive_failures = 0
            question_number = await self.get_question_number_from_page() or 1

            while not self.is_stopped:
                await self.check_pause()

                self.log(f"  ⏳ Question {question_number}...")

                data = await self.extract_current_question(question_number)
                corrects = data.get("correct_options", [])
                self.log(f"     Correct Options: {corrects if corrects else '⚠️ Not Found'}")
                all_questions.append(data)

                with open(self.output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_questions, f, ensure_ascii=False, indent=2)

                if total_questions and question_number >= total_questions:
                    self.log("✅ Reached last question.")
                    break

                await self.check_pause()
                success = await self.go_to_next(question_number, logged_in_mode)
                if not success:
                    await asyncio.sleep(4)
                    success = await self.go_to_next(question_number, logged_in_mode)

                if not success:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        self.log(f"✅ Finished - Navigation failed.")
                        break
                else:
                    consecutive_failures = 0
                    new_num = await self.get_question_number_from_page()
                    if new_num:
                        question_number = new_num
                    else:
                        question_number += 1

            await self.browser.close()
            self.log(f"\n✅ Done: {len(all_questions)} questions.")

    def pause(self):
        self.is_paused = True
        self.pause_event.clear()

    def resume(self):
        self.is_paused = False
        self.pause_event.set()

    def stop(self):
        self.is_stopped = True
        self.resume()
