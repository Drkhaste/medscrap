import 'package:flutter_test/flutter_test.dart';
import 'package:medofast_scraper/scraper_engine.dart';

void main() {
  test('ScraperEngine initial state', () {
    final engine = ScraperEngine();
    expect(engine.isRunning, false);
    expect(engine.isPaused, false);
    expect(engine.currentStatus, "Ready");
  });

  test('ScraperEngine log addition', () {
    final engine = ScraperEngine();
    engine.addLog("Test log");
    expect(engine.logs.length, 1);
    expect(engine.logs[0].contains("Test log"), true);
  });
}
