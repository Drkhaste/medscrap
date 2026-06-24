import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:csv/csv.dart';
import 'package:share_plus/share_plus.dart';

class ExporterTab extends StatefulWidget {
  const ExporterTab({super.key});

  @override
  State<ExporterTab> createState() => _ExporterTabState();
}

class _ExporterTabState extends State<ExporterTab> {
  String _status = "Select JSON to Export";

  Future<void> _exportToCsv() async {
    setState(() => _status = "Exporting...");
    try {
      final directory = await getApplicationDocumentsDirectory();
      final jsonFile = File('${directory.path}/questions.json');

      if (!await jsonFile.exists()) {
        setState(() => _status = "No JSON data found. Start scraper first.");
        return;
      }

      final jsonStr = await jsonFile.readAsString();
      final List<dynamic> data = jsonDecode(jsonStr);

      List<List<dynamic>> rows = [];
      rows.add([
        "Question Number", "Exam", "Lesson", "Subject", "Text",
        "Opt 1", "Opt 2", "Opt 3", "Opt 4", "Correct", "Explanation"
      ]);

      for (var q in data) {
        var meta = q['metadata'] ?? {};
        var opts = q['options'] as List;
        List<String> optTexts = ["", "", "", ""];
        for (var o in opts) {
          int idx = o['number'] - 1;
          if (idx >= 0 && idx < 4) optTexts[idx] = o['text'];
        }

        rows.add([
          q['question_number'],
          meta['آزمون'],
          meta['درس'],
          meta['موضوع'],
          q['question_text'],
          optTexts[0],
          optTexts[1],
          optTexts[2],
          optTexts[3],
          (q['correct_options'] as List).join(", "),
          q['answer_explanation']
        ]);
      }

      String csvData = const ListToCsvConverter().convert(rows);
      final tempDir = await getTemporaryDirectory();
      final csvFile = File('${tempDir.path}/medofast_export.csv');
      await csvFile.writeAsString('\uFEFF$csvData'); // UTF-8-SIG

      await Share.shareXFiles([XFile(csvFile.path)], text: 'Medofast Scraper Export');

      setState(() => _status = "Export shared successfully.");
    } catch (e) {
      setState(() => _status = "Export failed: $e");
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Export Data')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.share, size: 64, color: Colors.blue),
              const SizedBox(height: 16),
              Text(_status, textAlign: TextAlign.center),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: _exportToCsv,
                icon: const Icon(Icons.ios_share),
                label: const Text('Export to CSV & Share'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
