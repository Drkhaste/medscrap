import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:path_provider/path_provider.dart';

class ScraperEngine extends ChangeNotifier {
  InAppWebViewController? webViewController;
  bool isRunning = false;
  bool isPaused = false;
  List<String> logs = [];
  int questionsCount = 0;
  String currentStatus = "Ready";

  // Settings
  String startUrl = "https://medofast.ir/qbank";
  double clickDelay = 2.0;
  double questionLoadDelay = 3.0;
  double answerLoadDelay = 2.0;
  bool skipExplanation = false;
  bool saveScreenshots = false;

  Completer<void>? _loginCompleter;
  List<Map<String, dynamic>> allQuestions = [];

  void addLog(String message) {
    logs.add("${DateTime.now().toString().split(' ')[1].substring(0, 8)}: $message");
    if (logs.length > 500) logs.removeAt(0);
    notifyListeners();
  }

  Future<void> startScraping() async {
    if (isRunning) return;
    isRunning = true;
    isPaused = false;
    allQuestions = [];
    questionsCount = 0;
    currentStatus = "Starting...";
    addLog("🌐 Opening login page...");
    notifyListeners();

    try {
      await webViewController?.loadUrl(
          urlRequest: URLRequest(url: WebUri("https://medofast.ir/login")));

      _loginCompleter = Completer<void>();
      addLog("⏳ Waiting for login confirmation...");
      await _loginCompleter!.future;

      addLog("🌐 Navigating to URL: $startUrl");
      await webViewController?.loadUrl(
          urlRequest: URLRequest(url: WebUri(startUrl)));

      _runScrapingLoop();
    } catch (e) {
      addLog("❌ Error: $e");
      isRunning = false;
      notifyListeners();
    }
  }

  void stopScraping() {
    isRunning = false;
    currentStatus = "Stopped";
    addLog("🛑 Scraper stopped.");
    notifyListeners();
  }

  void togglePause() {
    isPaused = !isPaused;
    addLog(isPaused ? "⏸ Paused" : "▶️ Resumed");
    notifyListeners();
  }

  void confirmLogin() {
    if (_loginCompleter != null && !_loginCompleter!.isCompleted) {
      _loginCompleter!.complete();
    }
  }

  Future<void> _runScrapingLoop() async {
    while (isRunning) {
      if (isPaused) {
        await Future.delayed(const Duration(seconds: 1));
        continue;
      }

      currentStatus = "Extracting Question...";
      notifyListeners();

      try {
        // Wait for loader to disappear
        await _waitForElementHidden("#questionSkeletonLoader");
        await Future.delayed(Duration(milliseconds: (questionLoadDelay * 1000).toInt()));

        // Extract
        var dataResult = await webViewController?.evaluateJavascript(source: extractionJs);
        if (dataResult == null) {
          addLog("⚠️ Failed to extract data. Retrying...");
          await Future.delayed(const Duration(seconds: 3));
          continue;
        }

        Map<String, dynamic> questionData = Map<String, dynamic>.from(dataResult);
        addLog("📖 Question ${questionData['question_number']}");

        // Handle Radio and Submit
        await webViewController?.evaluateJavascript(source: """
          (function() {
            const radio = document.querySelector('input[type="radio"][value="1"]');
            if (radio) {
              let p = radio.closest('[inert]');
              if (p) p.removeAttribute('inert');
              radio.disabled = false;
              radio.click();
            }
            const btn = document.querySelector('#show-b-btn');
            if (btn) btn.click();
          })();
        """);

        await Future.delayed(Duration(milliseconds: (clickDelay * 1000).toInt()));

        // Extract Answer
        currentStatus = "Waiting for Answer...";
        notifyListeners();

        // Wait for block-b
        if (!skipExplanation) {
          await _waitForElementContent("#block-b");
        }

        var answerDataResult = await webViewController?.evaluateJavascript(source: answerExtractionJs);
        if (answerDataResult != null) {
          questionData.addAll(Map<String, dynamic>.from(answerDataResult));
        }

        allQuestions.add(questionData);
        await _saveData();
        questionsCount = allQuestions.length;
        addLog("✅ Saved. Correct: ${questionData['correct_options']}");

        // Next
        currentStatus = "Moving to Next...";
        notifyListeners();
        bool hasNext = await _goToNext();
        if (!hasNext) {
          addLog("🏁 Reached the end or navigation failed.");
          break;
        }

      } catch (e) {
        addLog("⚠️ Loop error: $e");
        await Future.delayed(const Duration(seconds: 5));
      }
    }
    isRunning = false;
    currentStatus = "Finished";
    notifyListeners();
  }

  Future<bool> _goToNext() async {
    var currentNum = await webViewController?.evaluateJavascript(source: """
      (function() {
        let h6 = document.querySelector('h6');
        if (h6) {
          let m = h6.innerText.match(/سوال\\s*(\\d+)/);
          return m ? m[1] : null;
        }
        return null;
      })();
    """);

    await webViewController?.evaluateJavascript(source: """
      (function() {
        const btn = document.querySelector("button[data-nav-role='next']");
        if (!btn || btn.classList.contains('turned-off')) return false;
        btn.click();
        return true;
      })();
    """);

    // Wait for question number to change
    for (int i = 0; i < 10; i++) {
      await Future.delayed(const Duration(seconds: 1));
      var newNum = await webViewController?.evaluateJavascript(source: """
        (function() {
          let h6 = document.querySelector('h6');
          if (h6) {
            let m = h6.innerText.match(/سوال\\s*(\\d+)/);
            return m ? m[1] : null;
          }
          return null;
        })();
      """);
      if (newNum != currentNum && newNum != null) return true;
    }
    return false;
  }

  Future<void> _waitForElementHidden(String selector) async {
    for (int i = 0; i < 15; i++) {
      var isHidden = await webViewController?.evaluateJavascript(source: """
        (function() {
          let el = document.querySelector('$selector');
          return !el || el.offsetParent === null || window.getComputedStyle(el).display === 'none';
        })();
      """);
      if (isHidden == true) return;
      await Future.delayed(const Duration(seconds: 1));
    }
  }

  Future<void> _waitForElementContent(String selector) async {
    for (int i = 0; i < 10; i++) {
      var hasContent = await webViewController?.evaluateJavascript(source: """
        (function() {
          let el = document.querySelector('$selector');
          return el && el.innerText.trim().length > 3;
        })();
      """);
      if (hasContent == true) return;
      await Future.delayed(const Duration(seconds: 1));
    }
  }

  Future<void> _saveData() async {
    final directory = await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/questions.json');
    await file.writeAsString(jsonEncode(allQuestions));
  }

  String get extractionJs => """
    (function() {
      function get_text(selector) {
        let el = document.querySelector(selector);
        return el ? el.innerText.trim() : "";
      }
      let meta = {
        "آزمون": get_text("li:has(i.fa-books)"),
        "تاریخ": get_text("li:has(i.fa-calendar-check)"),
        "درس": get_text("li:has(i.fa-syringe)"),
        "موضوع": get_text("li:has(i.fa-hashtag)"),
      };
      let h6 = document.querySelector('h6');
      let qNum = 0;
      if (h6) {
        let m = h6.innerText.match(/سوال\\s*(\\d+)/);
        if (m) qNum = parseInt(m[1]);
      }
      let options = [];
      document.querySelectorAll(".encoded-option").forEach((el, i) => {
        let text = el.innerText.trim();
        if (!text) {
          let enc = el.getAttribute('data-encoded-text');
          if (enc) { try { text = atob(enc); } catch(e) {} }
        }
        options.push({"number": i+1, "text": text});
      });
      return {
        "metadata": meta,
        "question_text": get_text("#qtxt"),
        "options": options,
        "question_number": qNum
      };
    })()
  """;

  String get answerExtractionJs => """
    (function() {
      let block = document.getElementById('block-b');
      let text = block ? block.innerText : "";
      let corrects = [];

      for (let i = 1; i <= 4; i++) {
        let label = document.getElementById('label' + i);
        let bar = document.getElementById('prograssBar' + i);
        let check = (el) => {
          if (!el) return false;
          let style = window.getComputedStyle(el);
          let bg = style.backgroundColor;
          return bg.includes('rgb(34') || bg.includes('rgb(0, 128') || bg.includes('rgb(76, 175, 80)');
        };
        if (check(label) || check(bar)) {
           corrects.push(i);
        }
      }
      return {
        "answer_explanation": text,
        "correct_options": corrects
      };
    })()
  """;
}
