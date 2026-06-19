import asyncio
import base64
import json
import re
import os
import csv
import aiohttp
from pathlib import Path
from playwright.async_api import async_playwright

class MedofastScraper:
    def __init__(self, logger_callback=None):
        self.logger = logger_callback
        self.is_paused = False
        self.is_stopped = False

        # Settings
        self.url = ""
        self.project_dir = Path("scrapes/default")
        self.skip_explanation = False
        self.save_screenshots = False
        self.save_html = False

        self.click_delay = 2.0
        self.question_load_delay = 3.0
        self.answer_load_delay = 2.0

        self.browser_context = None
        self.page = None
        self.playwright = None

        self.user_data_dir = Path("browser_session")
        self.json_path = None
        self.csv_path = None
        self.images_dir = None
        self.screenshots_dir = None
        self.html_dir = None

    def log(self, message):
        if self.logger: self.logger(message)
        else: print(message)

    async def check_pause_stop(self):
        while self.is_paused and not self.is_stopped:
            await asyncio.sleep(0.5)
        return self.is_stopped

    async def wait_for_question_load(self):
        try:
            await self.page.wait_for_selector("#questionSkeletonLoader", state="hidden", timeout=15000)
        except: pass
        await asyncio.sleep(self.question_load_delay)

    async def download_image(self, url):
        if not url: return None
        if url.startswith("/"): url = f"https://medofast.ir{url}"
        try:
            self.images_dir.mkdir(parents=True, exist_ok=True)
            filename = re.sub(r'[^\w\-_\. ]', '_', url.split("/")[-1])
            if not filename or len(filename) < 5: filename = f"img_{hash(url)}.png"
            filepath = self.images_dir / filename
            if filepath.exists(): return str(filepath)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(filepath, "wb") as f: f.write(content)
                        return str(filepath)
        except Exception as e:
            self.log(f"     ⚠️ Image download failed: {str(e)}")
        return url

    async def get_question_number_from_page(self):
        try:
            h6_text = await self.page.text_content("h6")
            if h6_text:
                m = re.search(r'سوال\s*(\d+)', h6_text)
                if m: return int(m.group(1))
        except: pass
        return None

    async def extract_current_question(self, question_number):
        result = {}
        async def get_text(selector):
            try:
                el = await self.page.query_selector(selector)
                if el: return (await el.inner_text()).strip()
            except: pass
            return ""

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
            if h6_text: meta["موقعیت سوال"] = h6_text.strip()
        except: pass
        result["metadata"] = {k: v for k, v in meta.items() if v}

        question_text = ""
        question_images = []
        try:
            q_elem = await self.page.query_selector("#qtxt")
            if q_elem:
                question_text = await q_elem.inner_text()
                for img in await q_elem.query_selector_all("img"):
                    src = await img.get_attribute("src")
                    if src:
                        local_path = await self.download_image(src)
                        question_images.append({"src": src, "local_path": local_path})
        except: pass
        if not question_text.strip():
            try:
                q_elem = await self.page.query_selector(".qtext-before")
                if q_elem: question_text = await q_elem.inner_text()
            except: pass

        result["question_text"] = question_text.strip()
        result["question_images"] = question_images

        options = []
        for i, opt_elem in enumerate(await self.page.query_selector_all(".encoded-option"), start=1):
            text = await opt_elem.inner_text()
            if not text.strip():
                encoded = await opt_elem.get_attribute("data-encoded-text")
                if encoded:
                    try: text = base64.b64decode(encoded).decode("utf-8")
                    except: text = encoded
            options.append({"number": i, "text": text.strip()})
        result["options"] = options

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
            if btn: await self.page.evaluate("btn => btn.click()", btn)
        except: pass
        await asyncio.sleep(self.click_delay)

        answer_text = ""
        explanation_images = []
        if self.skip_explanation:
            try:
                block = await self.page.query_selector("#block-b")
                if block and await block.is_visible(): answer_text = await block.inner_text()
            except: pass
        else:
            try:
                await self.page.wait_for_function(
                    "() => { const b = document.getElementById('block-b'); return b && b.innerText.trim().length > 3; }",
                    timeout=10000
                )
                block = await self.page.query_selector("#block-b")
                if block:
                    answer_text = await block.inner_text()
                    for img in await block.query_selector_all("img"):
                        src = await img.get_attribute("src")
                        if src:
                            local_path = await self.download_image(src)
                            explanation_images.append({"src": src, "local_path": local_path})
            except:
                for _ in range(3):
                    await asyncio.sleep(self.answer_load_delay)
                    try:
                        block = await self.page.query_selector("#block-b")
                        if block:
                            t = await block.inner_text()
                            if t.strip():
                                answer_text = t
                                break
                    except: pass

        correct_options = []
        if answer_text:
            norm_text = answer_text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
            patterns = [r'پاسخ صحیح[:\s]*گزینه\s*(\d)', r'تایید گزینه\s*(\d)', r'گزینه\s*(\d)\s*صحیح است', r'گزینه\s*(\d)']
            for p in patterns:
                matches = re.findall(p, norm_text)
                if matches:
                    correct_options.extend([int(m) for m in matches])
                    break
        try:
            visual = await self.page.evaluate("""() => {
                const results = [];
                for (let i = 1; i <= 4; i++) {
                    const label = document.getElementById('label' + i);
                    const bar = document.getElementById('prograssBar' + i);
                    const check = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const bg = style.backgroundColor;
                        const rgb = bg.match(/\\d+/g);
                        if (rgb && rgb.length >= 3) {
                            const r = parseInt(rgb[0]), g = parseInt(rgb[1]), b = parseInt(rgb[2]);
                            if (g > r + 30 && g > b + 30 && g > 100) return true;
                            if (b > r + 30 && b > g + 30 && b > 100) return true;
                        }
                        if (el.className.includes('success') || el.className.includes('correct') || el.className.includes('primary')) {
                             if (!el.className.includes('danger') && !el.className.includes('error')) return true;
                        }
                        if (el.querySelector('.fa-check, .fa-check-circle, .text-success, .text-primary, .tick')) return true;
                        return false;
                    };
                    if (check(label) || check(bar)) results.push(i);
                }
                return results;
            }""")
            if visual: correct_options.extend(visual)
        except: pass
        correct_options = sorted(list(set(correct_options)))

        if self.save_screenshots:
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = self.screenshots_dir / f"question_{question_number}.png"
            await self.page.screenshot(path=str(path), full_page=True)
            result["screenshot_path"] = str(path)
        if self.save_html:
            self.html_dir.mkdir(parents=True, exist_ok=True)
            path = self.html_dir / f"question_{question_number}.html"
            content = await self.page.content()
            with open(path, "w", encoding="utf-8") as f: f.write(content)
            result["html_path"] = str(path)

        result["correct_options"] = correct_options
        result["answer_explanation"] = answer_text.strip()
        result["explanation_images"] = explanation_images
        result["question_number"] = question_number
        return result

    async def go_to_next(self, current_number, logged_in_mode):
        next_btn = await self.page.query_selector("button[data-nav-role='next']")
        if not next_btn: return False
        cls = await next_btn.get_attribute("class") or ""
        if "turned-off" in cls: return False
        self.log(f"     Moving to next...")
        await asyncio.sleep(self.click_delay)
        try:
            if logged_in_mode:
                onclick = await next_btn.get_attribute("onclick") or ""
                url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
                if url_match:
                    full_url = f"https://medofast.ir{url_match.group(1)}" if url_match.group(1).startswith("/") else url_match.group(1)
                    await self.page.goto(full_url, wait_until="networkidle", timeout=30000)
                else: await next_btn.click(force=True)
            else: await next_btn.click(force=True)
        except: await self.page.evaluate("btn => btn.click()", next_btn)
        await self.wait_for_question_load()
        try:
            await self.page.wait_for_function(
                "(old) => { const h = document.querySelector('h6'); return h && h.innerText.includes('سوال') && parseInt(h.innerText.match(/\\d+/)[0]) !== old; }",
                current_number, timeout=10000
            )
        except: pass
        new_number = await self.get_question_number_from_page()
        return new_number is not None and new_number != current_number

    def save_data_concurrently(self, data_list, new_item):
        data_list.append(new_item)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        file_exists = self.csv_path.exists()
        with open(self.csv_path, 'a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Question Number", "Exam", "Date", "Lesson", "Subject", "Difficulty", "Success Rate", "Position", "Question Text", "Option 1", "Option 2", "Option 3", "Option 4", "Correct Options", "Explanation"])
            meta, opts = new_item.get("metadata", {}), new_item.get("options", [])
            opt_texts = ["", "", "", ""]
            for o in opts:
                idx = o.get("number", 1) - 1
                if 0 <= idx < 4: opt_texts[idx] = o.get("text", "")
            writer.writerow([new_item.get("question_number", ""), meta.get("آزمون", ""), meta.get("تاریخ", ""), meta.get("درس", ""), meta.get("موضوع", ""), meta.get("سطح دشواری", ""), meta.get("درصد پاسخ صحیح", ""), meta.get("موقعیت سوال", ""), new_item.get("question_text", ""), opt_texts[0], opt_texts[1], opt_texts[2], opt_texts[3], ", ".join(map(str, new_item.get("correct_options", []))), new_item.get("answer_explanation", "")])

    async def run(self, login_confirmed_event):
        self.playwright = await async_playwright().start()
        try:
            self.browser_context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir), headless=False, viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            self.page = self.browser_context.pages[0] if self.browser_context.pages else await self.browser_context.new_page()
            self.log("🌐 Session active. Checking login status...")
            await self.page.goto("https://medofast.ir/login", wait_until="networkidle")
            is_logged_in = await self.page.evaluate("() => document.body.getAttribute('data-user-authenticated') === 'true'")
            if not is_logged_in:
                self.log("⏳ Manual login required. Click 'Confirm Login' when ready.")
                while not login_confirmed_event.is_set():
                    if await self.check_pause_stop(): return
                    try: await asyncio.wait_for(login_confirmed_event.wait(), timeout=1.0)
                    except asyncio.TimeoutError: pass
            else: self.log("✅ Already logged in via session.")

            self.log("🌐 Navigating to URL...")
            await self.page.goto(self.url, wait_until="networkidle")
            await self.wait_for_question_load()
            logged_in_mode = await self.page.evaluate("() => document.body.getAttribute('data-user-authenticated') === 'true'")
            total_questions = None
            try:
                h6 = await self.page.text_content("h6")
                if h6: total_questions = int(re.search(r'از\s*(\d+)', h6).group(1))
            except: pass

            all_questions = []
            if self.json_path.exists():
                try:
                    with open(self.json_path, 'r', encoding='utf-8') as f: all_questions = json.load(f)
                    self.log(f"📋 Loaded {len(all_questions)} existing questions.")
                except: pass

            question_number = await self.get_question_number_from_page() or 1
            scraped_numbers = [q.get("question_number") for q in all_questions]
            while question_number in scraped_numbers:
                self.log(f"⏩ Question {question_number} already scraped. Skipping...")
                if not await self.go_to_next(question_number, logged_in_mode): break
                question_number = await self.get_question_number_from_page()

            while not self.is_stopped:
                if await self.check_pause_stop(): break
                self.log(f"  ⏳ Scraping Question {question_number}...")
                data = await self.extract_current_question(question_number)
                self.save_data_concurrently(all_questions, data)
                if total_questions and question_number >= total_questions:
                    self.log("✅ Reached last question.")
                    break
                if not await self.go_to_next(question_number, logged_in_mode):
                    await asyncio.sleep(4)
                    if not await self.go_to_next(question_number, logged_in_mode):
                        self.log("✅ End reached.")
                        break
                question_number = await self.get_question_number_from_page() or (question_number + 1)
        finally:
            if self.browser_context: await self.browser_context.close()
            if self.playwright: await self.playwright.stop()
            self.log("Scraper finished.")

    def pause(self): self.is_paused = True
    def resume(self): self.is_paused = False
    def stop(self):
        self.is_stopped = True
        self.resume()
