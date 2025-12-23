import 'package:flutter/material.dart';

class ScoreGauge extends StatelessWidget {
  final int score;
  final String label;

  const ScoreGauge({super.key, required this.score, required this.label});

  @override
  Widget build(BuildContext context) {
    final pct = (score.clamp(0, 100)) / 100.0;
    return SizedBox(
      width: 180,
      height: 180,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 180,
            height: 180,
            child: CircularProgressIndicator(
              value: pct,
              strokeWidth: 14,
              backgroundColor: Theme.of(context).colorScheme.surfaceVariant,
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text("$score", style: const TextStyle(fontSize: 46, fontWeight: FontWeight.w700)),
              Text(label, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
            ],
          ),
        ],
      ),
    );
  }
}
