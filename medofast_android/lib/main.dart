import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'scraper_engine.dart';
import 'exporter_tab.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ChangeNotifierProvider(
      create: (context) => ScraperEngine(),
      child: const MedofastApp(),
    ),
  );
}

class MedofastApp extends StatelessWidget {
  const MedofastApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Medofast Scraper',
      theme: ThemeData(
        primaryColor: const Color(0xFF1E88E5),
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _selectedIndex = 0;

  final List<Widget> _tabs = [
    const ScraperTab(),
    const BrowserTab(),
    const ExporterTab(),
    const SettingsTab(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _selectedIndex,
        children: _tabs,
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: (index) => setState(() => _selectedIndex = index),
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.bolt), label: 'Scraper'),
          BottomNavigationBarItem(icon: Icon(Icons.web), label: 'Browser'),
          BottomNavigationBarItem(icon: Icon(Icons.file_download), label: 'Export'),
          BottomNavigationBarItem(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}

class ScraperTab extends StatelessWidget {
  const ScraperTab({super.key});

  @override
  Widget build(BuildContext context) {
    final engine = Provider.of<ScraperEngine>(context);
    final ScrollController scrollController = ScrollController();

    // Auto-scroll logs
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (scrollController.hasClients) {
        scrollController.animateTo(
          scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Medofast Bot')),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: Colors.blue.withOpacity(0.1),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _ActionButton(
                      onPressed: engine.isRunning ? null : engine.startScraping,
                      icon: Icons.play_arrow,
                      label: 'Start',
                      color: Colors.green,
                    ),
                    _ActionButton(
                      onPressed: engine.isRunning ? engine.stopScraping : null,
                      icon: Icons.stop,
                      label: 'Stop',
                      color: Colors.red,
                    ),
                    _ActionButton(
                      onPressed: engine.isRunning ? engine.togglePause : null,
                      icon: engine.isPaused ? Icons.play_arrow : Icons.pause,
                      label: engine.isPaused ? 'Resume' : 'Pause',
                      color: Colors.orange,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: engine.isRunning ? engine.confirmLogin : null,
                  style: ElevatedButton.styleFrom(minimumSize: const Size(double.infinity, 45)),
                  child: const Text('Confirm Login'),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Status: ${engine.currentStatus}', style: const TextStyle(fontWeight: FontWeight.bold)),
                Text('Questions: ${engine.questionsCount}'),
              ],
            ),
          ),
          Expanded(
            child: Container(
              margin: const EdgeInsets.all(8),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.circular(8),
              ),
              child: ListView.builder(
                controller: scrollController,
                itemCount: engine.logs.length,
                itemBuilder: (context, index) => Text(
                  engine.logs[index],
                  style: const TextStyle(color: Colors.greenAccent, fontFamily: 'monospace', fontSize: 12),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final VoidCallback? onPressed;
  final IconData icon;
  final String label;
  final Color color;

  const _ActionButton({this.onPressed, required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        IconButton.filled(
          onPressed: onPressed,
          icon: Icon(icon),
          style: IconButton.styleFrom(backgroundColor: onPressed == null ? Colors.grey : color),
        ),
        Text(label, style: const TextStyle(fontSize: 12)),
      ],
    );
  }
}

class BrowserTab extends StatelessWidget {
  const BrowserTab({super.key});

  @override
  Widget build(BuildContext context) {
    final engine = Provider.of<ScraperEngine>(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Live WebView')),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri(engine.startUrl)),
        initialSettings: InAppWebViewSettings(
          javaScriptEnabled: true,
          userAgent: "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        ),
        onWebViewCreated: (controller) => engine.webViewController = controller,
      ),
    );
  }
}

class SettingsTab extends StatelessWidget {
  const SettingsTab({super.key});

  @override
  Widget build(BuildContext context) {
    final engine = Provider.of<ScraperEngine>(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            decoration: const InputDecoration(labelText: 'Start URL', border: OutlineInputBorder()),
            onChanged: (val) => engine.startUrl = val,
            controller: TextEditingController(text: engine.startUrl),
          ),
          const SizedBox(height: 20),
          const Text('Delays (seconds)', style: TextStyle(fontWeight: FontWeight.bold)),
          _SliderSetting(
            label: 'Click Delay',
            value: engine.clickDelay,
            onChanged: (v) => engine.clickDelay = v,
          ),
          _SliderSetting(
            label: 'Question Load',
            value: engine.questionLoadDelay,
            onChanged: (v) => engine.questionLoadDelay = v,
          ),
          SwitchListTile(
            title: const Text('Skip Explanations'),
            subtitle: const Text('Faster but misses explanation text'),
            value: engine.skipExplanation,
            onChanged: (val) => engine.skipExplanation = val,
          ),
        ],
      ),
    );
  }
}

class _SliderSetting extends StatelessWidget {
  final String label;
  final double value;
  final Function(double) onChanged;

  const _SliderSetting({required this.label, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$label: ${value.toStringAsFixed(1)}s'),
        Slider(value: value, min: 0.5, max: 15, onChanged: (v) => onChanged(v)),
      ],
    );
  }
}
