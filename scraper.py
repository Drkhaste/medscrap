import asyncio
import base64
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

class MedofastScraper:
    def __init__(self, logger_callback=None):
        self.logger = logger_callback
        self.is_paused = False
        self.is_stopped = False
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Start in unpaused state

        # Settings
        self.url = ""
        self.output_path = "questions.json"
        self.click_delay = 1.0
        self.question_load_delay = 2.0
        self.answer_load_delay = 1.0
        self.skip_explanation = False
        self.login_wait = 60

        self.browser = None
        self.context = None
        self.page = None

    def log(self, message):
        if self.logger:
            self.logger(message)
        else:
            print(message)

    async def check_pause(self):
        await self.pause_event.wait()

    async def wait_for_question_load(self):
        try:
            # Wait for the loader to disappear
            await self.page.wait_for_selector("#questionSkeletonLoader", state="hidden", timeout=10000)
        except:
            pass
        # Additional wait for AJAX content to settle
        await asyncio.sleep(self.question_load_delay)

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
                        question_images.append({"src": src, "alt": alt})
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

        # ── Identify correct option BEFORE clicking (if possible) ──
        # Sometimes it's already there in progress bars or other elements
        correct_option = None

        # ── Click option 1 and Confirm ──
        self.log("     Submitting answer to reveal correct option...")
        try:
            await self.page.eval_on_selector(
                'input[type="radio"][value="1"]',
                "el => { let p = el.closest('[inert]'); if(p) p.removeAttribute('inert'); }"
            )
            radio = await self.page.query_selector('input[type="radio"][value="1"]')
            if radio:
                await radio.click(force=True)
            await asyncio.sleep(self.click_delay)

            btn = await self.page.query_selector("#show-b-btn")
            if btn:
                await self.page.evaluate("btn => btn.click()", btn)
        except:
            pass

        await asyncio.sleep(self.click_delay)

        # Handle explanatory answers
        answer_text = ""

        if self.skip_explanation:
            self.log("     Skipping explanatory answer.")
        else:
            self.log("     Waiting for explanatory answer...")
            try:
                # Wait for block-b to appear and have content
                await self.page.wait_for_function(
                    """() => {
                        const block = document.getElementById('block-b');
                        if (!block) return false;
                        const text = block.innerText || '';
                        return text.trim().length > 10;
                    }""",
                    timeout=8000
                )
                block = await self.page.query_selector("#block-b")
                if block:
                    answer_text = await block.inner_text()
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

        # ── Identify correct option (Post-click) ──

        # Method 1: From answer text
        if answer_text:
            m = re.search(r'تایید گزینه\s*(\d)', answer_text)
            if m:
                correct_option = int(m.group(1))

        # Method 2: Check labels for success/correct classes or colors
        if not correct_option:
            try:
                for i in range(1, 5):
                    label = await self.page.query_selector(f"#label{i}")
                    if label:
                        cls = await label.get_attribute("class") or ""
                        style = await label.get_attribute("style") or ""
                        bg = await self.page.evaluate(
                            f"(id) => window.getComputedStyle(document.getElementById(id)).backgroundColor",
                            f"label{i}"
                        )
                        # Look for green colors (rgb(34, ...), etc.) or success classes
                        if ("success" in cls or "correct" in cls or
                                "green" in style.lower() or
                                "34" in bg or "40, 167, 69" in bg):
                            correct_option = i
                            break
            except:
                pass

        # Method 3: From progress bars
        if not correct_option:
            try:
                for i in range(1, 5):
                    bar = await self.page.query_selector(f"#prograssBar{i}")
                    if bar:
                        cls = await bar.get_attribute("class") or ""
                        if "bg-success" in cls:
                            correct_option = i
                            break
            except:
                pass

        # Method 4: Highest percentage (as fallback)
        if not correct_option:
            try:
                max_pct = -1
                for i in range(1, 5):
                    bar = await self.page.query_selector(f"#prograssBar{i}")
                    if bar:
                        enc = await bar.get_attribute("data-encoded-percent")
                        if enc:
                            try:
                                pct_val = int(base64.b64decode(enc).decode())
                                if pct_val > max_pct:
                                    max_pct = pct_val
                                    if pct_val > 50:
                                        correct_option = i
                            except:
                                pass
            except:
                pass

        result["correct_option"] = correct_option
        result["answer_explanation"] = answer_text.strip() if not self.skip_explanation else ""
        result["question_number"] = question_number

        return result

    async def go_to_next(self, current_number, logged_in_mode):
        next_btn = await self.page.query_selector("button[data-nav-role='next']")
        if not next_btn:
            self.log("     ⚠️ Next button not found.")
            return False

        cls = await next_btn.get_attribute("class") or ""
        if "turned-off" in cls:
            self.log("     🏁 Reached the end (Next button turned off).")
            return False

        self.log("     Navigating to next question...")

        if logged_in_mode:
            onclick = await next_btn.get_attribute("onclick") or ""
            url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
            if url_match:
                nav_url = url_match.group(1)
                full_url = f"https://medofast.ir{nav_url}" if nav_url.startswith("/") else nav_url
                await self.page.goto(full_url, wait_until="networkidle", timeout=30000)
            else:
                await self.page.evaluate("btn => btn.click()", next_btn)
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
        else:
            await self.page.evaluate("btn => btn.click()", next_btn)

        await self.wait_for_question_load()

        # Verify navigation
        new_number = await self.get_question_number_from_page()
        if new_number and new_number == current_number:
            self.log("     ⚠️ Still on the same question. Navigation failed.")
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

            self.log(f"⏳ Waiting for you to login manually. Click 'Confirm Login' button in GUI when ready.")

            while not login_confirmed_event.is_set():
                if self.is_stopped:
                    await self.browser.close()
                    return
                try:
                    await asyncio.wait_for(login_confirmed_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass

            self.log("🌐 Going to questions page...")
            await self.page.goto(self.url, wait_until="networkidle", timeout=30000)
            await self.wait_for_question_load()

            logged_in_mode = await self.page.evaluate(
                "() => document.body.getAttribute('data-user-authenticated') === 'true'"
            )
            self.log(f"🔑 Mode: {'Logged In ✅' if logged_in_mode else 'Guest'}")

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
                self.log(f"📊 Total Questions: {total_questions}")

            all_questions = []
            consecutive_failures = 0

            # Start from actual question number on page
            question_number = await self.get_question_number_from_page() or 1

            while not self.is_stopped:
                await self.check_pause()

                self.log(f"  ⏳ Extracting Question {question_number}" + (f" of {total_questions}" if total_questions else "") + " ...")

                data = await self.extract_current_question(question_number)
                correct = data.get("correct_option")
                self.log(f"     Correct Option: {'Option ' + str(correct) if correct else '⚠️  Not Found'}")
                all_questions.append(data)

                with open(self.output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_questions, f, ensure_ascii=False, indent=2)

                if total_questions and question_number >= total_questions:
                    self.log("✅ Reached the last question")
                    break

                await self.check_pause()
                success = await self.go_to_next(question_number, logged_in_mode)
                if not success:
                    # Retry once with longer delay
                    await asyncio.sleep(3)
                    success = await self.go_to_next(question_number, logged_in_mode)

                if not success:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        self.log(f"✅ Finished - Navigation failed twice (Question {question_number})")
                        break
                else:
                    consecutive_failures = 0
                    # Get new question number from page
                    new_num = await self.get_question_number_from_page()
                    if new_num:
                        question_number = new_num
                    else:
                        question_number += 1

            await self.browser.close()
            found = sum(1 for q in all_questions if q.get("correct_option"))
            self.log(f"\n✅ Extraction complete: {len(all_questions)} questions")
            self.log(f"🎯 Correct answers found: {found}/{len(all_questions)}")
            self.log(f"💾 Saved to: {self.output_path}")

    def pause(self):
        self.is_paused = True
        self.pause_event.clear()

    def resume(self):
        self.is_paused = False
        self.pause_event.set()

    def stop(self):
        self.is_stopped = True
        self.resume()
