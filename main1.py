"""
اسکریپت scraping برای تمام سوالات مدوفست
"""
from time import sleep
import asyncio
import base64
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).parent


async def wait_for_question_load(page):
    try:
        await page.wait_for_selector("#questionSkeletonLoader", state="hidden", timeout=8000)
    except:
        pass
    await page.wait_for_timeout(2000)
    sleep(1)


async def extract_current_question(page, question_number):
    result = {}

    async def get_text(selector):
        try:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except:
            pass
        return ""

    # متادیتا
    meta = {}
    meta["آزمون"]  = await get_text("li:has(i.fa-books)")
    meta["تاریخ"]  = await get_text("li:has(i.fa-calendar-check)")
    meta["درس"]    = await get_text("li:has(i.fa-syringe)")
    meta["موضوع"]  = await get_text("li:has(i.fa-hashtag)")

    diff_raw = await get_text("li:has(i.fa-fire-alt)")
    meta["سطح دشواری"] = re.sub(r'^سطح دشواری سوال[:\s]*', '', diff_raw).strip()

    stats_raw = await get_text("li:has(i.fa-chart-bar)")
    pct = re.search(r'(\d+)%', stats_raw)
    meta["درصد پاسخ صحیح"] = pct.group(1) + "%" if pct else ""

    try:
        h6_text = await page.text_content("h6")
        if h6_text:
            meta["موقعیت سوال"] = h6_text.strip()
    except:
        pass

    result["metadata"] = {k: v for k, v in meta.items() if v}

    # متن سوال + تصاویر
    question_text = ""
    question_images = []
    try:
        q_elem = await page.query_selector("#qtxt")
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
            q_elem = await page.query_selector(".qtext-before")
            if q_elem:
                question_text = await q_elem.inner_text()
        except:
            pass

    result["question_text"] = question_text.strip()
    result["question_images"] = question_images

    # گزینه‌ها
    options = []
    for i, opt_elem in enumerate(await page.query_selector_all(".encoded-option"), start=1):
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
        encoded_attrs = await page.eval_on_selector_all(
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

    result["options"] = options
    sleep(1)

    # ── انتخاب گزینه ۱ و زدن دکمه تایید ──
    try:
        await page.eval_on_selector(
            'input[type="radio"][value="1"]',
            "el => { let p = el.closest('[inert]'); if(p) p.removeAttribute('inert'); }"
        )
        radio = await page.query_selector('input[type="radio"][value="1"]')
        if radio:
            await radio.click(force=True)
    except:
        pass

    await page.wait_for_timeout(1000)

    try:
        btn = await page.query_selector("#show-b-btn")
        if btn:
            await page.evaluate("btn => btn.click()", btn)
    except:
        pass
    sleep(1)

    # ── صبر برای ظاهر شدن پاسخنامه ──
    # بعد از لاگین، block-b با AJAX پر می‌شه - صبر می‌کنیم تا محتوا بیاد
    answer_text = ""
    correct_option = None

    try:
        # صبر کن تا block-b نه‌تنها visible بشه، بلکه محتوا هم داشته باشه
        await page.wait_for_function(
            """() => {
                const block = document.getElementById('block-b');
                if (!block) return false;
                const text = block.innerText || '';
                // منتظر می‌مونیم تا متن معناداری بیاد (حداقل ۲۰ کاراکتر)
                return text.trim().length > 20;
            }""",
            timeout=8000
        )
        block = await page.query_selector("#block-b")
        if block:
            answer_text = await block.inner_text()
    except:
        # fallback: چند بار چک کن
        for _ in range(5):
            await page.wait_for_timeout(1000)
            try:
                block = await page.query_selector("#block-b")
                if block:
                    t = await block.inner_text()
                    if t.strip():
                        answer_text = t
                        break
            except:
                pass

    sleep(1)

    # ── تشخیص گزینه صحیح ──

    # روش ۱: از متن پاسخنامه - "تایید گزینه X"
    if answer_text:
        m = re.search(r'تایید گزینه\s*(\d)', answer_text)
        if m:
            correct_option = int(m.group(1))

    # روش ۲: از کلاس label‌ها (بعد از نمایش پاسخ، سایت label رو رنگی می‌کنه)
    if not correct_option:
        try:
            for i in range(1, 5):
                label = await page.query_selector(f"#label{i}")
                if label:
                    cls = await label.get_attribute("class") or ""
                    style = await label.get_attribute("style") or ""
                    bg = await page.evaluate(
                        f"() => window.getComputedStyle(document.getElementById('label{i}')).backgroundColor"
                    )
                    if ("success" in cls or "correct" in cls or
                            "green" in style.lower() or
                            "34" in bg):   # rgb شامل ۳۴ (رنگ سبز) باشه
                        correct_option = i
                        break
        except:
            pass

    # روش ۳: از progress bar - گزینه‌ای که bg-success داره (نه bg-danger)
    if not correct_option:
        try:
            for i in range(1, 5):
                bar = await page.query_selector(f"#prograssBar{i}")
                if bar:
                    cls = await bar.get_attribute("class") or ""
                    if "bg-success" in cls:
                        correct_option = i
                        break
        except:
            pass

    # روش ۴: از data-encoded-percent - بالاترین درصد (اگه پاسخ خیلی واضح باشه)
    # این روش آخرین fallback است
    if not correct_option:
        try:
            max_pct = -1
            for i in range(1, 5):
                bar = await page.query_selector(f"#prograssBar{i}")
                if bar:
                    enc = await bar.get_attribute("data-encoded-percent")
                    if enc:
                        pct_val = int(base64.b64decode(enc).decode())
                        if pct_val > max_pct:
                            max_pct = pct_val
                            # فقط اگه درصد > 50 باشه به عنوان پاسخ صحیح در نظر بگیر
                            if pct_val > 50:
                                correct_option = i
        except:
            pass

    result["correct_option"] = correct_option
    result["answer_explanation"] = answer_text.strip()
    result["question_number"] = question_number
    sleep(1)
    return result
    


async def go_to_next(page, current_number, logged_in_mode, total):
    next_btn = await page.query_selector("button[data-nav-role='next']")
    if not next_btn:
        return False

    cls = await next_btn.get_attribute("class") or ""
    if "turned-off" in cls:
        return False

    if logged_in_mode:
        onclick = await next_btn.get_attribute("onclick") or ""
        url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
        if url_match:
            nav_url = url_match.group(1)
            full_url = f"https://medofast.ir{nav_url}" if nav_url.startswith("/") else nav_url
            await page.goto(full_url, wait_until="networkidle", timeout=20000)
            await wait_for_question_load(page)
            return True

        await page.evaluate("btn => btn.click()", next_btn)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await wait_for_question_load(page)
        sleep(1)
        return True

    else:
        next_page = current_number + 1
        data_page = await next_btn.get_attribute("data-page") or ""
        if data_page and int(data_page) != next_page:
            await page.wait_for_timeout(1000)
            next_btn = await page.query_selector("button[data-nav-role='next']")
            if not next_btn:
                return False
            cls = await next_btn.get_attribute("class") or ""
            if "turned-off" in cls:
                return False

        await page.evaluate("btn => btn.click()", next_btn)
        try:
            await page.wait_for_function(
                f"() => document.querySelector('h6') && document.querySelector('h6').textContent.includes('سوال {next_page}')",
                timeout=8000
            )
        except:
            await wait_for_question_load(page)
        return True

async def scrape_all_questions(url: str, output_path: str, login_wait: int = 60):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"\n🌐 باز کردن صفحه لاگین...")
        await page.goto("https://medofast.ir/login", wait_until="networkidle", timeout=30000)

        print(f"\n{'='*50}")
        print(f"⏳ {login_wait} ثانیه فرصت داری تا لاگین کنی!")
        print(f"   بعد از لاگین، ربات خودکار شروع می‌کنه.")
        print(f"{'='*50}\n")

        logged_in = False
        for remaining in range(login_wait, 0, -1):
            current_url = page.url
            if "login" not in current_url and "otp" not in current_url:
                logged_in = True
                print(f"\n✅ لاگین تشخیص داده شد!")
                break
            print(f"\r  ⏱  {remaining} ثانیه باقیمانده...    ", end="", flush=True)
            await asyncio.sleep(1)

        if not logged_in:
            ans = input("\n   آیا لاگین انجام شده؟ (y/n): ").strip().lower()
            if ans != 'y':
                await browser.close()
                return []

        print()
        print(f"🌐 رفتن به صفحه سوالات...")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await wait_for_question_load(page)

        logged_in_mode = await page.evaluate(
            "() => document.body.getAttribute('data-user-authenticated') === 'true'"
        )
        print(f"🔑 حالت: {'لاگین شده ✅' if logged_in_mode else 'مهمان'}")

        total_questions = None
        try:
            h6_text = await page.text_content("h6")
            if h6_text:
                m = re.search(r'از\s*(\d+)', h6_text)
                if m:
                    total_questions = int(m.group(1))
        except:
            pass

        if total_questions:
            print(f"📊 تعداد کل سوالات: {total_questions}\n")

        all_questions = []
        question_number = 1
        consecutive_failures = 0

        while True:
            print(f"  ⏳ سوال {question_number}" + (f" از {total_questions}" if total_questions else "") + " ...")

            data = await extract_current_question(page, question_number)
            correct = data.get("correct_option")
            print(f"     پاسخ صحیح: {'گزینه ' + str(correct) if correct else '⚠️  پیدا نشد'}")
            all_questions.append(data)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_questions, f, ensure_ascii=False, indent=2)

            if total_questions and question_number >= total_questions:
                print("✅ به آخرین سوال رسیدیم")
                break

            success = await go_to_next(page, question_number, logged_in_mode, total_questions)
            if not success:
                await page.wait_for_timeout(2000)
                success = await go_to_next(page, question_number, logged_in_mode, total_questions)

            if not success:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    print(f"✅ پایان - دکمه بعدی در دسترس نیست (سوال {question_number})")
                    break
            else:
                consecutive_failures = 0
                question_number += 1

        await browser.close()
        found = sum(1 for q in all_questions if q.get("correct_option"))
        print(f"\n✅ استخراج کامل شد: {len(all_questions)} سوال")
        print(f"🎯 پاسخ صحیح پیدا شد: {found}/{len(all_questions)}")
        print(f"💾 ذخیره شد: {output_path}")
        return all_questions


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper تمام سوالات مدوفست")
    parser.add_argument("--url", default="https://medofast.ir/qbank/year-id-358")
    parser.add_argument("--output", default=str(SCRIPT_DIR / "questions.json"))
    parser.add_argument("--login-wait", type=int, default=60)
    args = parser.parse_args()

    questions = asyncio.run(scrape_all_questions(args.url, args.output, args.login_wait))

    print(f"\n📋 خلاصه:")
    print(f"   تعداد سوالات: {len(questions)}")
    if questions:
        print(f"   آزمون: {questions[0]['metadata'].get('آزمون', '-')}")
