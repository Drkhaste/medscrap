import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medofast_scraper/main.dart';
import 'package:provider/provider.dart';
import 'package:medofast_scraper/scraper_engine.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (context) => ScraperEngine(),
        child: const MedofastApp(),
      ),
    );

    expect(find.text('Medofast Bot'), findsOneWidget);
    expect(find.byIcon(Icons.bolt), findsOneWidget);
  });
}
